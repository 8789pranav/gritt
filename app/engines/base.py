"""
Assessment engine abstractions.

The interfaces here are split by responsibility so that a collaborator only
depends on the slice it needs (interface segregation):

* :class:`QuestionLoader`  - reads items from a question bank
* :class:`Scorer`          - turns responses into a :class:`TestScore`
* :class:`SignalDeriver`   - turns responses into tagging signals
* :class:`AssessmentEngine`- composes the three into one façade

Every concrete engine subclasses :class:`AssessmentEngine`, so callers can
treat all four assessments uniformly (Liskov substitution).
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Generic, List, Mapping, Optional, Sequence, TypeVar

from app.core.config import get_settings
from app.core.exceptions import DataFileError, InvalidGradeError
from app.domain.enums import Grade, TestType
from app.domain.models import (
    AssessmentResult,
    PerItemTags,
    TagOutput,
    TestScore,
)
from app.tagging.config_loader import TagConfig, load_tag_config
from app.tagging.emitter import emit_tags

logger = logging.getLogger(__name__)

TItem = TypeVar("TItem")
TResponse = TypeVar("TResponse")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
class QuestionLoader(ABC, Generic[TItem]):
    """Reads a question bank for one assessment."""

    #: Key under which the item collection is stored in the JSON envelope.
    items_key: str = "items"

    def __init__(self, test: TestType) -> None:
        self.test = test
        self._cache: Dict[Grade, List[TItem]] = {}

    @property
    def questions_dir(self) -> Path:
        return get_settings().paths.questions_dir / self.test.value

    def load(self, grade: Grade) -> List[TItem]:
        """Return every item for ``grade``, reading from disk at most once."""
        if grade not in self._cache:
            self._cache[grade] = self._read(grade)
        return list(self._cache[grade])

    def load_all(self) -> List[TItem]:
        """Return every item across every grade."""
        items: List[TItem] = []
        for grade in Grade:
            try:
                items.extend(self.load(grade))
            except DataFileError:
                logger.warning("No %s bank for %s", self.test.value, grade.value)
        return items

    def _read(self, grade: Grade) -> List[TItem]:
        path = self.questions_dir / f"{grade.file_stem}.json"
        if not path.exists():
            raise DataFileError(f"Question bank not found: {path}")

        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DataFileError(f"{path.name} contains invalid JSON: {exc}") from exc

        raw_items = document.get(self.items_key)
        if not isinstance(raw_items, list):
            raise DataFileError(f"{path.name} has no '{self.items_key}' list")

        return [self.parse_item(raw, grade) for raw in raw_items]

    @abstractmethod
    def parse_item(self, raw: Mapping[str, Any], grade: Grade) -> TItem:
        """Convert one raw JSON object into a domain item."""

    def clear_cache(self) -> None:
        self._cache.clear()


# ---------------------------------------------------------------------------
# Scoring and signals
# ---------------------------------------------------------------------------
class Scorer(ABC, Generic[TItem, TResponse]):
    """Converts responses into an aggregate score."""

    @abstractmethod
    def score(
        self,
        items: Sequence[TItem],
        responses: Sequence[TResponse],
        grade: Grade,
    ) -> TestScore:
        """Score a complete submission."""

    @staticmethod
    def level_for(percentage: float, bands: Sequence[tuple[float, str]]) -> str:
        """Resolve a percentage to a label using descending ``(min, label)`` bands."""
        for minimum, label in bands:
            if percentage >= minimum:
                return label
        return bands[-1][1] if bands else ""


class SignalDeriver(ABC, Generic[TItem, TResponse]):
    """Derives the tagging signals for one assessment."""

    def __init__(self, test: TestType) -> None:
        self.test = test

    @property
    def config(self) -> TagConfig:
        return load_tag_config(self.test)

    @abstractmethod
    def derive(
        self,
        items: Sequence[TItem],
        responses: Sequence[TResponse],
        score: TestScore,
    ) -> Dict[str, Any]:
        """Return the signal dictionary consumed by the tag emitter."""

    def per_item_tags(
        self,
        items: Sequence[TItem],
        responses: Sequence[TResponse],
    ) -> List[PerItemTags]:
        """Optional per-item tagging. Defaults to no per-item tags."""
        return []

    @staticmethod
    def ratio(numerator: float, denominator: float) -> float:
        """Safe division returning 0.0 when the denominator is zero."""
        if not denominator:
            return 0.0
        return round(numerator / denominator, 4)


# ---------------------------------------------------------------------------
# Engine façade
# ---------------------------------------------------------------------------
class AssessmentEngine(ABC, Generic[TItem, TResponse]):
    """Composes loading, scoring, signal derivation and tag emission."""

    #: Percentage bands, highest first, used to label overall performance.
    level_bands: Sequence[tuple[float, str]] = ()

    def __init__(
        self,
        loader: QuestionLoader[TItem],
        scorer: Scorer[TItem, TResponse],
        deriver: SignalDeriver[TItem, TResponse],
    ) -> None:
        self.loader = loader
        self.scorer = scorer
        self.deriver = deriver

    # -- identity ----------------------------------------------------------
    @property
    @abstractmethod
    def test_type(self) -> TestType:
        """Which assessment this engine implements."""

    @property
    def display_name(self) -> str:
        return self.test_type.display_name

    @property
    def tag_config(self) -> TagConfig:
        return load_tag_config(self.test_type)

    # -- item access -------------------------------------------------------
    def get_items(self, grade: Grade) -> List[TItem]:
        items = self.loader.load(grade)
        if not items:
            raise InvalidGradeError(grade.value, Grade.values())
        return items

    def get_all_items(self) -> List[TItem]:
        return self.loader.load_all()

    def item_index(self, grade: Optional[Grade] = None) -> Dict[str, TItem]:
        """Map item identifier to item, for fast response lookups."""
        items = self.get_items(grade) if grade else self.get_all_items()
        return {self.item_key(item): item for item in items}

    @abstractmethod
    def item_key(self, item: TItem) -> str:
        """Identifier used to match a response back to its item."""

    # -- the main pipeline -------------------------------------------------
    def evaluate(
        self,
        child_id: str,
        grade: Grade,
        responses: Sequence[TResponse],
    ) -> AssessmentResult:
        """Run the full score -> derive -> tag pipeline for one submission."""
        items = self.get_items(grade)

        score = self.scorer.score(items, responses, grade)
        if not score.level:
            score.level = Scorer.level_for(score.percentage, self.level_bands)

        signals = self.deriver.derive(items, responses, score)
        tags = self.emit(signals)
        per_item = self.deriver.per_item_tags(items, responses)

        return AssessmentResult(
            test_type=self.test_type,
            grade=grade,
            child_id=child_id,
            score=score,
            signals=signals,
            tags=tags,
            per_item_tags=per_item,
            recommendation=self.recommend(score, tags),
            message=self.summary_message(score),
        )

    def emit(self, signals: Mapping[str, Any]) -> List[TagOutput]:
        """Apply this engine's tag rules to a signal dictionary."""
        return emit_tags(self.test_type, signals, config=self.tag_config)

    # -- presentation hooks ------------------------------------------------
    @abstractmethod
    def recommend(self, score: TestScore, tags: Sequence[TagOutput]) -> str:
        """Parent-facing next-step guidance."""

    def summary_message(self, score: TestScore) -> str:
        return (
            f"Test completed: {score.correct_answers}/{score.total_items} "
            f"correct ({score.percentage}%)"
        )

    def narration_targets(self, grade: Grade) -> List[tuple[str, str]]:
        """``(cache_key, text)`` pairs this engine wants narrated.

        Engines that need no audio can leave the default empty implementation.
        """
        return []
