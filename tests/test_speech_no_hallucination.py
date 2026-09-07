"""Regression tests for the speaking analyser scoring silence.

Three seconds of digital silence used to score 89.5/100 against "Purple
wizards juggle seventeen bananas", complete with an invented transcription of
that sentence, while a correct reading scored 65.6. The scoring prompt tells
the model which sentence to expect, and with nothing on the tape to contradict
it the model produced the expected answer.

These tests pin the two defences: a deterministic gate on the waveform, and a
transcription taken with no knowledge of the target sentence.
"""

from __future__ import annotations

import base64
import io
import math
import struct

import pytest

from app.infrastructure.audio_gate import (
    MIN_DURATION_SECONDS,
    AudioCheck,
    inspect,
    message_for,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def wav(samples, rate: int = 16000, channels: int = 1) -> str:
    data = b''.join(
        struct.pack('<h', int(max(-1.0, min(1.0, s)) * 32767)) for s in samples
    )
    buf = io.BytesIO()
    block = 2 * channels
    buf.write(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVE')
    buf.write(b'fmt ' + struct.pack('<IHHIIHH', 16, 1, channels, rate,
                                    rate * block, block, 16))
    buf.write(b'data' + struct.pack('<I', len(data)) + data)
    return base64.b64encode(buf.getvalue()).decode()


def silence(seconds=3.0, rate=16000):
    return wav([0.0] * int(seconds * rate), rate)


def room_tone(seconds=3.0, rate=16000):
    import random
    random.seed(11)
    return wav([random.uniform(-0.004, 0.004) for _ in range(int(seconds * rate))], rate)


def speech_like(seconds=2.0, rate=16000):
    """An amplitude-modulated buzz: loud, and voiced in bursts like speech."""
    out = []
    for i in range(int(seconds * rate)):
        t = i / rate
        envelope = 0.5 * (1 + math.sin(2 * math.pi * 3.5 * t))
        out.append(0.35 * envelope * math.sin(2 * math.pi * 180 * t))
    return wav(out, rate)


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------
class TestAudioGateRejectsNonSpeech:
    def test_pure_silence(self):
        check = inspect(silence(), 'wav')
        assert not check.has_speech
        assert check.reason == 'silent'
        assert check.rms == 0.0

    def test_room_tone_is_not_speech(self):
        check = inspect(room_tone(), 'wav')
        assert not check.has_speech
        assert check.reason in ('silent', 'no_speech_detected')

    def test_a_click_is_too_short(self):
        check = inspect(silence(0.1), 'wav')
        assert not check.has_speech
        assert check.reason == 'too_short'

    def test_empty_string(self):
        check = inspect('', 'wav')
        assert not check.has_speech
        assert check.reason == 'no_audio'

    def test_not_base64(self):
        check = inspect('!!!! not base64 !!!!', 'wav')
        assert not check.has_speech
        assert check.reason == 'undecodable_audio'

    def test_garbage_bytes_claiming_to_be_wav(self):
        check = inspect(base64.b64encode(b'x' * 4096).decode(), 'wav')
        assert not check.has_speech
        assert check.reason == 'undecodable_audio'

    def test_loud_modulated_audio_passes(self):
        """The gate must not reject something that could be speech."""
        check = inspect(speech_like(), 'wav')
        assert check.has_speech, check
        assert check.reason == 'ok'

    def test_stereo_is_handled(self):
        rate = 16000
        interleaved = []
        for i in range(int(1.5 * rate)):
            v = 0.3 * math.sin(2 * math.pi * 200 * i / rate)
            interleaved.extend([v, v])
        check = inspect(wav(interleaved, rate, channels=2), 'wav')
        assert check.has_speech
        assert check.duration_seconds == pytest.approx(1.5, abs=0.05)

    def test_duration_is_measured(self):
        check = inspect(speech_like(seconds=2.0), 'wav')
        assert check.duration_seconds == pytest.approx(2.0, abs=0.05)

    def test_non_wav_is_not_rejected_unheard(self):
        """An mp3 cannot be measured here; it must not be thrown away."""
        check = inspect(base64.b64encode(b'\xff\xfb' + b'\x00' * 4096).decode(), 'mp3')
        assert check.has_speech
        assert check.reason == 'unmeasurable'

    @pytest.mark.parametrize('reason', [
        'no_audio', 'undecodable_audio', 'empty_audio',
        'too_short', 'silent', 'no_speech_detected',
    ])
    def test_every_reason_has_parent_wording(self, reason):
        assert message_for(reason)
        assert not message_for(reason).endswith('None')


# ---------------------------------------------------------------------------
# the zero-score result
# ---------------------------------------------------------------------------
class TestNoSpeechScoresZero:
    def _result(self, sentence='Purple wizards juggle seventeen bananas.'):
        from app.infrastructure.hybrid_speech import HybridSpeechProvider

        return HybridSpeechProvider._no_speech_result(
            sentence, 'silent', message_for('silent'),
            AudioCheck(ok=False, reason='silent', duration_seconds=3.0),
        )

    def test_overall_is_zero(self):
        assert self._result()['analysis']['overall']['score'] == 0.0

    @pytest.mark.parametrize('section,key', [
        ('pronunciation', 'score'),
        ('fluency', 'fluency_score'),
        ('prosody', 'score'),
        ('grammar', 'grammar_score'),
        ('completeness', 'completeness_score'),
    ])
    def test_every_sub_score_is_zero(self, section, key):
        assert self._result()['analysis'][section][key] == 0.0

    def test_nothing_is_transcribed(self):
        result = self._result()
        assert result['transcribed_text'] == ''
        assert result['analysis']['completeness']['spoken_words'] == 0

    def test_the_target_sentence_is_never_echoed(self):
        """The old failure invented the expected sentence out of silence."""
        sentence = 'Purple wizards juggle seventeen bananas.'
        blob = str(self._result(sentence))
        for word in ('purple', 'wizards', 'juggle', 'bananas'):
            assert word not in blob.lower(), word

    def test_it_is_marked_not_attempted(self):
        assert self._result()['analysis']['overall']['status'] == 'Not Attempted'

    def test_the_reason_is_reported(self):
        result = self._result()
        assert result['no_speech_reason'] == 'silent'
        assert result['audio_check']['reason'] == 'silent'


# ---------------------------------------------------------------------------
# grammar must not credit silence
# ---------------------------------------------------------------------------
class TestGrammarOnSilence:
    def _grammar(self, sentence, transcript):
        from app.infrastructure.hybrid_speech import HybridSpeechProvider

        return HybridSpeechProvider()._analyze_grammar(sentence, transcript, 'First')

    @pytest.mark.parametrize('sentence', [
        'The cat sat.',
        'The cat sat on the mat.',
        'A dog runs.',
        'I like it.',
    ])
    def test_empty_transcription_scores_zero(self, sentence):
        """A short sentence used to leave silence on 25-55 out of 100."""
        assert self._grammar(sentence, '')['grammar_score'] == 0.0

    def test_a_correct_reading_scores_full(self):
        result = self._grammar('The cat sat on the mat.', 'the cat sat on the mat')
        assert result['grammar_score'] == 100.0

    def test_deductions_scale_with_sentence_length(self):
        """Missing half a short sentence must cost like missing half a long one."""
        short = self._grammar('The cat sat.', 'the cat')
        assert short['grammar_score'] < 100.0
        assert short['grammar_score'] > 0.0

    def test_no_speech_is_reported_as_an_issue(self):
        issues = self._grammar('The cat sat.', '')['issues']
        assert any(i['type'] == 'no_speech' for i in issues)


# ---------------------------------------------------------------------------
# the transcript cross-check
# ---------------------------------------------------------------------------
class TestTranscriptAgreement:
    def _agree(self, a, b):
        from app.infrastructure.hybrid_speech import HybridSpeechProvider

        return HybridSpeechProvider._transcripts_agree(a, b)

    def test_identical(self):
        assert self._agree('the dog ran', 'the dog ran')

    def test_a_mispronunciation_still_agrees(self):
        assert self._agree('the dog ran through the park',
                           'the dog wan through the park')

    def test_a_different_sentence_does_not(self):
        assert not self._agree('the dog ran through the park',
                               'purple wizards juggle seventeen bananas')

    def test_empty_never_agrees(self):
        assert not self._agree('', 'the cat sat on the mat')
        assert not self._agree('the cat sat on the mat', '')
