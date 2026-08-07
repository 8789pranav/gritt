"""Logic Quest assessment engine."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from app.domain.enums import Grade, Polarity, TestType
from app.domain.models import LogicItem, LogicResponse, TagOutput, TestScore
from app.engines.base import AssessmentEngine
from app.engines.logic.loader import LogicQuestionLoader
from app.engines.logic.scorer import LEVEL_BANDS, LogicScorer
from app.engines.logic.signals import LogicSignalDeriver

#: Guidance shown to parents, keyed by the lowest percentage that earns it.
_RECOMMENDATIONS: Sequence[Tuple[float, str]] = (
    (
        90.0,
        "Excellent logical reasoning! Challenge your child with advanced puzzles "
        "and abstract thinking exercises.",
    ),
    (
        75.0,
        "Strong reasoning skills. Keep introducing multi-step puzzles to stretch "
        "their thinking.",
    ),
    (
        60.0,
        "Developing well. Practise pattern and sequence puzzles together a few "
        "times a week.",
    ),
    (
        0.0,
        "Focus on simple patterns and sorting games first, then build up to "
        "multi-step reasoning.",
    ),
)

_NEXT_STEPS = {
    Polarity.STRENGTH: "Keep extending these strengths with harder puzzles.",
    Polarity.GROWTH_EDGE: "Practise multi-step logic puzzles and pattern recognition.",
}


class LogicEngine(AssessmentEngine[LogicItem, LogicResponse]):
    """Assembles the Logic Quest loader, scorer and signal deriver."""

    level_bands = LEVEL_BANDS

    def __init__(self) -> None:
        super().__init__(
            loader=LogicQuestionLoader(),
            scorer=LogicScorer(),
            deriver=LogicSignalDeriver(),
        )

    @property
    def test_type(self) -> TestType:
        return TestType.LOGIC

    def item_key(self, item: LogicItem) -> str:
        return item.item_id

    def recommend(self, score: TestScore, tags: Sequence[TagOutput]) -> str:
        for minimum, text in _RECOMMENDATIONS:
            if score.percentage >= minimum:
                return text
        return _RECOMMENDATIONS[-1][1]

    def next_step(self, tags: Sequence[TagOutput]) -> str:
        """Single actionable suggestion derived from the emitted tags."""
        has_growth_edge = any(tag.polarity is Polarity.GROWTH_EDGE for tag in tags)
        polarity = Polarity.GROWTH_EDGE if has_growth_edge else Polarity.STRENGTH
        return _NEXT_STEPS[polarity]

    def narration_targets(self, grade: Grade) -> List[Tuple[str, str]]:
        """Every question and option string that needs a narration clip."""
        targets: List[Tuple[str, str]] = []
        for item in self.get_items(grade):
            targets.append((f"{item.item_id}:question", item.question_text))
            for option in item.options:
                targets.append((f"{item.item_id}:option:{option.index}", option.text))
        return targets
