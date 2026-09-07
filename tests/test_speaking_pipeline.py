"""Tests for the Voice Challenge signal chain.

Everything here runs without an Azure key and without a network: the Azure
response is a recorded fixture in the documented shape, so the parsing, the
derived metrics and the chain's control flow are all verifiable now, and the
only thing left to confirm against the live service is that Azure returns what
its contract says it returns.
"""

from __future__ import annotations

import asyncio
import base64
import io
import struct
import wave

import pytest

from app.engines.speaking.metrics import (
    PHONICS_FEATURES,
    build_sentence_metrics,
    classify_phoneme,
    disfluency_metrics,
    error_counts,
    phonics_scores,
    reading_metrics,
    timing_metrics,
)
from app.engines.speaking.pipeline import (
    SentenceSubmission,
    SpeakingPipeline,
    aggregate,
)
from app.infrastructure.azure_pronunciation import (
    AzureNotConfigured,
    AzurePronunciationClient,
    parse_result,
    pron_score,
    to_azure_wav,
)

MS = 10_000          # 100-ns ticks per millisecond
REFERENCE = "The brown dog ran."


def ticks(ms):
    return ms * MS


def _word(word, accuracy, error, offset_ms, duration_ms, phonemes):
    return {
        "Word": word,
        "Offset": ticks(offset_ms),
        "Duration": ticks(duration_ms),
        "PronunciationAssessment": {"AccuracyScore": accuracy, "ErrorType": error},
        "Phonemes": [
            {
                "Phoneme": ipa,
                "Offset": ticks(offset_ms),
                "Duration": ticks(30),
                "PronunciationAssessment": {"AccuracyScore": score},
            }
            for ipa, score in phonemes
        ],
    }


def azure_payload():
    """A response in the shape the published contract describes.

    "The brown dog ran." read with a weak diphthong in "brown", a 700 ms pause
    before "dog", and "ran" omitted.
    """
    return {
        "RecognitionStatus": "Success",
        "Display": "The brown dog.",
        "NBest": [{
            "Display": "The brown dog.",
            "PronunciationAssessment": {
                "AccuracyScore": 78.0,
                "FluencyScore": 65.0,
                "CompletenessScore": 75.0,
                "ProsodyScore": 82.0,
                "PronScore": 72.4,
            },
            "Words": [
                _word("The", 95.0, "None", 200, 250, [("ð", 96.0), ("ə", 94.0)]),
                _word("brown", 58.0, "Mispronunciation", 460, 400,
                      [("b", 92.0), ("r", 88.0), ("aʊ", 41.0), ("n", 90.0)]),
                _word("dog", 91.0, "None", 1560, 380,
                      [("d", 93.0), ("ɒ", 90.0), ("g", 89.0)]),
                _word("ran", 0.0, "Omission", 0, 0, []),
            ],
        }],
    }


@pytest.fixture
def result():
    return parse_result(azure_payload())


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
class TestParsing:
    def test_top_level_scores(self, result):
        assert result.accuracy == 78.0
        assert result.fluency == 65.0
        assert result.completeness == 75.0
        assert result.prosody == 82.0
        assert result.pron_score == 72.4

    def test_ticks_become_milliseconds(self, result):
        assert result.words[0].offset_ms == 200.0
        assert result.words[0].duration_ms == 250.0

    def test_error_types_are_preserved(self, result):
        assert result.words[1].error_type == "Mispronunciation"
        assert result.words[3].error_type == "Omission"

    def test_omitted_words_are_not_spoken(self, result):
        assert len(result.words) == 4
        assert len(result.spoken_words) == 3
        assert len(result.correct_words) == 2

    def test_phonemes_carry_ipa_and_accuracy(self, result):
        brown = result.words[1]
        assert [p.ipa for p in brown.phonemes] == ["b", "r", "aʊ", "n"]
        assert brown.phonemes[2].accuracy == 41.0

    def test_a_failed_recognition_scores_zero(self):
        failed = parse_result({"RecognitionStatus": "NoMatch"})
        assert failed.pron_score == 0.0
        assert failed.recognized_text == ""
        assert failed.words == []

    def test_missing_prosody_is_none_not_zero(self):
        payload = azure_payload()
        del payload["NBest"][0]["PronunciationAssessment"]["ProsodyScore"]
        assert parse_result(payload).prosody is None


