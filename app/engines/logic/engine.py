"""Logic Quest assessment engine."""

from __future__ import annotations

from typing import Any, List, Mapping, Sequence, Tuple

from app.domain.enums import Confidence, Grade, Polarity, TestType
from app.domain.models import LogicItem, LogicResponse, TagOutput, TestScore
from app.engines.base import AssessmentEngine
from app.engines.logic.loader import LogicQuestionLoader
from app.engines.logic.scorer import LEVEL_BANDS, LogicScorer
from app.engines.logic.signals import LogicSignalDeriver

#: Guidance shown to parents, keyed by the lowest percentage that earns it.
#: L-D9: advice describes what the child DID, not what the child IS. No
#: labels, no grade levels, no scores.
_RECOMMENDATIONS: Sequence[Tuple[float, str]] = (
    (
        90.0,
        "Your child solved most of the puzzles correctly, including the "
        "harder multi-step ones. Try introducing more complex pattern and "
        "logic puzzles to keep stretching their thinking.",
    ),
    (
        75.0,
        "Your child worked through most of the puzzles well. Keep "
        "introducing multi-step puzzles to stretch their thinking further.",
    ),
    (
        60.0,
        "Your child is building their reasoning skills. Practising pattern "
        "and sequence puzzles together a few times a week will help them "
        "grow.",
    ),
    (
        0.0,
        "Your child is starting to explore logic puzzles. Focus on simple "
        "patterns and sorting games first, then build up to multi-step "
        "reasoning.",
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

    # L-D8: tie confidence to the number of questions behind a tag. A tag
    # backed by 3-4 questions is capped at medium; only 5+ questions can be
    # high. The >= 3 trigger threshold is enforced in logic_tags.json.
    _TAG_TO_COUNT_SIGNAL = {
        "pattern_detection_strong": "pattern_items_count",
        "pattern_detection_emerging": "pattern_items_count",
        "relational_reasoning_present": "relational_items_count",
        "relational_reasoning_emerging": "relational_items_count",
        "systematic_problem_solving": "systematic_items_count",
        "systematic_problem_solving_emerging": "systematic_items_count",
        "flexible_strategy_use": "flexibility_items_count",
        "flexible_strategy_emerging": "flexibility_items_count",
        "reasoning_under_load": "load_items_count",
        "reasoning_under_load_emerging": "load_items_count",
    }

    def emit(self, signals: Mapping[str, Any]) -> List[TagOutput]:
        tags = super().emit(signals)
        result: List[TagOutput] = []
        for tag in tags:
            count_signal = self._TAG_TO_COUNT_SIGNAL.get(tag.tag)
            if count_signal and count_signal in signals:
                count = signals[count_signal]
                if count < 5 and tag.confidence is Confidence.HIGH:
                    tag = tag.model_copy(update={"confidence": Confidence.MEDIUM})
            result.append(tag)
        return result

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
