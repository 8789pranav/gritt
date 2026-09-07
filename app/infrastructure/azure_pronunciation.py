"""Azure Pronunciation Assessment over the REST short-audio API.

Stage 2 of the Voice Challenge signal chain: the scoring spine.

REST rather than the Speech SDK, deliberately:

* The SDK needs native audio libraries that complicate a slim container image.
  This module needs nothing that is not already in requirements.txt.
* Authentication is a subscription key and a region, which is all we have.
* Every Voice Challenge sentence is 5-10 words, so each recording is far below
  the 30-second ceiling on the short-audio endpoint. That ceiling is also what
  makes ``EnableMiscue`` available: it is unsupported in continuous mode, and
  it is the feature that reports omissions and insertions per word.

The service returns accuracy at four levels (phoneme, syllable, word, text),
plus fluency, completeness and prosody, and word offsets in 100-nanosecond
ticks. Everything in :mod:`app.engines.speaking.metrics` is derived from those
offsets rather than estimated by a model.
"""

from __future__ import annotations

import array
import base64
import binascii
import io
import json
import logging
import os
import sys
import wave
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: Azure expresses every offset and duration in 100-nanosecond ticks.
TICKS_PER_SECOND = 10_000_000
TICKS_PER_MS = 10_000

#: The short-audio endpoint refuses anything longer than this.
MAX_AUDIO_SECONDS = 30.0

#: Azure wants 16 kHz mono 16-bit PCM for the samplerate we declare.
TARGET_RATE = 16000

#: Prosody and syllable-level output are en-US only.
DEFAULT_LOCALE = "en-US"

_BIG_ENDIAN = sys.byteorder == "big"


class AzureNotConfigured(RuntimeError):
    """Raised when the key or region is missing."""


@dataclass(frozen=True)
class SpokenPhoneme:
    """A sound the child may actually have produced, and how likely it is."""

    ipa: str
    score: float


@dataclass(frozen=True)
class Phoneme:
    #: The sound the reference word expects here.
    ipa: str
    accuracy: float
    offset_ms: float
    duration_ms: float
    #: What Azure believes was actually produced, most likely first. This is
    #: the channel that survives transcription: the recognised text reads
    #: "dog" whatever the child said, but a child who said "dot" shows /t/
    #: here where /g/ was expected.
    spoken: List[SpokenPhoneme] = field(default_factory=list)

    @property
    def actually_said(self) -> str:
        """The most likely sound produced, falling back to the expected one."""
        return self.spoken[0].ipa if self.spoken else self.ipa

    @property
    def is_substitution(self) -> bool:
        """A different sound was produced from the one the word needs."""
        return bool(self.spoken) and self.spoken[0].ipa != self.ipa


@dataclass(frozen=True)
class Syllable:
    syllable: str
    grapheme: str
    accuracy: float
    offset_ms: float
    duration_ms: float


@dataclass(frozen=True)
class Word:
    word: str
    accuracy: float
    error_type: str
    offset_ms: float
    duration_ms: float
    phonemes: List[Phoneme] = field(default_factory=list)
    syllables: List[Syllable] = field(default_factory=list)
    #: Per-word prosody feedback. The REST response carries confidences here
    #: rather than a decided error type, so the thresholds are ours.
    unexpected_break_confidence: float = 0.0
    missing_break_confidence: float = 0.0
    monotone_confidence: float = 0.0
    break_length_ms: float = 0.0

    @property
    def end_ms(self) -> float:
        return self.offset_ms + self.duration_ms

    @property
    def is_correct(self) -> bool:
        return self.error_type == "None"

    @property
    def was_spoken(self) -> bool:
        """Omitted words are in the result but were never said."""
        return self.error_type != "Omission"

    @property
    def expected_ipa(self) -> str:
        """The sounds the reference word needs."""
        return "".join(p.ipa for p in self.phonemes)

    @property
    def spoken_ipa(self) -> str:
        """The sounds the child actually produced.

        This is the closest thing to a verbatim record of a mispronunciation.
        No transcriber gives it: both Azure and Whisper spell real words, so
        "dot" for "dog" reads back as "dog" in every text field.
        """
        return "".join(p.actually_said for p in self.phonemes)

    @property
    def substituted_sounds(self) -> List[Phoneme]:
        return [p for p in self.phonemes if p.is_substitution]


