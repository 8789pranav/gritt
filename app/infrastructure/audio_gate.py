"""Deterministic checks on the audio itself, before any model sees it.

The speech analyser used to decide "was anything said?" by asking a language
model that had already been told which sentence to expect. With silence on the
tape and the sentence in its context, the model reliably invented a flawless
reading of it - three seconds of digital silence scored 89/100 against
"Purple wizards juggle seventeen bananas".

No prompt wording fixes that reliably. This module answers the question from
the waveform instead: measure the audio, and refuse to spend a model call on a
recording that contains no speech. It has no dependencies beyond the standard
library so it can run on any deployment.
"""

from __future__ import annotations

import array
import base64
import binascii
import io
import logging
import sys
import wave
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

#: Recordings shorter than this cannot contain a spoken sentence.
MIN_DURATION_SECONDS = 0.35

#: Mean amplitude (0-1) below which a recording is treated as silence.
#: Room tone on a laptop mic sits around 0.005-0.02; speech is well above 0.02.
MIN_RMS = 0.012

#: A recording needs some fraction of reasonably loud frames to be speech
#: rather than a click, a knock, or a burst of static.
MIN_VOICED_FRACTION = 0.06

#: Frames are analysed in windows of this length.
_FRAME_SECONDS = 0.03


#: array("h") is native-endian; WAV samples are little-endian.
_BIG_ENDIAN = sys.byteorder == "big"


def _rms(samples) -> float:
    """Root mean square of 16-bit samples, without the audioop module.

    audioop was removed from the standard library in Python 3.13 (PEP 594).
    This gate is what guarantees that silence scores zero, so it must not
    depend on a module that disappears when the base image is bumped.
    """
    if not samples:
        return 0.0
    total = 0
    for value in samples:
        total += int(value) * int(value)
    return (total / len(samples)) ** 0.5


@dataclass(frozen=True)
class AudioCheck:
    """What the waveform says about a submitted recording."""

    ok: bool
    reason: str
    duration_seconds: float = 0.0
    rms: float = 0.0
    voiced_fraction: float = 0.0
    peak: float = 0.0

    @property
    def has_speech(self) -> bool:
        return self.ok


def _decode_wav(raw: bytes) -> Optional[tuple[bytes, int, int, int]]:
    """Return (frames, sample_width, channels, rate) for a RIFF/WAVE payload."""
    try:
        with wave.open(io.BytesIO(raw), "rb") as handle:
            return (
                handle.readframes(handle.getnframes()),
                handle.getsampwidth(),
                handle.getnchannels(),
                handle.getframerate(),
            )
    except (wave.Error, EOFError, ValueError):
        return None


def inspect(audio_base64: str, audio_format: str = "wav") -> AudioCheck:
    """Measure a base64 recording and decide whether it contains speech.

    Only uncompressed WAV can be measured with the standard library. For any
    other container the check passes with ``reason="unmeasurable"`` so that a
    valid mp3 is never rejected - the caller still has the model-side guards.
    """
    if not audio_base64 or not audio_base64.strip():
        return AudioCheck(ok=False, reason="no_audio")

    try:
        raw = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError):
        return AudioCheck(ok=False, reason="undecodable_audio")

    if len(raw) < 128:
        return AudioCheck(ok=False, reason="no_audio")

    decoded = _decode_wav(raw)
    if decoded is None:
        if audio_format and audio_format.lower() != "wav":
            return AudioCheck(ok=True, reason="unmeasurable", duration_seconds=0.0)
        return AudioCheck(ok=False, reason="undecodable_audio")

    frames, width, channels, rate = decoded
    if not frames or not rate:
        return AudioCheck(ok=False, reason="empty_audio")
    if width != 2:
        # Only 16-bit PCM is measured here; anything else is passed through
        # to the transcription guard rather than being wrongly rejected.
        return AudioCheck(ok=True, reason="unmeasurable")

    samples = array.array("h")
    samples.frombytes(frames[: len(frames) - (len(frames) % 2)])
    if _BIG_ENDIAN:
        samples.byteswap()

    if channels > 1:
        samples = array.array("h", samples[::channels])

    if not samples:
        return AudioCheck(ok=False, reason="empty_audio")

    duration = len(samples) / float(rate)
    full_scale = 32768.0
    rms = _rms(samples) / full_scale
    peak = max(abs(int(v)) for v in samples) / full_scale

    window = max(1, int(rate * _FRAME_SECONDS))
    voiced = total = 0
    for start in range(0, len(samples) - window + 1, window):
        total += 1
        if _rms(samples[start:start + window]) / full_scale >= MIN_RMS:
            voiced += 1
    voiced_fraction = round(voiced / total, 4) if total else 0.0

    measured = {
        "duration_seconds": round(duration, 3),
        "rms": round(rms, 5),
        "voiced_fraction": voiced_fraction,
        "peak": round(peak, 5),
    }

    if duration < MIN_DURATION_SECONDS:
        return AudioCheck(ok=False, reason="too_short", **measured)
    if rms < MIN_RMS:
        return AudioCheck(ok=False, reason="silent", **measured)
    if voiced_fraction < MIN_VOICED_FRACTION:
        return AudioCheck(ok=False, reason="no_speech_detected", **measured)

    return AudioCheck(ok=True, reason="ok", **measured)


#: Parent-facing wording for each rejection reason.
REASON_MESSAGES = {
    "no_audio": "No recording was received for this sentence.",
    "undecodable_audio": "The recording could not be read. Please try again.",
    "empty_audio": "The recording was empty. Please try again.",
    "too_short": "The recording was too short to contain the sentence.",
    "silent": "No sound was picked up. Check the microphone and try again.",
    "no_speech_detected": "No speech was detected in the recording.",
}


def message_for(reason: str) -> str:
    return REASON_MESSAGES.get(reason, "No speech was detected in the recording.")
