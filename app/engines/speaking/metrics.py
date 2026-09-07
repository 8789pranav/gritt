"""Stage 4 of the signal chain: everything derived in our own code.

Azure returns word and phoneme offsets in 100-nanosecond ticks. Every timing
measure below is counted from those offsets rather than estimated by a model,
which is the difference between "the model said there were two pauses" and
"there were two pauses".

The phonics mapping is the piece that connects speaking to Word Wizard: Azure
reports per-phoneme accuracy in IPA, and Word Wizard already classifies
spelling errors against a phonics taxonomy. Scoring the same features from
both tests lets one difficulty corroborate itself across two domains.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.infrastructure.azure_pronunciation import PronunciationResult, Word

#: A gap between words longer than this is a pause a listener would notice.
PAUSE_MS = 150.0

#: A pause this long breaks the phrase.
LONG_PAUSE_MS = 500.0

#: Words per minute a fluent reader reaches, by grade. Used to describe the
#: reading rate, never to fail a child for being outside the band.
GRADE_WCPM_BANDS: Dict[str, tuple] = {
    "Kindergarten": (10, 40),
    "First": (25, 70),
    "Second": (55, 100),
    "Third": (75, 120),
}
DEFAULT_WCPM_BAND = (25, 100)

#: Filler tokens. Kept explicit rather than regex-guessed so the list can be
#: reviewed, and so "um" inside a word is never matched.
FILLERS = frozenset({
    "um", "umm", "ummm", "uh", "uhh", "uhm", "er", "err", "erm",
    "ah", "ahh", "eh", "hm", "hmm", "hmmm", "mm", "mmm", "like",
})

#: Fillers that are also ordinary words. Only counted when they sit outside
#: the reference sentence, so "I like it" never reads as hesitation.
AMBIGUOUS_FILLERS = frozenset({"like", "ah", "mm"})


# ---------------------------------------------------------------------------
# phonics
# ---------------------------------------------------------------------------
#: IPA vowels grouped into the categories Word Wizard already uses.
SHORT_VOWELS = frozenset({"æ", "ɛ", "ɪ", "ɒ", "ɑ", "ʌ", "ʊ", "ə"})
LONG_VOWELS = frozenset({"eɪ", "iː", "i", "aɪ", "oʊ", "uː", "u", "ɔː", "ɜː", "ɑː"})
OTHER_VOWEL_PATTERNS = frozenset({"aʊ", "ɔɪ", "ɪə", "ɛə", "ʊə", "ɝ", "ɚ", "ɐ"})

#: Single IPA symbols that English spells with two letters.
DIGRAPHS = frozenset({"ʃ", "tʃ", "θ", "ð", "ʒ", "dʒ", "ŋ"})

CONSONANTS = frozenset({
    "p", "b", "t", "d", "k", "g", "f", "v", "s", "z", "h",
    "m", "n", "l", "r", "w", "j", "ɹ", "ɫ",
})

PHONICS_FEATURES = (
    "beginning_consonant",
    "ending_consonant",
    "short_vowel",
    "long_vowel",
    "other_vowel_pattern",
    "consonant_digraph",
    "consonant_blend",
)


def classify_phoneme(ipa: str, position: int, total: int) -> List[str]:
    """Which phonics features does this phoneme carry?

    A phoneme can belong to more than one: the /ʃ/ in "shop" is both a digraph
    and the beginning consonant.
    """
    symbol = (ipa or "").strip().lower()
    if not symbol:
        return []

    features: List[str] = []
    is_first = position == 0
    is_last = position == total - 1

    if symbol in DIGRAPHS:
        features.append("consonant_digraph")

    if symbol in SHORT_VOWELS:
        features.append("short_vowel")
    elif symbol in LONG_VOWELS:
        features.append("long_vowel")
    elif symbol in OTHER_VOWEL_PATTERNS:
        features.append("other_vowel_pattern")
    else:
        if is_first:
            features.append("beginning_consonant")
        if is_last:
            features.append("ending_consonant")

    return features


def _is_consonant(ipa: str) -> bool:
    symbol = (ipa or "").strip().lower()
    return bool(symbol) and (symbol in CONSONANTS or symbol in DIGRAPHS)


def phonics_scores(words: Sequence[Word]) -> Dict[str, Optional[float]]:
    """Mean Azure accuracy per phonics feature across every word spoken.

    Returns None for a feature the sentence set never exercised, so an absent
    feature is never reported as a weakness - the same rule the other three
    domains now follow.
    """
    totals: Dict[str, List[float]] = {name: [] for name in PHONICS_FEATURES}

    for word in words:
        if not word.was_spoken or not word.phonemes:
            continue
        count = len(word.phonemes)
        for index, phoneme in enumerate(word.phonemes):
            for feature in classify_phoneme(phoneme.ipa, index, count):
                totals[feature].append(phoneme.accuracy)

        # A blend is two consonants running together with no vowel between.
        for index in range(count - 1):
            if _is_consonant(word.phonemes[index].ipa) and _is_consonant(
                word.phonemes[index + 1].ipa
            ):
                totals["consonant_blend"].extend([
                    word.phonemes[index].accuracy,
                    word.phonemes[index + 1].accuracy,
                ])

    return {
        name: round(sum(values) / len(values), 1) if values else None
        for name, values in totals.items()
    }


# ---------------------------------------------------------------------------
# timing
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TimingMetrics:
    time_to_first_word_ms: float
    pause_count: int
    long_pause_count: int
    mean_pause_ms: float
    longest_pause_ms: float
    total_pause_ms: float
    speaking_span_ms: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "time_to_first_word_ms": self.time_to_first_word_ms,
            "pause_count": self.pause_count,
            "long_pause_count": self.long_pause_count,
            "mean_pause_ms": self.mean_pause_ms,
            "longest_pause_ms": self.longest_pause_ms,
            "total_pause_ms": self.total_pause_ms,
            "speaking_span_ms": self.speaking_span_ms,
        }


def timing_metrics(words: Sequence[Word]) -> TimingMetrics:
    """Pauses counted from the gaps between consecutive spoken words."""
    spoken = [w for w in words if w.was_spoken and w.duration_ms > 0]
    if not spoken:
        return TimingMetrics(0.0, 0, 0, 0.0, 0.0, 0.0, 0.0)

    gaps: List[float] = []
    for previous, current in zip(spoken, spoken[1:]):
        gap = current.offset_ms - previous.end_ms
        if gap > PAUSE_MS:
            gaps.append(round(gap, 1))

    span = round(spoken[-1].end_ms - spoken[0].offset_ms, 1)
    return TimingMetrics(
        time_to_first_word_ms=round(spoken[0].offset_ms, 1),
        pause_count=len(gaps),
        long_pause_count=sum(1 for g in gaps if g > LONG_PAUSE_MS),
        mean_pause_ms=round(sum(gaps) / len(gaps), 1) if gaps else 0.0,
        longest_pause_ms=max(gaps) if gaps else 0.0,
        total_pause_ms=round(sum(gaps), 1),
        speaking_span_ms=span,
    )


# ---------------------------------------------------------------------------
# reading rate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReadingMetrics:
    correct_words: int
    total_words: int
    accuracy_pct: float
    wcpm: float
    elapsed_seconds: float
    rate_band: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "correct_words": self.correct_words,
            "total_words": self.total_words,
            "accuracy_pct": self.accuracy_pct,
            "wcpm": self.wcpm,
            "elapsed_seconds": self.elapsed_seconds,
            "rate_band": self.rate_band,
        }


def reading_metrics(
    words: Sequence[Word],
    grade: str,
    elapsed_ms: Optional[float] = None,
) -> ReadingMetrics:
    """Words correct per minute, the standard oral reading fluency measure.

    A teacher already knows how to read WCPM, which is why it belongs in the
    report ahead of any score we invent.
    """
    total = len([w for w in words if w.word])
    correct = len([w for w in words if w.is_correct])

    if elapsed_ms is None:
        spoken = [w for w in words if w.was_spoken and w.duration_ms > 0]
        elapsed_ms = (spoken[-1].end_ms - spoken[0].offset_ms) if spoken else 0.0

    seconds = round(elapsed_ms / 1000.0, 2)
    wcpm = round(correct / (seconds / 60.0), 1) if seconds > 0 else 0.0

    low, high = GRADE_WCPM_BANDS.get(grade, DEFAULT_WCPM_BAND)
    if wcpm <= 0:
        band = "no_reading"
    elif wcpm < low:
        band = "below_band"
    elif wcpm > high:
        band = "above_band"
    else:
        band = "in_band"

    return ReadingMetrics(
        correct_words=correct,
        total_words=total,
        accuracy_pct=round(correct / total * 100, 1) if total else 0.0,
        wcpm=wcpm,
        elapsed_seconds=seconds,
        rate_band=band,
    )


# ---------------------------------------------------------------------------
# disfluency
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DisfluencyMetrics:
    fillers: List[str]
    filler_count: int
    filler_rate_per_100w: float
    repetitions: int
    repeated_words: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "fillers": self.fillers,
            "filler_count": self.filler_count,
            "filler_rate_per_100w": self.filler_rate_per_100w,
            "repetitions": self.repetitions,
            "repeated_words": self.repeated_words,
        }


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z']+", (text or "").lower())


def disfluency_metrics(verbatim_text: str, reference_text: str) -> DisfluencyMetrics:
    """Fillers and repetitions, from the blind verbatim transcript.

    Azure's recogniser normalises "um" and "uh" away - it is built to hear the
    sentence - so this reads the verbatim channel instead. Tokens that are
    also ordinary words are only counted when the reference sentence does not
    contain them, so "I like it" is never scored as hesitation.
    """
    spoken = _tokens(verbatim_text)
    reference = set(_tokens(reference_text))

    fillers = [
        token for token in spoken
        if token in FILLERS
        and not (token in AMBIGUOUS_FILLERS and token in reference)
    ]

    repeated: List[str] = []
    for previous, current in zip(spoken, spoken[1:]):
        if previous == current and previous not in FILLERS and len(previous) > 1:
            repeated.append(current)

    content = [t for t in spoken if t not in FILLERS]
    per_100 = round(len(fillers) / len(content) * 100, 1) if content else 0.0

    return DisfluencyMetrics(
        fillers=fillers,
        filler_count=len(fillers),
        filler_rate_per_100w=per_100,
        repetitions=len(repeated),
        repeated_words=repeated,
    )


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def error_counts(words: Sequence[Word]) -> Dict[str, int]:
    counts = {
        "omission": 0, "insertion": 0, "mispronunciation": 0,
        "unexpected_break": 0, "missing_break": 0, "monotone": 0,
    }
    lookup = {
        "Omission": "omission",
        "Insertion": "insertion",
        "Mispronunciation": "mispronunciation",
        "UnexpectedBreak": "unexpected_break",
        "MissingBreak": "missing_break",
        "Monotone": "monotone",
    }
    for word in words:
        key = lookup.get(word.error_type)
        if key:
            counts[key] += 1
    return counts


def build_sentence_metrics(
    result: PronunciationResult,
    reference_text: str,
    grade: str,
    verbatim_text: str = "",
    time_to_speak_ms: Optional[float] = None,
) -> Dict[str, Any]:
    """The full per-sentence measurement set the report and tags read."""
    timing = timing_metrics(result.words)
    reading = reading_metrics(result.words, grade)
    disfluency = disfluency_metrics(verbatim_text, reference_text)

    timing_dict = timing.as_dict()
    if time_to_speak_ms is not None:
        timing_dict["time_to_speak_ms"] = round(float(time_to_speak_ms), 1)

    return {
        "reference": reference_text,
        "recognized": result.recognized_text,
        "verbatim": verbatim_text,
        "scores": {
            "accuracy": result.accuracy,
            "fluency": result.fluency,
            "completeness": result.completeness,
            "prosody": result.prosody,
            "pron_score": result.pron_score,
        },
        "reading": reading.as_dict(),
        "timing": timing_dict,
        "disfluency": disfluency.as_dict(),
        "phonics": phonics_scores(result.words),
        "errors": error_counts(result.words),
        "words": [
            {
                "word": w.word,
                "accuracy": w.accuracy,
                "error_type": w.error_type,
                "offset_ms": w.offset_ms,
                "duration_ms": w.duration_ms,
                "phonemes": [
                    {"ipa": p.ipa, "accuracy": p.accuracy} for p in w.phonemes
                ],
            }
            for w in result.words
        ],
    }


def empty_sentence_metrics(
    reference_text: str,
    reason: str,
    message: str,
) -> Dict[str, Any]:
    """A sentence with no speech. Zero everywhere, nothing echoed back."""
    return {
        "reference": reference_text,
        "recognized": "",
        "verbatim": "",
        "status": "not_attempted",
        "reason": reason,
        "message": message,
        "scores": {
            "accuracy": 0.0, "fluency": 0.0, "completeness": 0.0,
            "prosody": 0.0, "pron_score": 0.0,
        },
        "reading": ReadingMetrics(0, len(reference_text.split()), 0.0, 0.0, 0.0,
                                  "no_reading").as_dict(),
        "timing": TimingMetrics(0.0, 0, 0, 0.0, 0.0, 0.0, 0.0).as_dict(),
        "disfluency": DisfluencyMetrics([], 0, 0.0, 0, []).as_dict(),
        "phonics": {name: None for name in PHONICS_FEATURES},
        "errors": error_counts([]),
        "words": [],
    }