@dataclass(frozen=True)
class PronunciationResult:
    """One scored sentence."""

    recognized_text: str
    accuracy: float
    fluency: float
    completeness: float
    prosody: Optional[float]
    pron_score: float
    words: List[Word] = field(default_factory=list)
    #: Signal-to-noise ratio, reported by the service. A low value means a
    #: noisy room, which is worth knowing before trusting a low score.
    snr: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def spoken_words(self) -> List[Word]:
        return [w for w in self.words if w.was_spoken]

    @property
    def correct_words(self) -> List[Word]:
        return [w for w in self.words if w.is_correct]

    def words_with_error(self, error_type: str) -> List[Word]:
        return [w for w in self.words if w.error_type == error_type]


# ---------------------------------------------------------------------------
# audio normalisation
# ---------------------------------------------------------------------------
def _read_wav(raw: bytes):
    with wave.open(io.BytesIO(raw), "rb") as handle:
        return (
            handle.readframes(handle.getnframes()),
            handle.getsampwidth(),
            handle.getnchannels(),
            handle.getframerate(),
        )


def _resample(samples: array.array, source_rate: int, target_rate: int) -> array.array:
    """Linear resample. Adequate for speech at these rates, and dependency-free."""
    if source_rate == target_rate or not samples:
        return samples
    ratio = target_rate / float(source_rate)
    out = array.array("h", bytes(2 * max(1, int(len(samples) * ratio))))
    for i in range(len(out)):
        position = i / ratio
        left = int(position)
        right = min(left + 1, len(samples) - 1)
        weight = position - left
        out[i] = int(samples[left] * (1 - weight) + samples[right] * weight)
    return out