# ---------------------------------------------------------------------------
# Azure's own weighting
# ---------------------------------------------------------------------------
class TestPronScoreFormula:
    def test_weakest_dimension_carries_most_weight(self):
        # sorted: 60, 80, 90, 100 -> .4*60 + .2*80 + .2*90 + .2*100
        assert pron_score(90, 80, 100, 60) == 78.0

    def test_without_prosody_uses_the_three_term_form(self):
        # sorted: 70, 80, 90 -> .6*70 + .2*80 + .2*90
        assert pron_score(80, 70, 90, None) == 76.0

    def test_a_flat_reader_cannot_hide_behind_accuracy(self):
        strong_but_flat = pron_score(100, 100, 100, 20)
        even = pron_score(80, 80, 80, 80)
        assert strong_but_flat < even

    def test_all_perfect(self):
        assert pron_score(100, 100, 100, 100) == 100.0


# ---------------------------------------------------------------------------
# derived timing
# ---------------------------------------------------------------------------
class TestTiming:
    def test_pause_before_dog_is_counted(self, result):
        # "brown" ends at 860 ms, "dog" starts at 1560 ms
        timing = timing_metrics(result.words)
        assert timing.pause_count == 1
        assert timing.long_pause_count == 1
        assert timing.longest_pause_ms == pytest.approx(700.0)

    def test_time_to_first_word(self, result):
        assert timing_metrics(result.words).time_to_first_word_ms == 200.0

    def test_omitted_words_do_not_create_phantom_pauses(self, result):
        """"ran" has offset 0 and would otherwise look like a huge gap."""
        assert timing_metrics(result.words).pause_count == 1

    def test_no_words_gives_zeroes(self):
        timing = timing_metrics([])
        assert timing.pause_count == 0
        assert timing.time_to_first_word_ms == 0.0


# ---------------------------------------------------------------------------
# WCPM
# ---------------------------------------------------------------------------
class TestReadingRate:
    def test_only_correct_words_count(self, result):
        reading = reading_metrics(result.words, "First")
        assert reading.total_words == 4
        assert reading.correct_words == 2

    def test_wcpm_is_correct_words_over_elapsed_minutes(self, result):
        reading = reading_metrics(result.words, "First", elapsed_ms=30_000)
        assert reading.wcpm == 4.0

    def test_rate_band_is_named_per_grade(self, result):
        slow = reading_metrics(result.words, "Third", elapsed_ms=60_000)
        assert slow.rate_band == "below_band"

    def test_no_speech_is_no_reading(self):
        assert reading_metrics([], "First").rate_band == "no_reading"


# ---------------------------------------------------------------------------
# phonics
# ---------------------------------------------------------------------------
class TestPhonics:
    def test_diphthong_is_an_other_vowel_pattern(self):
        assert "other_vowel_pattern" in classify_phoneme("aʊ", 2, 4)

    def test_short_and_long_vowels_are_separated(self):
        assert "short_vowel" in classify_phoneme("ɪ", 1, 3)
        assert "long_vowel" in classify_phoneme("iː", 1, 3)

    def test_a_digraph_is_one_ipa_symbol(self):
        features = classify_phoneme("ʃ", 0, 3)
        assert "consonant_digraph" in features
        assert "beginning_consonant" in features

    def test_position_decides_beginning_and_ending(self):
        assert classify_phoneme("d", 0, 3) == ["beginning_consonant"]
        assert classify_phoneme("g", 2, 3) == ["ending_consonant"]

    def test_the_weak_diphthong_pulls_its_feature_down(self, result):
        scores = phonics_scores(result.words)
        assert scores["other_vowel_pattern"] == 41.0
        assert scores["short_vowel"] > 80

    def test_a_blend_is_two_consonants_running_together(self, result):
        """"br" in brown."""
        blend = phonics_scores(result.words)["consonant_blend"]
        assert blend == pytest.approx(90.0, abs=0.1)

    def test_an_unexercised_feature_is_none_not_zero(self, result):
        scores = phonics_scores(result.words)
        assert scores["long_vowel"] is None

    def test_every_feature_is_reported(self, result):
        assert set(phonics_scores(result.words)) == set(PHONICS_FEATURES)


# ---------------------------------------------------------------------------
# disfluency
# ---------------------------------------------------------------------------
class TestDisfluency:
    def test_fillers_are_found(self):
        d = disfluency_metrics("the um brown uh dog ran", REFERENCE)
        assert d.fillers == ["um", "uh"]
        assert d.filler_count == 2

    def test_an_ordinary_word_in_the_sentence_is_not_a_filler(self):
        d = disfluency_metrics("i like it", "I like it.")
        assert d.filler_count == 0

    def test_the_same_word_is_a_filler_when_not_in_the_sentence(self):
        d = disfluency_metrics("the like brown dog", REFERENCE)
        assert "like" in d.fillers

    def test_repetitions_are_counted(self):
        d = disfluency_metrics("the the brown dog ran", REFERENCE)
        assert d.repetitions == 1
        assert d.repeated_words == ["the"]

    def test_filler_rate_excludes_the_fillers_themselves(self):
        d = disfluency_metrics("um the brown dog ran", REFERENCE)
        assert d.filler_rate_per_100w == 25.0

    def test_empty_transcript(self):
        d = disfluency_metrics("", REFERENCE)
        assert d.filler_count == 0
        assert d.filler_rate_per_100w == 0.0


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------
def test_error_counts(result):
    counts = error_counts(result.words)
    assert counts["mispronunciation"] == 1
    assert counts["omission"] == 1
    assert counts["insertion"] == 0


