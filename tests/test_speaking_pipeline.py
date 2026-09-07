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
def make_wav(seconds=1.0, rate=48000, channels=2, gain=1.0):
    """Audio shaped like speech: bursts with near-silent gaps between them.

    A constant tone will not do. The gate tests the spread between a
    recording's loud and quiet frames, because that is what separates a quiet
    child from a quiet room - and a flat signal has no spread at all.
    """
    import math

    frames = int(seconds * rate)
    samples = []
    for i in range(frames):
        t = i / rate
        on = math.sin(2 * math.pi * 3.5 * t) > 0.1
        envelope = 1.0 if on else 0.002
        value = int(gain * 9000 * envelope * math.sin(2 * math.pi * 180 * t))
        samples.append(max(-32768, min(32767, value)))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(
            struct.pack("<h", v) * channels for v in samples
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


# ---------------------------------------------------------------------------
# WCPM is a whole-test measure
# ---------------------------------------------------------------------------
class TestTestLevelWcpm:
    """Grade norms assume ~a minute of connected reading, not one sentence."""

    def _answered(self, correct_words, span_ms):
        return {
            "status": "answered",
            "scores": {"pron_score": 90.0, "accuracy": 90.0, "fluency": 90.0,
                       "completeness": 90.0, "prosody": 90.0},
            "reading": {"correct_words": correct_words, "total_words": correct_words,
                        "wcpm": round(correct_words / (span_ms / 60000.0), 1),
                        "accuracy_pct": 100.0},
            "timing": {"speaking_span_ms": span_ms, "pause_count": 0,
                       "long_pause_count": 0},
            "disfluency": {"filler_count": 0, "repetitions": 0},
            "errors": {}, "phonics": {},
        }

    def test_totals_not_the_mean_of_per_sentence_rates(self):
        # Eight 9-word sentences, 2.4s each: 72 words in 19.2s.
        rows = [self._answered(9, 2400) for _ in range(8)]
        signals = aggregate(rows, "First")
        assert signals["correct_words"] == 72
        assert signals["speaking_seconds"] == pytest.approx(19.2, abs=0.1)
        assert signals["wcpm"] == pytest.approx(225.0, abs=1.0)

    def test_a_slow_reader_lands_in_band(self):
        # 9 words in 12s per sentence -> 45 wcpm, inside the First band.
        rows = [self._answered(9, 12_000) for _ in range(8)]
        signals = aggregate(rows, "First")
        assert signals["wcpm"] == pytest.approx(45.0, abs=1.0)
        assert signals["wcpm_band"] == "in_band"

    def test_no_speaking_time_is_no_reading(self):
        signals = aggregate([], "First")
        assert signals["wcpm"] == 0.0
        assert signals["wcpm_band"] == "no_reading"

    def test_unattempted_sentences_do_not_add_time(self):
        rows = [self._answered(9, 12_000),
                {"status": "not_attempted", "scores": {}, "reading": {}, "timing": {},
                 "disfluency": {}, "errors": {}, "phonics": {}}]
        signals = aggregate(rows, "First")
        assert signals["speaking_seconds"] == pytest.approx(12.0, abs=0.1)
        assert signals["correct_words"] == 9


# ---------------------------------------------------------------------------
# Edge cases a transcriber auto-corrects away
# ---------------------------------------------------------------------------
def _mk_word(word, accuracy, error, offset_ms, duration_ms, phonemes,
             monotone=0.0):
    from app.infrastructure.azure_pronunciation import Phoneme, Word as W

    return W(
        word=word, accuracy=accuracy, error_type=error,
        offset_ms=offset_ms, duration_ms=duration_ms,
        phonemes=[Phoneme(ipa=i, accuracy=a, offset_ms=offset_ms, duration_ms=30)
                  for i, a in phonemes],
        monotone_confidence=monotone,
    )


class TestWordFindings:
    """Azure flags Mispronunciation below 60 only. Measured against deliberate
    errors, "dug" for "dog" scored 67 and "doggggg" scored 76 - neither
    flagged, though a teacher would mark both. And the recognised text said
    "dog" for every one of them, so the transcript cannot be the detector."""

    from app.engines.speaking.metrics import word_findings

    def _sentence(self, target):
        return [
            _mk_word("the", 96, "None", 0, 200, [("ð", 96), ("ə", 96)]),
            _mk_word("brown", 95, "None", 220, 300,
                     [("b", 95), ("ɹ", 95), ("aʊ", 95), ("n", 95)]),
            target,
            _mk_word("likes", 97, "None", 1200, 300,
                     [("l", 97), ("aɪ", 97), ("k", 97), ("s", 97)]),
        ]

    def _flags(self, target):
        from app.engines.speaking.metrics import word_findings

        found = word_findings(self._sentence(target))
        return next(f for f in found if f["word"] == target.word)["flags"]

    def test_a_correct_word_is_not_flagged(self):
        dog = _mk_word("dog", 100, "None", 600, 220,
                       [("d", 100), ("ɑ", 100), ("g", 100)])
        assert self._flags(dog) == []

    def test_a_word_azure_calls_fine_at_67_is_still_flagged(self):
        """The "dug" case: Azure said ErrorType None, a teacher would not."""
        dog = _mk_word("dog", 67, "None", 600, 220,
                       [("d", 71), ("ɑ", 50), ("g", 80)])
        assert self._flags(dog), "a word at 67 reached the parent unflagged"

    def test_the_middle_band_is_needs_attention_not_a_clear_error(self):
        """Audibly off, but still recognisably the word."""
        dog = _mk_word("dog", 78, "None", 600, 220,
                       [("d", 90), ("ɑ", 62), ("g", 82)])
        flags = self._flags(dog)
        assert "needs_attention" in flags
        assert "clear_error" not in flags

    def test_a_word_at_59_is_a_clear_error(self):
        dog = _mk_word("dog", 59, "Mispronunciation", 600, 220,
                       [("d", 100), ("ɔ", 37), ("g", 4)])
        assert "clear_error" in self._flags(dog)

    def test_a_stretched_word_is_caught_by_duration(self):
        """The "doggggg" case: every sound present, so accuracy stays high."""
        dog = _mk_word("dog", 94, "None", 600, 1500,
                       [("d", 100), ("ɑ", 100), ("g", 81)])
        flags = self._flags(dog)
        assert "prolonged" in flags, flags
        assert "clear_error" not in flags

    def test_a_normal_length_word_is_not_prolonged(self):
        dog = _mk_word("dog", 97, "None", 600, 230,
                       [("d", 97), ("ɑ", 97), ("g", 97)])
        assert "prolonged" not in self._flags(dog)

    def test_the_weakest_sound_is_named(self):
        from app.engines.speaking.metrics import word_findings

        dog = _mk_word("dog", 59, "Mispronunciation", 600, 220,
                       [("d", 100), ("ɔ", 37), ("g", 4)])
        found = word_findings(self._sentence(dog))
        weakest = next(f for f in found if f["word"] == "dog")["weakest_sound"]
        assert weakest["ipa"] == "g"
        assert weakest["accuracy"] == 4

    def test_omission_is_reported_as_omission_not_a_low_score(self):
        from app.engines.speaking.metrics import word_findings

        dog = _mk_word("dog", 0, "Omission", 0, 0, [])
        flags = next(f for f in word_findings(self._sentence(dog))
                     if f["word"] == "dog")["flags"]
        assert flags == ["omitted"]

    def test_monotone_confidence_is_surfaced(self):
        dog = _mk_word("dog", 97, "None", 600, 220,
                       [("d", 97), ("ɑ", 97), ("g", 97)], monotone=0.8)
        assert "monotone" in self._flags(dog)

    def test_prolongation_needs_enough_words_to_compare(self):
        from app.engines.speaking.metrics import word_findings

        pair = [_mk_word("dog", 95, "None", 0, 1500,
                         [("d", 95), ("ɑ", 95), ("g", 95)])]
        assert word_findings(pair)[0]["flags"] == []

    def test_counts_roll_up(self):
        from app.engines.speaking.metrics import error_counts

        dog = _mk_word("dog", 52, "Mispronunciation", 600, 220,
                       [("d", 47), ("ɑ", 40), ("g", 100)])
        counts = error_counts(self._sentence(dog))
        assert counts["clear_error"] == 1
        assert counts["words_flagged"] == 1
        assert counts["mispronunciation"] == 1


# ---------------------------------------------------------------------------
# The guarantee: nothing said, or the wrong thing said -> no score
# ---------------------------------------------------------------------------
class TestNoScoreGuarantee:
    """Verified live: a reading of "Elephants migrate across the savannah"
    against the reference "The cat sat on the mat." came back scored 32.5 with
    the transcript "The cat the sat cat the on." Azure aligns its recognition
    to the reference, so a child who read something else entirely produced a
    plausible number and a transcript full of reference words. Marking the
    item needs_review was not enough - the score was still returned."""

    LEAK_WORDS = ("purple", "wizards", "juggle", "bananas")
    REF = "Purple wizards juggle bananas."

    def _silent_wav(self, seconds=2.0):
        raw = bytearray(base64.b64decode(make_wav(seconds, 16000, 1)))
        raw[44:] = b"\x00" * (len(raw) - 44)
        return base64.b64encode(bytes(raw)).decode()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("audio_name", [
        "silent", "empty", "not_base64", "truncated",
    ])
    async def test_nothing_said_scores_zero(self, audio_name):
        audio = {
            "silent": self._silent_wav(),
            "empty": "",
            "not_base64": "!!!! nope !!!!",
            "truncated": base64.b64encode(b"RIFF" + b"\x00" * 60).decode(),
        }[audio_name]
        azure = FakeAzure()
        out = await SpeakingPipeline(azure, FakeTranscriber()).analyse_sentence(
            SentenceSubmission("s1", self.REF, audio), "First")

        assert out["status"] == "not_attempted"
        assert azure.calls == 0, "a silent recording reached a paid service"
        for key, value in out["scores"].items():
            assert value == 0.0, f"{key} was {value}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("audio_name", ["silent", "empty"])
    async def test_nothing_said_never_echoes_the_reference(self, audio_name):
        audio = self._silent_wav() if audio_name == "silent" else ""
        out = await SpeakingPipeline(FakeAzure(), FakeTranscriber()).analyse_sentence(
            SentenceSubmission("s1", self.REF, audio), "First")
        blob = str({k: v for k, v in out.items() if k != "reference"}).lower()
        for word in self.LEAK_WORDS:
            assert word not in blob, f"{word!r} leaked into the result"

    @pytest.mark.asyncio
    async def test_the_wrong_sentence_is_not_scored(self):
        """Not merely labelled needs_review - the numbers are withheld."""
        pipeline = SpeakingPipeline(
            FakeAzure(), FakeTranscriber("elephants migrate across the savannah"))
        out = await pipeline.analyse_sentence(
            SentenceSubmission("s1", REFERENCE, loud_wav()), "First")

        assert out["status"] == "needs_review"
        for key, value in out["scores"].items():
            assert value == 0.0, f"{key} was still {value} on a disagreement"
        assert out["recognized"] == ""
        assert out["reading"]["wcpm"] == 0.0
        assert all(v is None for v in out["phonics"].values())

    @pytest.mark.asyncio
    async def test_the_withheld_numbers_are_kept_for_diagnosis(self):
        pipeline = SpeakingPipeline(
            FakeAzure(), FakeTranscriber("elephants migrate across the savannah"))
        out = await pipeline.analyse_sentence(
            SentenceSubmission("s1", REFERENCE, loud_wav()), "First")
        assert out["withheld"]["reason"] == "channel_disagreement"
        assert out["withheld"]["scores"]["pron_score"] > 0

    @pytest.mark.asyncio
    async def test_a_withheld_sentence_does_not_move_the_test_average(self):
        pipeline = SpeakingPipeline(
            FakeAzure(), FakeTranscriber("elephants migrate across the savannah"))
        good = SpeakingPipeline(FakeAzure(), FakeTranscriber())
        wrong = await pipeline.analyse_sentence(
            SentenceSubmission("s1", REFERENCE, loud_wav()), "First")
        right = await good.analyse_sentence(
            SentenceSubmission("s2", REFERENCE, loud_wav()), "First")

        signals = aggregate([right, wrong], "First")
        assert signals["sentences_answered"] == 1
        assert signals["sentences_needs_review"] == 1
        assert signals["avg_pron_score"] == right["scores"]["pron_score"]

    @pytest.mark.asyncio
    async def test_a_real_reading_still_scores(self):
        """The guarantee must not be a blanket refusal to score."""
        out = await SpeakingPipeline(FakeAzure(), FakeTranscriber()).analyse_sentence(
            SentenceSubmission("s1", REFERENCE, loud_wav()), "First")
        assert out["status"] == "answered"
        assert out["scores"]["pron_score"] > 0


# ---------------------------------------------------------------------------
# What the child actually said, when no transcript will tell you
# ---------------------------------------------------------------------------
class TestSpokenPhonemes:
    """Verified live. Azure's recognised text reads "The brown dog likes to
    play." whether the child said dog, doy or dot, because scripted
    recognition aligns to the reference. NBestPhonemeCount asks a different
    question - what sound was actually produced here - and answers it:

        said 'dog'  expected /dɑg/  actually /dɑg/
        said 'doy'  expected /dɔg/  actually /dɔɪɔɪ/
        said 'dot'  expected /dɑg/  actually /dɑt/
    """

    def _payload(self, spoken_for_g):
        payload = azure_payload()
        payload["NBest"][0]["Words"] = [{
            "Word": "dog",
            "Offset": ticks(600), "Duration": ticks(220),
            "PronunciationAssessment": {"AccuracyScore": 40.0,
                                        "ErrorType": "Mispronunciation"},
            "Phonemes": [
                {"Phoneme": "d", "Offset": ticks(600), "Duration": ticks(60),
                 "PronunciationAssessment": {
                     "AccuracyScore": 100.0,
                     "NBestPhonemes": [{"Phoneme": "d", "Score": 100.0}]}},
                {"Phoneme": "ɑ", "Offset": ticks(660), "Duration": ticks(80),
                 "PronunciationAssessment": {
                     "AccuracyScore": 95.0,
                     "NBestPhonemes": [{"Phoneme": "ɑ", "Score": 100.0}]}},
                {"Phoneme": "g", "Offset": ticks(740), "Duration": ticks(80),
                 "PronunciationAssessment": {
                     "AccuracyScore": 0.0,
                     "NBestPhonemes": [
                         {"Phoneme": spoken_for_g, "Score": 100.0},
                         {"Phoneme": "ɑ", "Score": 99.0},
                     ]}},
            ],
        }]
        return payload

    def test_the_expected_sounds_are_reported(self):
        word = parse_result(self._payload("g")).words[0]
        assert word.expected_ipa == "dɑg"

    def test_the_actually_spoken_sounds_are_reported(self):
        """The "dot" case: a /t/ where the word needs a /g/."""
        word = parse_result(self._payload("t")).words[0]
        assert word.spoken_ipa == "dɑt"
        assert word.expected_ipa == "dɑg"

    def test_a_correct_reading_shows_no_substitution(self):
        word = parse_result(self._payload("g")).words[0]
        assert word.spoken_ipa == word.expected_ipa
        assert word.substituted_sounds == []

    def test_the_substituted_sound_is_named(self):
        word = parse_result(self._payload("t")).words[0]
        subs = word.substituted_sounds
        assert len(subs) == 1
        assert subs[0].ipa == "g"
        assert subs[0].actually_said == "t"

    def test_a_phoneme_without_candidates_falls_back_to_expected(self):
        """Older responses, or a service that returns no NBestPhonemes."""
        word = parse_result(azure_payload()).words[1]
        assert word.spoken_ipa == word.expected_ipa
        assert word.substituted_sounds == []

    def test_findings_carry_both_spellings(self):
        from app.engines.speaking.metrics import word_findings

        words = parse_result(self._payload("t")).words
        finding = word_findings(words)[0]
        assert finding["expected_ipa"] == "dɑg"
        assert finding["spoken_ipa"] == "dɑt"
        assert finding["substitutions"] == [
            {"expected": "g", "said": "t", "accuracy": 0.0}
        ]
        assert "sound_substituted" in finding["flags"]

    def test_the_weakest_sound_says_what_replaced_it(self):
        from app.engines.speaking.metrics import word_findings

        weakest = word_findings(parse_result(self._payload("t")).words)[0]["weakest_sound"]
        assert weakest["ipa"] == "g"
        assert weakest["actually_said"] == "t"

    def test_the_request_asks_for_spoken_phonemes(self):
        import json

        client = AzurePronunciationClient(key="k", region="eastus")
        config = json.loads(base64.b64decode(client.build_config_header("hi")))
        assert config["NBestPhonemeCount"] >= 1
        assert config["PhonemeAlphabet"] == "IPA"
