"""
Domain enumerations shared by every assessment engine.

This module is deliberately dependency-free (standard library only) so that it
can be imported from any layer without pulling in FastAPI, Firebase or
OpenAI.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional


class TestType(str, Enum):
    """The four assessment domains offered by the platform."""

    LOGIC = "logic"
    SPELLING = "spelling"
    SPEAKING = "speaking"
    COMPREHENSION = "comprehension"

    @property
    def display_name(self) -> str:
        return _TEST_DISPLAY_NAMES[self]

    @property
    def storage_key(self) -> str:
        """Firebase child node under which results for this test are stored."""
        return _TEST_STORAGE_KEYS[self]

    @property
    def audio_namespace(self) -> str:
        """Firebase child node under which cached narration is stored."""
        return _TEST_AUDIO_NAMESPACES[self]


_TEST_DISPLAY_NAMES: Dict[TestType, str] = {
    TestType.LOGIC: "Logic Quest",
    TestType.SPELLING: "Word Wizard",
    TestType.SPEAKING: "Voice Challenge",
    TestType.COMPREHENSION: "Story Explorer",
}

# Preserved from the legacy schema so existing stored results stay readable.
_TEST_STORAGE_KEYS: Dict[TestType, str] = {
    TestType.LOGIC: "logic_tests",
    TestType.SPELLING: "scores",
    TestType.SPEAKING: "speaking_tests",
    TestType.COMPREHENSION: "comprehension_tests",
}

_TEST_AUDIO_NAMESPACES: Dict[TestType, str] = {
    TestType.LOGIC: "logic_audio",
    TestType.SPELLING: "spelling_audio",
    TestType.SPEAKING: "speaking_audio",
    TestType.COMPREHENSION: "story_audio",
}


class Grade(str, Enum):
    """Canonical grade identifiers.

    The public API historically accepted two spellings for each grade
    (``"Kindergarten"`` and ``"K-1"``). :meth:`parse` normalises both.
    """

    KINDERGARTEN = "Kindergarten"
    FIRST = "First"
    SECOND = "Second"
    THIRD = "Third"

    @property
    def band(self) -> str:
        """The two-year band label used by the Logic Quest item bank."""
        return _GRADE_BANDS[self]

    @property
    def file_stem(self) -> str:
        """Filename stem under ``data/questions/<test>/``."""
        return _GRADE_FILE_STEMS[self]

    @classmethod
    def parse(cls, value: str) -> "Grade":
        """Resolve any accepted grade spelling to a :class:`Grade`.

        Raises ``ValueError`` when the value is not recognised.
        """
        if isinstance(value, cls):
            return value

        key = str(value).strip().lower()
        resolved = _GRADE_ALIASES.get(key)
        if resolved is None:
            raise ValueError(f"Unrecognised grade: {value!r}")
        return resolved

    @classmethod
    def try_parse(cls, value: Optional[str]) -> Optional["Grade"]:
        """Like :meth:`parse` but returns ``None`` instead of raising."""
        if value is None:
            return None
        try:
            return cls.parse(value)
        except ValueError:
            return None

    @classmethod
    def values(cls) -> List[str]:
        return [grade.value for grade in cls]


_GRADE_BANDS: Dict[Grade, str] = {
    Grade.KINDERGARTEN: "K-1",
    Grade.FIRST: "1-2",
    Grade.SECOND: "2-3",
    Grade.THIRD: "3-4",
}

_GRADE_FILE_STEMS: Dict[Grade, str] = {
    Grade.KINDERGARTEN: "kindergarten",
    Grade.FIRST: "grade_1",
    Grade.SECOND: "grade_2",
    Grade.THIRD: "grade_3",
}

# Every accepted spelling, lower-cased, mapped to its canonical grade.
_GRADE_ALIASES: Dict[str, Grade] = {
    "kindergarten": Grade.KINDERGARTEN,
    "k": Grade.KINDERGARTEN,
    "k-1": Grade.KINDERGARTEN,
    "first": Grade.FIRST,
    "1": Grade.FIRST,
    "1st": Grade.FIRST,
    "1-2": Grade.FIRST,
    "second": Grade.SECOND,
    "2": Grade.SECOND,
    "2nd": Grade.SECOND,
    "2-3": Grade.SECOND,
    "third": Grade.THIRD,
    "3": Grade.THIRD,
    "3rd": Grade.THIRD,
    "3-4": Grade.THIRD,
}


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class WordType(str, Enum):
    """Category of a spelling item."""

    REGULAR = "regular"
    NONSENSE = "nonsense"
    SIGHT = "sight"


class QuestionType(str, Enum):
    """Comprehension question category, used for per-type accuracy signals."""

    LITERAL = "literal"
    INFERENTIAL = "inferential"
    VOCABULARY = "vocabulary"


class CognitiveTag(str, Enum):
    """Logic Quest cognitive domain tags."""

    PATTERN_DETECTION_STRONG = "pattern_detection_strong"
    PATTERN_DETECTION_EMERGING = "pattern_detection_emerging"
    RELATIONAL_REASONING_PRESENT = "relational_reasoning_present"
    SYSTEMATIC_PROBLEM_SOLVING = "systematic_problem_solving"
    COGNITIVE_FLEXIBILITY_INTACT = "cognitive_flexibility_intact"
    FLEXIBLE_STRATEGY_USE = "flexible_strategy_use"
    STRATEGY_SHIFT_DIFFICULTY = "strategy_shift_difficulty"
    REASONING_UNDER_LOAD_EMERGING = "reasoning_under_load_emerging"
    TRIAL_AND_ERROR_STRATEGY = "trial_and_error_strategy"
    IMPULSIVE_RESPONSE = "impulsive_response"
    SELF_CORRECTION_PRESENT = "self_correction_present"
    RULE_MAINTENANCE_DIFFICULTY = "rule_maintenance_difficulty"


class Confidence(str, Enum):
    """How strongly the evidence supports an emitted tag."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def weight(self) -> float:
        return _CONFIDENCE_WEIGHTS[self]


_CONFIDENCE_WEIGHTS: Dict[Confidence, float] = {
    Confidence.HIGH: 1.0,
    Confidence.MEDIUM: 0.6,
    Confidence.LOW: 0.3,
}


class Polarity(str, Enum):
    """Whether a tag describes a strength, a growth edge, or is neutral."""

    STRENGTH = "strength"
    GROWTH_EDGE = "growth_edge"
    NEUTRAL = "neutral"


class PerformanceLevel(str, Enum):
    """Placement band derived from an overall percentage."""

    ABOVE = "Above Grade Level"
    AT = "At Grade Level"
    BELOW = "Below Grade Level"

    @classmethod
    def from_percentage(cls, percentage: float) -> "PerformanceLevel":
        if percentage >= 90:
            return cls.ABOVE
        if percentage >= 75:
            return cls.AT
        return cls.BELOW


class ResponseStatus(str, Enum):
    """Outcome of a single submitted response."""

    ANSWERED = "Answered"
    NOT_ATTEMPTED = "Not Attempted"
    ERROR = "Error"