def to_azure_wav(audio_base64: str) -> bytes:
    """Normalise a base64 WAV to 16 kHz mono 16-bit PCM.

    Browsers record at the device rate, commonly 44.1 or 48 kHz, and often in
    stereo. Azure is told the sample rate in the Content-Type header, so the
    audio has to actually be at that rate.
    """
    try:
        raw = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio is not valid base64") from exc

    frames, width, channels, rate = _read_wav(raw)
    if width != 2:
        raise ValueError(f"expected 16-bit PCM, got {width * 8}-bit")

    samples = array.array("h")
    samples.frombytes(frames[: len(frames) - (len(frames) % 2)])
    if _BIG_ENDIAN:
        samples.byteswap()

    if channels > 1:
        samples = array.array("h", samples[::channels])

    samples = _resample(samples, rate, TARGET_RATE)

    if _BIG_ENDIAN:
        samples = array.array("h", samples)
        samples.byteswap()

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(TARGET_RATE)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------
class AzurePronunciationClient:
    """Scripted pronunciation assessment for one short utterance."""

    def __init__(
        self,
        key: Optional[str] = None,
        region: Optional[str] = None,
        locale: str = DEFAULT_LOCALE,
        timeout: float = 25.0,
        nbest_phoneme_count: int = 5,
    ) -> None:
        self.key = key if key is not None else os.getenv("AZURE_SPEECH_KEY", "")
        self.region = region if region is not None else os.getenv("AZURE_SPEECH_REGION", "")
        self.locale = locale
        self.timeout = timeout
        self.nbest_phoneme_count = nbest_phoneme_count

    @property
    def is_configured(self) -> bool:
        return bool(self.key and self.region)

    @property
    def endpoint(self) -> str:
        return (
            f"https://{self.region}.stt.speech.microsoft.com"
            f"/speech/recognition/conversation/cognitiveservices/v1"
        )

    def build_config_header(self, reference_text: str, enable_miscue: bool = True) -> str:
        """The Pronunciation-Assessment header is base64-encoded JSON."""
        config = {
            "ReferenceText": reference_text,
            "GradingSystem": "HundredMark",
            "Granularity": "Phoneme",
            "Dimension": "Comprehensive",
            "EnableMiscue": enable_miscue,
            "EnableProsodyAssessment": True,
            "PhonemeAlphabet": "IPA",
            # The phonemes the child ACTUALLY produced, ranked by likelihood,
            # rather than only a score against the expected one. This is the
            # channel that survives transcription: the recognised text says
            # "dog" whatever the child said, but the spoken phoneme for the
            # final sound tells you they produced something else.
            "NBestPhonemeCount": self.nbest_phoneme_count,
        }
        payload = json.dumps(config, ensure_ascii=False)
        return base64.b64encode(payload.encode("utf-8")).decode("utf-8")

    def build_headers(self, reference_text: str, enable_miscue: bool = True) -> Dict[str, str]:
        return {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": f"audio/wav; codecs=audio/pcm; samplerate={TARGET_RATE}",
            "Accept": "application/json",
            "Pronunciation-Assessment": self.build_config_header(
                reference_text, enable_miscue
            ),
        }

    @property
    def params(self) -> Dict[str, str]:
        return {"language": self.locale, "format": "detailed"}

    async def assess(
        self,
        audio_base64: str,
        reference_text: str,
        enable_miscue: bool = True,
    ) -> PronunciationResult:
        """Score one recording against its reference sentence."""
        if not self.is_configured:
            raise AzureNotConfigured(
                "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must both be set"
            )

        wav_bytes = to_azure_wav(audio_base64)
        seconds = (len(wav_bytes) - 44) / float(TARGET_RATE * 2)
        if seconds > MAX_AUDIO_SECONDS:
            raise ValueError(
                f"recording is {seconds:.1f}s; the short-audio endpoint accepts "
                f"{MAX_AUDIO_SECONDS:.0f}s"
            )

        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.endpoint,
                params=self.params,
                headers=self.build_headers(reference_text, enable_miscue),
                content=wav_bytes,
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Azure returned {response.status_code}: {response.text[:300]}"
            )
        return parse_result(response.json())


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
def _ticks_to_ms(ticks: Any) -> float:
    try:
        return round(float(ticks) / TICKS_PER_MS, 1)
    except (TypeError, ValueError):
        return 0.0


def _scores(node: Dict[str, Any]) -> Dict[str, Any]:
    """Read assessment scores from either response shape.

    The Speech SDK nests them under "PronunciationAssessment". The REST
    short-audio endpoint returns them flat on the same object, with
    "PronunciationAssessment" present but null. Confirmed against the live
    service - the documentation shows the SDK shape only.
    """
    nested = node.get("PronunciationAssessment")
    return nested if isinstance(nested, dict) and nested else node


