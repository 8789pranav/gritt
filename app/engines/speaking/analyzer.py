"""
Speech analysis abstraction.

The speaking assessment needs two capabilities that live outside the process:
transcription and qualitative analysis. Both are expressed here as protocols
so the engine depends on the *capability*, not on OpenAI. Tests can supply a
stub, and swapping providers means adding one class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class WordTiming:
    """Start and end offsets for a single spoken word."""

    word: str
    start: float
    end: float

    def to_dict(self) -> Dict[str, Any]:
        return {"word": self.word, "start": self.start, "end": self.end}


@dataclass
class Transcription:
    """Result of converting an audio clip to text."""

    text: str
    duration_seconds: float = 0.0
    word_timings: List[WordTiming] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def words_per_minute(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return round(self.word_count / self.duration_seconds * 60, 1)


@dataclass
class DimensionScore:
    """A single scored dimension of a spoken response."""

    score: float = 0.0
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def normalised(self) -> float:
        """Score expressed as a 0.0-1.0 ratio.

        Providers report on a 0-100 scale but the tag triggers are written
        against ratios, so the conversion happens once, here.
        """
        return round(max(0.0, min(self.score, 100.0)) / 100, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {"score": self.score, **self.detail}


@dataclass
class SpeechAnalysis:
    """Full qualitative analysis of one spoken sentence."""

    pronunciation: DimensionScore = field(default_factory=DimensionScore)
    fluency: DimensionScore = field(default_factory=DimensionScore)
    prosody: DimensionScore = field(default_factory=DimensionScore)
    grammar: DimensionScore = field(default_factory=DimensionScore)
    speaking_rate: DimensionScore = field(default_factory=DimensionScore)

    overall_score: float = 0.0
    level: str = ""
    recommendation: str = ""
    parent_tip: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pronunciation": self.pronunciation.to_dict(),
            "fluency": self.fluency.to_dict(),
            "prosody": self.prosody.to_dict(),
            "grammar": self.grammar.to_dict(),
            "speaking_rate": self.speaking_rate.to_dict(),
            "overall": {
                "score": self.overall_score,
                "level": self.level,
                "recommendation": self.recommendation,
                "parent_tip": self.parent_tip,
            },
        }

    @classmethod
    def from_provider_payload(cls, payload: Dict[str, Any]) -> "SpeechAnalysis":
        """Build an analysis from a provider's raw JSON response."""

        def dimension(key: str) -> DimensionScore:
            raw = payload.get(key) or {}
            if not isinstance(raw, dict):
                return DimensionScore()
            score = raw.get("score", 0)
            detail = {k: v for k, v in raw.items() if k != "score"}
            try:
                return DimensionScore(score=float(score), detail=detail)
            except (TypeError, ValueError):
                return DimensionScore(detail=detail)

        overall = payload.get("overall") or {}
        try:
            overall_score = float(overall.get("score", 0))
        except (TypeError, ValueError):
            overall_score = 0.0

        return cls(
            pronunciation=dimension("pronunciation"),
            fluency=dimension("fluency"),
            prosody=dimension("prosody"),
            grammar=dimension("grammar"),
            speaking_rate=dimension("speaking_rate"),
            overall_score=overall_score,
            level=str(overall.get("level", "")),
            recommendation=str(overall.get("recommendation", "")),
            parent_tip=str(overall.get("parent_tip", "")),
        )


@runtime_checkable
class Transcriber(Protocol):
    """Converts recorded audio into text with word-level timings."""

    async def transcribe(
        self,
        audio_base64: str,
        *,
        audio_format: str = "mp3",
    ) -> Transcription:
        """Transcribe a base64-encoded audio clip."""
        ...


@runtime_checkable
class SpeechAnalyzer(Protocol):
    """Scores a transcription against the sentence the child was asked to read."""

    async def analyze(
        self,
        *,
        original_sentence: str,
        transcription: Transcription,
        grade: str,
    ) -> SpeechAnalysis:
        """Produce a qualitative analysis of one spoken response."""
        ...


class NullTranscriber:
    """No-op transcriber used when no provider is configured."""

    async def transcribe(
        self,
        audio_base64: str,
        *,
        audio_format: str = "mp3",
    ) -> Transcription:
        return Transcription(text="")


class NullSpeechAnalyzer:
    """No-op analyzer used when no provider is configured."""

    async def analyze(
        self,
        *,
        original_sentence: str,
        transcription: Transcription,
        grade: str,
    ) -> SpeechAnalysis:
        return SpeechAnalysis()