# ---------------------------------------------------------------------------
# audio normalisation
# ---------------------------------------------------------------------------
def make_wav(seconds=1.0, rate=48000, channels=2):
    frames = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(
            struct.pack("<h", 8000) * channels for _ in range(frames)
        ))
    return base64.b64encode(buf.getvalue()).decode()


class TestAudioNormalisation:
    def test_48k_stereo_becomes_16k_mono(self):
        out = to_azure_wav(make_wav(1.0, 48000, 2))
        with wave.open(io.BytesIO(out), "rb") as handle:
            assert handle.getframerate() == 16000
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2

    def test_duration_is_preserved(self):
        out = to_azure_wav(make_wav(2.0, 44100, 1))
        with wave.open(io.BytesIO(out), "rb") as handle:
            duration = handle.getnframes() / handle.getframerate()
        assert duration == pytest.approx(2.0, abs=0.05)

    def test_already_16k_mono_passes_through(self):
        out = to_azure_wav(make_wav(1.0, 16000, 1))
        with wave.open(io.BytesIO(out), "rb") as handle:
            assert handle.getframerate() == 16000

    def test_bad_base64_is_rejected(self):
        with pytest.raises(ValueError):
            to_azure_wav("!!!not base64!!!")


# ---------------------------------------------------------------------------
# the client's request shape
# ---------------------------------------------------------------------------
class TestClientConfiguration:
    def test_key_and_region_are_all_that_is_needed(self):
        client = AzurePronunciationClient(key="k", region="eastus")
        assert client.is_configured

    def test_missing_key_is_not_configured(self):
        assert not AzurePronunciationClient(key="", region="eastus").is_configured

    def test_endpoint_is_built_from_the_region(self):
        client = AzurePronunciationClient(key="k", region="westeurope")
        assert client.endpoint.startswith("https://westeurope.stt.speech")

    def test_config_header_is_base64_json(self):
        import json

        client = AzurePronunciationClient(key="k", region="eastus")
        config = json.loads(
            base64.b64decode(client.build_config_header("The cat sat."))
        )
        assert config["ReferenceText"] == "The cat sat."
        assert config["Granularity"] == "Phoneme"
        assert config["EnableMiscue"] is True
        assert config["EnableProsodyAssessment"] is True
        assert config["PhonemeAlphabet"] == "IPA"

    def test_headers_declare_the_sample_rate_we_send(self):
        client = AzurePronunciationClient(key="k", region="eastus")
        headers = client.build_headers("hello")
        assert headers["Ocp-Apim-Subscription-Key"] == "k"
        assert "samplerate=16000" in headers["Content-Type"]

    @pytest.mark.asyncio
    async def test_missing_credentials_raise_rather_than_score(self):
        client = AzurePronunciationClient(key="", region="")
        with pytest.raises(AzureNotConfigured):
            await client.assess(make_wav(), "hello")


# ---------------------------------------------------------------------------
# the chain
# ---------------------------------------------------------------------------
class FakeAzure:
    is_configured = True

    def __init__(self, payload=None, fail=False):
        self._payload = payload or azure_payload()
        self._fail = fail
        self.calls = 0

    async def assess(self, audio_base64, reference_text, enable_miscue=True):
        self.calls += 1
        if self._fail:
            raise RuntimeError("azure is down")
        return parse_result(self._payload)


class FakeTranscriber:
    def __init__(self, text="the brown dog"):
        self.text = text

    def _transcribe_blind(self, audio_bytes, audio_format):
        return self.text


def loud_wav(seconds=2.0):
    return make_wav(seconds, 16000, 1)