def _number(node: Dict[str, Any], key: str, default: Optional[float] = None):
    value = _scores(node).get(key, default)
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _break_feedback(entry: Dict[str, Any]) -> Dict[str, float]:
    """Prosody confidences for one word, where the response provides them."""
    prosody = ((entry.get("Feedback") or {}).get("Prosody") or {})
    brk = prosody.get("Break") or {}
    intonation = prosody.get("Intonation") or {}

    def confidence(node: Any) -> float:
        if isinstance(node, dict):
            try:
                return float(node.get("Confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    try:
        break_length = float(brk.get("BreakLength", 0) or 0)
    except (TypeError, ValueError):
        break_length = 0.0

    return {
        "unexpected_break_confidence": confidence(brk.get("UnexpectedBreak")),
        "missing_break_confidence": confidence(brk.get("MissingBreak")),
        "monotone_confidence": confidence(intonation.get("Monotone")),
        "break_length_ms": _ticks_to_ms(break_length),
    }


def parse_result(payload: Dict[str, Any]) -> PronunciationResult:
    """Turn Azure's detailed JSON into our own shape.

    Tolerates both the flat REST response and the nested SDK one, so the same
    parser serves either transport. Kept separate from the HTTP call so it can
    be unit-tested against recorded fixtures without a key or a network.
    """
    if payload.get("RecognitionStatus") not in (None, "Success"):
        return PronunciationResult(
            recognized_text="", accuracy=0.0, fluency=0.0, completeness=0.0,
            prosody=None, pron_score=0.0, words=[], raw=payload,
        )

    best = (payload.get("NBest") or [{}])[0]

    words: List[Word] = []
    for entry in best.get("Words", []) or []:
        phonemes = []
        for p in (entry.get("Phonemes") or []):
            candidates = (
                _scores(p).get("NBestPhonemes")
                or p.get("NBestPhonemes")
                or []
            )
            phonemes.append(Phoneme(
                ipa=p.get("Phoneme", ""),
                accuracy=_number(p, "AccuracyScore", 0.0) or 0.0,
                offset_ms=_ticks_to_ms(p.get("Offset")),
                duration_ms=_ticks_to_ms(p.get("Duration")),
                spoken=[
                    SpokenPhoneme(
                        ipa=c.get("Phoneme", ""),
                        score=float(c.get("Score", 0.0) or 0.0),
                    )
                    for c in candidates if c.get("Phoneme")
                ],
            ))
        syllables = [
            Syllable(
                syllable=y.get("Syllable", ""),
                grapheme=y.get("Grapheme", ""),
                accuracy=_number(y, "AccuracyScore", 0.0) or 0.0,
                offset_ms=_ticks_to_ms(y.get("Offset")),
                duration_ms=_ticks_to_ms(y.get("Duration")),
            )
            for y in (entry.get("Syllables") or [])
        ]
        words.append(
            Word(
                word=entry.get("Word", ""),
                accuracy=_number(entry, "AccuracyScore", 0.0) or 0.0,
                error_type=_scores(entry).get("ErrorType", "None") or "None",
                offset_ms=_ticks_to_ms(entry.get("Offset")),
                duration_ms=_ticks_to_ms(entry.get("Duration")),
                phonemes=phonemes,
                syllables=syllables,
                **_break_feedback(entry),
            )
        )

    snr = payload.get("SNR")
    try:
        snr = float(snr) if snr is not None else None
    except (TypeError, ValueError):
        snr = None

    return PronunciationResult(
        recognized_text=(
            best.get("Display") or best.get("Lexical")
            or payload.get("DisplayText") or ""
        ),
        accuracy=_number(best, "AccuracyScore", 0.0) or 0.0,
        fluency=_number(best, "FluencyScore", 0.0) or 0.0,
        completeness=_number(best, "CompletenessScore", 0.0) or 0.0,
        prosody=_number(best, "ProsodyScore", None),
        pron_score=_number(best, "PronScore", 0.0) or 0.0,
        words=words,
        snr=snr,
        raw=payload,
    )


def pron_score(
    accuracy: float,
    fluency: float,
    completeness: Optional[float] = None,
    prosody: Optional[float] = None,
) -> float:
    """Azure's own reading-scenario weighting, reimplemented.

    Sorting the available dimensions low to high as s0..s3, the weakest
    dimension carries the most weight. A reader who is accurate but flat
    cannot hide behind accuracy, which is the right behaviour for a
    diagnostic. Used when we need the score without a round trip, and to
    verify that what Azure returns is what we expect.
    """
    scores = [s for s in (accuracy, fluency, completeness, prosody) if s is not None]
    scores.sort()
    if len(scores) >= 4:
        weights = [0.4, 0.2, 0.2, 0.2]
    elif len(scores) == 3:
        weights = [0.6, 0.2, 0.2]
    elif len(scores) == 2:
        weights = [0.6, 0.4]
    else:
        return round(scores[0], 1) if scores else 0.0
    return round(sum(s * w for s, w in zip(scores, weights)), 1)
