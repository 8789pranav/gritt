"""
Core domain models.

These are plain Pydantic models describing assessment items, responses and
results. They contain no persistence, HTTP or vendor-SDK concerns, which lets
the engines be unit-tested without any infrastructure.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.domain.enums import (
    CognitiveTag,
    Confidence,
    Difficulty,
    Grade,
    Polarity,
    QuestionType,
    ResponseStatus,
    TestType,
    WordType,
)


def _new_id() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------
class Option(BaseModel):
    """A single answer choice."""

    index: int
    text: str
    image_url: Optional[str] = None


class TagOutput(BaseModel):
    """An emitted cognitive tag together with its supporting evidence."""

    tag: str
    confidence: Confidence
    polarity: Polarity
    description: str = ""
    evidence: str = ""

    @property
    def weight(self) -> float:
        return self.confidence.weight


class PerItemTags(BaseModel):
    """Tags attributed to one specific item within a test."""

    item_id: str
    answered: bool = True
    is_correct: Optional[bool] = None
    tags: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Assessment items - one model per test type
# ---------------------------------------------------------------------------
class AssessmentItem(BaseModel):
    """Common surface shared by every assessable item."""

    item_id: str
    grade: Grade
    test_type: TestType

    def identity(self) -> str:
        return self.item_id


class LogicItem(AssessmentItem):
    """A single Logic Quest question."""

    test_type: TestType = TestType.LOGIC

    item_number: str
    item_type: str
    question_text: str
    options: List[Option]
    correct_answer_index: int
    primary_tag: CognitiveTag
    conditional_tags: Dict[str, CognitiveTag] = Field(default_factory=dict)
    difficulty: Difficulty = Difficulty.MEDIUM
    expected_latency_seconds: int = 30

    def is_correct(self, selected_index: int) -> bool:
        return selected_index == self.correct_answer_index

    def correct_option(self) -> Optional[Option]:
        for option in self.options:
            if option.index == self.correct_answer_index:
                return option
        return None


class SpellingWord(AssessmentItem):
    """A single spelling target word."""

    test_type: TestType = TestType.SPELLING

    word: str
    word_type: WordType
    sentence: str = ""
    features: Dict[str, str] = Field(default_factory=dict)

    @property
    def max_points(self) -> int:
        """Regular words score one point per phonics feature; others score 1."""
        if self.word_type is WordType.REGULAR:
            return max(len(self.features), 1)
        return 1

    def identity(self) -> str:
        return self.word


class SpeakingSentence(AssessmentItem):
    """A sentence the child is asked to read aloud."""

    test_type: TestType = TestType.SPEAKING

    sentence_id: str
    sentence: str
    word_count: int = 0
    difficulty: Difficulty = Difficulty.MEDIUM

    def identity(self) -> str:
        return self.sentence_id


class ComprehensionQuestion(BaseModel):
    """A multiple-choice question attached to a story."""

    question_id: str
    question: str
    options: List[str]
    correct_index: int
    question_type: QuestionType = QuestionType.LITERAL

    def is_correct(self, selected_index: int) -> bool:
        return selected_index == self.correct_index

    def answer_text(self, index: int) -> str:
        if 0 <= index < len(self.options):
            return self.options[index]
        return "Invalid"


class ComprehensionStory(AssessmentItem):
    """A narrated story plus its comprehension questions."""

    test_type: TestType = TestType.COMPREHENSION

    story_id: str
    title: str
    story_text: str
    duration_estimate: str = "60 seconds"
    questions: List[ComprehensionQuestion] = Field(default_factory=list)

    def identity(self) -> str:
        return self.story_id

    @property
    def total_questions(self) -> int:
        return len(self.questions)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------
class ItemResponse(BaseModel):
    """Base class for a child's answer to a single item."""

    item_id: str
    response_time_seconds: float = 0.0
    attempts: int = 1
    self_corrected: bool = False


class LogicResponse(ItemResponse):
    """A response to one Logic Quest item."""

    selected_answer_index: int
    explanation_provided: Optional[str] = None
    post_shift_accuracy: Optional[str] = None
    rule_inferred: Optional[bool] = None


class SpellingResponse(ItemResponse):
    """A spelling attempt for one word."""

    word: str
    user_input: str
    word_type: WordType = WordType.REGULAR
    hints_used: int = 0


class SpeakingResponse(ItemResponse):
    """A recorded reading of one sentence."""

    sentence_id: str
    original_sentence: str
    audio_base64: Optional[str] = None
    audio_format: str = "mp3"


class ComprehensionResponse(ItemResponse):
    """An answer to one comprehension question."""

    question_id: str
    selected_index: int


# ---------------------------------------------------------------------------
# Scoring output
# ---------------------------------------------------------------------------
class ScoredItem(BaseModel):
    """Normalised per-item scoring outcome, uniform across all tests."""

    item_id: str
    label: str = ""
    is_correct: Optional[bool] = None
    points: float = 0.0
    max_points: float = 0.0
    status: ResponseStatus = ResponseStatus.ANSWERED
    detail: Dict[str, Any] = Field(default_factory=dict)

    @property
    def percentage(self) -> float:
        if self.max_points <= 0:
            return 0.0
        return round(self.points / self.max_points * 100, 1)


class TestScore(BaseModel):
    """Aggregate score for one completed test."""

    test_type: TestType
    grade: Grade
    total_items: int = 0
    answered_items: int = 0
    correct_answers: int = 0
    points: float = 0.0
    max_points: float = 0.0
    percentage: float = 0.0
    level: str = ""
    scored_items: List[ScoredItem] = Field(default_factory=list)

    @property
    def score_display(self) -> str:
        return f"{self.correct_answers}/{self.total_items}"


class AssessmentResult(BaseModel):
    """Everything produced by one completed assessment run."""

    result_id: str = Field(default_factory=_new_id)
    test_type: TestType
    grade: Grade
    child_id: str

    score: TestScore
    signals: Dict[str, Any] = Field(default_factory=dict)
    tags: List[TagOutput] = Field(default_factory=list)
    per_item_tags: List[PerItemTags] = Field(default_factory=list)

    recommendation: str = ""
    message: str = ""
    created_at: datetime = Field(default_factory=_utc_now)

    @property
    def tag_ids(self) -> List[str]:
        return [tag.tag for tag in self.tags]

    def tags_by_polarity(self, polarity: Polarity) -> List[TagOutput]:
        return [tag for tag in self.tags if tag.polarity is polarity]

    @property
    def strengths(self) -> List[TagOutput]:
        return self.tags_by_polarity(Polarity.STRENGTH)

    @property
    def growth_edges(self) -> List[TagOutput]:
        return self.tags_by_polarity(Polarity.GROWTH_EDGE)


# ---------------------------------------------------------------------------
# Account models
# ---------------------------------------------------------------------------
class Child(BaseModel):
    """A child profile belonging to a parent account."""

    child_id: str = Field(default_factory=_new_id)
    name: str
    age: int
    grade: Grade
    created_at: datetime = Field(default_factory=_utc_now)


class User(BaseModel):
    """A parent or administrator account."""

    user_id: str
    email: str
    name: str = ""
    is_admin: bool = False
    created_at: Optional[datetime] = None
