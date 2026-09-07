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

#: The loudest part of a real recording, however quiet the child. Below this
#: there is no signal at all, only a dead microphone or digital silence.
MIN_PEAK_RMS = 0.0008

#: Speech is loud on vowels and near-silent between words, so the spread
#: between its quiet and loud frames is large. Steady noise has almost none.
#: Measured: speech from full volume down to 1% gain holds a p90/p10 frame
#: ratio of 111 or more, while room tone at every level and a pure tone both
#: sit at exactly 1.0. Thresholding the spread rather than the loudness is
#: what lets a child sitting back from the microphone through - the old
#: absolute cut-off rejected speech that Azure went on to score 98.
MIN_DYNAMIC_RANGE = 6.0

#: Speech is also sustained. A single knock or click is loud and brief, so it
#: passes the spread test; requiring a share of frames near the recording's own
#: peak rules it out.
MIN_VOICED_FRACTION = 0.08

#: A frame counts as voiced at this fraction of the recording's loudest frame.
#: Relative, so it means the same thing at any recording level.
VOICED_RELATIVE_TO_PEAK = 0.15

#: Kept for callers that referenced it. No longer a gate criterion: an
#: absolute loudness floor is exactly what misclassified quiet children.
MIN_RMS = 0.0008

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
    #: Spread between the loud and quiet frames. The speech test.
    dynamic_range: float = 0.0
    #: Energy of the loudest part, however quiet the recording overall.
    peak_frame_rms: float = 0.0

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

    # Frame energies. Everything below is a shape test on these, not a
    # loudness test, so a quiet child reads the same as a loud one.
    window = max(1, int(rate * _FRAME_SECONDS))
    frame_rms = [
        _rms(samples[start:start + window]) / full_scale
        for start in range(0, len(samples) - window + 1, window)
    ]

    if not frame_rms:
        return AudioCheck(ok=False, reason="too_short",
                          duration_seconds=round(duration, 3))

    ordered = sorted(frame_rms)
    quiet = ordered[int(len(ordered) * 0.10)]
    loud = ordered[int(len(ordered) * 0.90)]

    dynamic_range = round(loud / quiet, 2) if quiet > 1e-9 else float("inf")
    voiced_cut = loud * VOICED_RELATIVE_TO_PEAK
    voiced_fraction = round(
        sum(1 for f in frame_rms if f >= voiced_cut) / len(frame_rms), 4
    )

    measured = {
        "duration_seconds": round(duration, 3),
        "rms": round(rms, 5),
        "voiced_fraction": voiced_fraction,
        "peak": round(peak, 5),
        "dynamic_range": dynamic_range,
        "peak_frame_rms": round(loud, 6),
    }

    if duration < MIN_DURATION_SECONDS:
        return AudioCheck(ok=False, reason="too_short", **measured)
    if loud < MIN_PEAK_RMS:
        return AudioCheck(ok=False, reason="silent", **measured)
    if dynamic_range < MIN_DYNAMIC_RANGE:
        return AudioCheck(ok=False, reason="no_speech_detected", **measured)
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
