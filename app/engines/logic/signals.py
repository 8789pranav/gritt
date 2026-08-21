"""
Signal derivation for the Logic Quest assessment.

Reads a child's raw responses and produces the numeric signals that the
declarative tag rules in ``data/tags/logic_tags.json`` are evaluated against.

Two behaviours are load-bearing and were the subject of an earlier bug fix, so
they are called out explicitly:

* ``pattern_score`` counts **both** ``pattern_detection_strong`` and
  ``pattern_detection_emerging`` items. Counting only the latter caused whole
  grades to score zero.
* ``flexibility_score`` and ``load_success_count`` count *successes* on
  flexibility and load items. Without them, ``flexible_strategy_use`` could
  only ever fire from the grade 3-4 sort task, and
  ``reasoning_under_load_emerging`` could only fire from failures.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.domain.enums import CognitiveTag, Difficulty, TestType
from app.domain.models import LogicItem, LogicResponse, PerItemTags, TestScore
from app.engines.base import SignalDeriver

#: Tags whose correct answers contribute to ``pattern_score``.
PATTERN_TAGS = {
    CognitiveTag.PATTERN_DETECTION_STRONG,
    CognitiveTag.PATTERN_DETECTION_EMERGING,
}

#: A response faster than this fraction of the expected latency is "fast".
FAST_RESPONSE_RATIO = 0.5

#: A response slower than this multiple of the expected latency is "slow".
SLOW_RESPONSE_MULTIPLIER = 1.5


class LogicSignalDeriver(SignalDeriver[LogicItem, LogicResponse]):
    """Derives Logic Quest tagging signals."""

    def __init__(self) -> None:
        super().__init__(TestType.LOGIC)

    def derive(
        self,
        items: Sequence[LogicItem],
        responses: Sequence[LogicResponse],
        score: TestScore,
    ) -> Dict[str, Any]:
        items_by_id = {item.item_id: item for item in items}
        load_item_types = set(self.config.item_type_groups.get("load", []))

        # Skill accumulators.
        pattern_score = 0
        pattern_hard_count = 0
        relational_score = 0
        systematic_score = 0
        flexibility_score = 0
        load_success_count = 0

        # Difficulty / behaviour accumulators.
        load_fails = 0
        rule_maintenance_fails = 0
        multiple_attempts_count = 0
        fast_and_wrong_count = 0
        self_corrected_to_right_count = 0

        shift_result = "no_sort"
        rule_inferred = False

        for response in responses:
            item = items_by_id.get(response.item_id)
            if item is None:
                continue

            is_correct = item.is_correct(response.selected_answer_index)
            latency = response.response_time_seconds or 0
            expected = item.expected_latency_seconds or 30

            # --- skill credit for correct answers ---------------------------
            if is_correct:
                if item.primary_tag in PATTERN_TAGS:
                    pattern_score += 1
                    if item.difficulty is Difficulty.HARD:
                        pattern_hard_count += 1
                elif item.primary_tag is CognitiveTag.RELATIONAL_REASONING_PRESENT:
                    relational_score += 1
                elif item.primary_tag is CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING:
                    systematic_score += 1
                elif item.primary_tag is CognitiveTag.FLEXIBLE_STRATEGY_USE:
                    flexibility_score += 1
                elif item.primary_tag is CognitiveTag.REASONING_UNDER_LOAD_EMERGING:
                    load_success_count += 1

            # --- cognitive load: wrong, or right but laboured ---------------
            if item.item_type in load_item_types:
                if not is_correct or latency > expected * SLOW_RESPONSE_MULTIPLIER:
                    load_fails += 1

            # --- rule maintenance: failed a multi-step rule application -----
            if item.item_type in {"two_step", "rule_application"} and not is_correct:
                rule_maintenance_fails += 1

            # --- behavioural signals ---------------------------------------
            if response.attempts > 1:
                multiple_attempts_count += 1

            if not is_correct and latency and latency < expected * FAST_RESPONSE_RATIO:
                fast_and_wrong_count += 1

            if response.self_corrected and is_correct:
                self_corrected_to_right_count += 1

            # --- sort-task specific signals --------------------------------
            if response.post_shift_accuracy == "correct":
                shift_result = "shifted_ok"
            elif response.post_shift_accuracy == "incorrect":
                shift_result = "stuck"

            if response.rule_inferred:
                rule_inferred = True

        return {
            "pattern_score": pattern_score,
            "pattern_hard_count": pattern_hard_count,
            "relational_score": relational_score,
            "systematic_score": systematic_score,
            "flexibility_score": flexibility_score,
            "load_success_count": load_success_count,
            "load_fails": load_fails,
            "rule_maintenance_fails": rule_maintenance_fails,
            "shift_result": shift_result,
            "rule_inferred": rule_inferred,
            "multiple_attempts_count": multiple_attempts_count,
            "fast_and_wrong_count": fast_and_wrong_count,
            "self_corrected_to_right_count": self_corrected_to_right_count,
            # Contextual values, useful for reporting but not referenced by
            # any trigger.
            "total_items": score.total_items,
            "correct_answers": score.correct_answers,
            "overall_accuracy": self.ratio(score.correct_answers, score.total_items),
        }

    def per_item_tags(
        self,
        items: Sequence[LogicItem],
        responses: Sequence[LogicResponse],
        score: Optional[TestScore] = None,
    ) -> List[PerItemTags]:
        """Attribute behavioural observations to individual items."""
        items_by_id = {item.item_id: item for item in items}
        responses_by_id = {response.item_id: response for response in responses}
        results: List[PerItemTags] = []

        for item in items:
            response = responses_by_id.get(item.item_id)
            if response is None:
                results.append(
                    PerItemTags(
                        item_id=item.item_id,
                        answered=False,
                        is_correct=None,
                        tags=[f"{item.primary_tag.value}_missed"],
                    )
                )
                continue

            is_correct = item.is_correct(response.selected_answer_index)
            latency = response.response_time_seconds or 0
            expected = item.expected_latency_seconds or 30
            tags: List[str] = []

            if is_correct:
                tags.append(item.primary_tag.value)
            else:
                tags.append(f"{item.primary_tag.value}_missed")
            if response.attempts > 1:
                tags.append(CognitiveTag.TRIAL_AND_ERROR_STRATEGY.value)
            if response.self_corrected and is_correct:
                tags.append(CognitiveTag.SELF_CORRECTION_PRESENT.value)
            if not is_correct and latency and latency < expected * FAST_RESPONSE_RATIO:
                tags.append(CognitiveTag.IMPULSIVE_RESPONSE.value)
            if not is_correct and latency > expected * SLOW_RESPONSE_MULTIPLIER:
                tags.append(CognitiveTag.REASONING_UNDER_LOAD_EMERGING.value)

            # Conditional tags declared on the item itself.
            condition = self._condition_for(is_correct, latency, expected)
            conditional = item.conditional_tags.get(condition)
            if conditional is not None:
                tags.append(conditional.value)

            results.append(
                PerItemTags(
                    item_id=item.item_id,
                    answered=True,
                    is_correct=is_correct,
                    tags=list(dict.fromkeys(tags)),
                )
            )

        return results

    @staticmethod
    def _condition_for(is_correct: bool, latency: float, expected: int) -> str:
        speed = "slow" if latency > expected * SLOW_RESPONSE_MULTIPLIER else "fast"
        outcome = "right" if is_correct else "wrong"
        return f"{outcome}_{speed}"
