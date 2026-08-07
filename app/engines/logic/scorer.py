"""Scoring rules for the Logic Quest assessment."""

from __future__ import annotations

from typing import Dict, List, Sequence

from app.domain.enums import Grade, ResponseStatus, TestType
from app.domain.models import LogicItem, LogicResponse, ScoredItem, TestScore
from app.engines.base import Scorer

#: Percentage bands, highest first.
LEVEL_BANDS: Sequence[tuple[float, str]] = (
    (90.0, "Exceptional Logical Thinker"),
    (80.0, "Advanced Logical Thinker"),
    (70.0, "Good Logical Thinker"),
    (60.0, "Developing Logical Thinker"),
    (0.0, "Emerging Logical Thinker"),
)


class LogicScorer(Scorer[LogicItem, LogicResponse]):
    """Awards one point per correctly answered item.

    Items the child never reached are recorded as ``NOT_ATTEMPTED`` rather
    than being silently dropped, so the denominator always reflects the full
    test length.
    """

    def score(
        self,
        items: Sequence[LogicItem],
        responses: Sequence[LogicResponse],
        grade: Grade,
    ) -> TestScore:
        responses_by_item: Dict[str, LogicResponse] = {
            response.item_id: response for response in responses
        }

        scored: List[ScoredItem] = []
        correct = 0
        answered = 0

        for item in items:
            response = responses_by_item.get(item.item_id)

            if response is None:
                scored.append(
                    ScoredItem(
                        item_id=item.item_id,
                        label=item.item_number,
                        is_correct=False,
                        points=0.0,
                        max_points=1.0,
                        status=ResponseStatus.NOT_ATTEMPTED,
                        detail={
                            "item_type": item.item_type,
                            "difficulty": item.difficulty.value,
                            "primary_tag": item.primary_tag.value,
                            "correct_answer_index": item.correct_answer_index,
                        },
                    )
                )
                continue

            answered += 1
            is_correct = item.is_correct(response.selected_answer_index)
            if is_correct:
                correct += 1

            scored.append(
                ScoredItem(
                    item_id=item.item_id,
                    label=item.item_number,
                    is_correct=is_correct,
                    points=1.0 if is_correct else 0.0,
                    max_points=1.0,
                    status=ResponseStatus.ANSWERED,
                    detail={
                        "item_type": item.item_type,
                        "difficulty": item.difficulty.value,
                        "primary_tag": item.primary_tag.value,
                        "selected_answer_index": response.selected_answer_index,
                        "correct_answer_index": item.correct_answer_index,
                        "response_time_seconds": response.response_time_seconds,
                        "attempts": response.attempts,
                        "self_corrected": response.self_corrected,
                    },
                )
            )

        total = len(items)
        percentage = round(correct / total * 100, 1) if total else 0.0

        return TestScore(
            test_type=TestType.LOGIC,
            grade=grade,
            total_items=total,
            answered_items=answered,
            correct_answers=correct,
            points=float(correct),
            max_points=float(total),
            percentage=percentage,
            level=Scorer.level_for(percentage, LEVEL_BANDS),
            scored_items=scored,
        )