class TestPipeline:
    @pytest.mark.asyncio
    async def test_a_normal_sentence_is_scored(self):
        pipeline = SpeakingPipeline(FakeAzure(), FakeTranscriber())
        out = await pipeline.analyse_sentence(
            SentenceSubmission("s1", REFERENCE, loud_wav(), time_to_speak_ms=1400),
            "First",
        )
        assert out["status"] == "answered"
        assert out["scores"]["pron_score"] == 72.4
        assert out["timing"]["time_to_speak_ms"] == 1400.0
        assert out["phonics"]["other_vowel_pattern"] == 41.0

    @pytest.mark.asyncio
    async def test_silence_never_reaches_azure(self):
        azure = FakeAzure()
        pipeline = SpeakingPipeline(azure, FakeTranscriber())
        silent = make_wav(2.0, 16000, 1)
        # overwrite the samples with zeroes
        raw = bytearray(base64.b64decode(silent))
        raw[44:] = b"\x00" * (len(raw) - 44)
        out = await pipeline.analyse_sentence(
            SentenceSubmission("s1", REFERENCE, base64.b64encode(bytes(raw)).decode()),
            "First",
        )
        assert azure.calls == 0, "silence was sent to a paid service"
        assert out["status"] == "not_attempted"
        assert out["scores"]["pron_score"] == 0.0
        assert out["recognized"] == ""

    @pytest.mark.asyncio
    async def test_silence_never_echoes_the_reference(self):
        pipeline = SpeakingPipeline(FakeAzure(), FakeTranscriber())
        out = await pipeline.analyse_sentence(
            SentenceSubmission("s1", "Purple wizards juggle bananas.", ""), "First",
        )
        blob = str(out).lower()
        for word in ("wizards", "juggle", "bananas"):
            assert word not in blob.replace("purple wizards juggle bananas.", "")

    @pytest.mark.asyncio
    async def test_disagreeing_channels_are_not_scored(self):
        pipeline = SpeakingPipeline(
            FakeAzure(), FakeTranscriber("completely different words entirely")
        )
        out = await pipeline.analyse_sentence(
            SentenceSubmission("s1", REFERENCE, loud_wav()), "First",
        )
        assert out["status"] == "needs_review"
        assert out["channel_agreement"] < 0.5

    @pytest.mark.asyncio
    async def test_an_azure_failure_is_not_a_score(self):
        pipeline = SpeakingPipeline(FakeAzure(fail=True), FakeTranscriber())
        out = await pipeline.analyse_sentence(
            SentenceSubmission("s1", REFERENCE, loud_wav()), "First",
        )
        assert out["status"] == "needs_review"
        assert out["scores"]["pron_score"] == 0.0

    @pytest.mark.asyncio
    async def test_sentences_run_concurrently(self):
        """App Runner's 120s timeout is fixed; eight in series does not fit."""
        import time

        class SlowAzure(FakeAzure):
            async def assess(self, *a, **k):
                await asyncio.sleep(0.15)
                return parse_result(self._payload)

        pipeline = SpeakingPipeline(SlowAzure(), FakeTranscriber())
        subs = [
            SentenceSubmission(f"s{i}", REFERENCE, loud_wav()) for i in range(8)
        ]
        start = time.perf_counter()
        out = await pipeline.analyse(subs, "First")
        elapsed = time.perf_counter() - start

        assert len(out) == 8
        assert elapsed < 0.15 * 8 * 0.6, f"ran in series: {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_results_keep_submission_order(self):
        pipeline = SpeakingPipeline(FakeAzure(), FakeTranscriber())
        subs = [
            SentenceSubmission(f"s{i}", REFERENCE, loud_wav()) for i in range(4)
        ]
        out = await pipeline.analyse(subs, "First")
        assert [r["sentence_id"] for r in out] == ["s0", "s1", "s2", "s3"]


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------
class TestAggregate:
    def _results(self):
        answered = build_sentence_metrics(
            parse_result(azure_payload()), REFERENCE, "First", "the brown dog"
        )
        answered["status"] = "answered"
        skipped = {"status": "not_attempted", "scores": {"pron_score": 0.0},
                   "reading": {"total_words": 4, "wcpm": 0.0}, "timing": {},
                   "disfluency": {}, "errors": {}, "phonics": {}}
        return [answered, dict(answered), skipped]

    def test_unattempted_sentences_do_not_drag_the_mean(self):
        signals = aggregate(self._results(), "First")
        assert signals["sentences_total"] == 3
        assert signals["sentences_answered"] == 2
        assert signals["avg_pron_score"] == 72.4

    def test_attempted_ratio_is_reported(self):
        signals = aggregate(self._results(), "First")
        assert signals["attempted_ratio"] == pytest.approx(0.667, abs=0.001)

    def test_phonics_rolls_up_and_keeps_none(self):
        signals = aggregate(self._results(), "First")
        assert signals["phonics_other_vowel_pattern"] == 41.0
        assert signals["phonics_long_vowel"] is None

    def test_error_counts_are_totalled(self):
        signals = aggregate(self._results(), "First")
        assert signals["mispronunciation_count"] == 2
        assert signals["omission_count"] == 2

    def test_an_empty_submission_is_all_zeroes(self):
        signals = aggregate([], "First")
        assert signals["sentences_total"] == 0
        assert signals["avg_pron_score"] == 0.0
        assert signals["attempted_ratio"] == 0.0
