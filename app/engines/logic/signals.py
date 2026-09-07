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

#: Item tags that measure working-memory load. The _EMERGING spelling is the
#: pre-L-B3 name, kept so an older stored payload still resolves.
LOAD_TAGS = {
    CognitiveTag.REASONING_UNDER_LOAD,
    CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
}

#: A response faster than this fraction of the expected latency is "fast".
FAST_RESPONSE_RATIO = 0.5

#: A response slower than this multiple of the expected latency is "slow".
SLOW_RESPONSE_MULTIPLIER = 1.5

#: Construct accuracy at or above this counts as a strength (G5, L-N1).
#: Thresholds must be proportions: the bank holds only one or two items per
#: construct per grade, so an absolute count like ">= 3" can never be met.
MASTERY_THRESHOLD = 0.75


def impulsive_threshold(responses) -> float:
    """Half the median response time across EVERY answered item (G1).

    Taking the median of the wrong answers alone made the tag unfirable: when
    every wrong answer is fast, none of them is fast *relative to the wrong
    answers*. The rollup and the per-item tags now read the same number.
    """
    latencies = sorted(
        r.response_time_seconds
        for r in responses
        if r.response_time_seconds and r.response_time_seconds > 0
    )
    if not latencies:
        return 0.0
    middle = len(latencies) // 2
    median = (
        latencies[middle]
        if len(latencies) % 2
        else (latencies[middle - 1] + latencies[middle]) / 2
    )
    return median * 0.5


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
        rule_item_types = set(self.config.item_type_groups.get("rule_application", []))

        # Skill accumulators. Each construct tracks how many items were SHOWN
        # as well as how many were correct, so the rollup can use a proportion
        # rather than an absolute count (G5, L-N1).
        pattern_score = pattern_shown = 0
        pattern_hard_count = 0
        relational_score = relational_shown = 0
        systematic_score = systematic_shown = 0
        flexibility_score = flexibility_shown = 0
        load_success_count = load_shown = 0

        # Difficulty / behaviour accumulators.
        load_fails = 0
        rule_maintenance_fails = rule_maintenance_shown = 0
        slow_and_correct_count = 0
        multiple_attempts_count = 0
        fast_and_wrong_count = 0
        self_corrected_to_right_count = 0

        # G1: Track latencies for median-based impulsivity check.
        latencies: List[float] = []
        wrong_latencies: List[float] = []

        shift_result = "no_sort"
        rule_inferred = False

        for response in responses:
            item = items_by_id.get(response.item_id)
            if item is None:
                continue

            is_correct = item.is_correct(response.selected_answer_index)
            latency = response.response_time_seconds or 0
            expected = item.expected_latency_seconds or 30

            # --- skill credit, counted against the items actually shown -----
            if item.primary_tag in PATTERN_TAGS:
                pattern_shown += 1
                if is_correct:
                    pattern_score += 1
                    if item.difficulty is Difficulty.HARD:
                        pattern_hard_count += 1
            elif item.primary_tag is CognitiveTag.RELATIONAL_REASONING_PRESENT:
                relational_shown += 1
                relational_score += int(is_correct)
            elif item.primary_tag is CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING:
                systematic_shown += 1
                systematic_score += int(is_correct)
            elif item.primary_tag is CognitiveTag.FLEXIBLE_STRATEGY_USE:
                flexibility_shown += 1
                flexibility_score += int(is_correct)
            elif item.primary_tag in LOAD_TAGS:
                load_shown += 1
                load_success_count += int(is_correct)

            # --- cognitive load: wrong, or right but laboured ---------------
            if item.item_type in load_item_types:
                if not is_correct or latency > expected * SLOW_RESPONSE_MULTIPLIER:
                    load_fails += 1

            # --- rule maintenance: held a stated rule, or dropped it --------
            # The item types come from the config so every grade has some;
            # the hardcoded pair only existed at Grade 1.
            if item.item_type in rule_item_types:
                rule_maintenance_shown += 1
                if not is_correct:
                    rule_maintenance_fails += 1

            # --- pace: worked slowly and still got it right -----------------
            if is_correct and latency > expected * SLOW_RESPONSE_MULTIPLIER:
                slow_and_correct_count += 1

            # --- behavioural signals ---------------------------------------
            if response.attempts > 1:
                multiple_attempts_count += 1

            if response.self_corrected and is_correct:
                self_corrected_to_right_count += 1

            # --- sort-task specific signals --------------------------------
            if response.post_shift_accuracy == "correct":
                shift_result = "shifted_ok"
            elif response.post_shift_accuracy == "incorrect":
                shift_result = "stuck"

            if response.rule_inferred:
                rule_inferred = True

            # G1: Collect response times for median-based impulsivity check.
            latencies.append(latency)

            # G1: Record wrong-answer latency for impulsivity check.
            if not is_correct and latency > 0:
                wrong_latencies.append(latency)

        # G1: wrong AND clearly faster than the typical pace. The threshold
        # is half the median of EVERY answered item - the same number that
        # per_item_tags uses, so the rollup and the item tags agree.
        cutoff = impulsive_threshold(responses)
        if cutoff > 0:
            fast_and_wrong_count = sum(
                1 for wl in wrong_latencies if 0 < wl <= cutoff
            )

        return {
            "pattern_score": pattern_score,
            "pattern_hard_count": pattern_hard_count,
            "relational_score": relational_score,
            "systematic_score": systematic_score,
            "flexibility_score": flexibility_score,
            "load_success_count": load_success_count,
            "load_fails": load_fails,
            # Proportions the rollup triggers read (G5, L-D7, L-N1).
            "pattern_accuracy": self.ratio(pattern_score, pattern_shown),
            "pattern_items_count": pattern_shown,
            "relational_accuracy": self.ratio(relational_score, relational_shown),
            "relational_items_count": relational_shown,
            "systematic_accuracy": self.ratio(systematic_score, systematic_shown),
            "systematic_items_count": systematic_shown,
            "flexibility_accuracy": self.ratio(flexibility_score, flexibility_shown),
            "flexibility_items_count": flexibility_shown,
            "load_accuracy": self.ratio(load_success_count, load_shown),
            "load_items_count": load_shown,
            "rule_maintenance_fails": rule_maintenance_fails,
            "rule_maintenance_items_count": rule_maintenance_shown,
            "rule_maintenance_accuracy": self.ratio(
                rule_maintenance_shown - rule_maintenance_fails,
                rule_maintenance_shown,
            ),
            "slow_and_correct_count": slow_and_correct_count,
            # L-D5: shift_result and rule_inferred are still derived above, so
            # wiring the sort task back up stays a one-line change, but they
            # are no longer published as signals - the API never populates the
            # response fields they read, so every tag built on them was dead.
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

        # G1: the same threshold the rollup uses.
        cutoff = impulsive_threshold(responses)

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
            # G1: Only tag as impulsive if wrong AND clearly faster than
            # the child's own median (below 50% of their median).
            if not is_correct and cutoff > 0 and 0 < latency <= cutoff:
                tags.append(CognitiveTag.IMPULSIVE_RESPONSE.value)
            # L-B3: the item tag names the construct; it makes no judgement.
            if not is_correct and latency > expected * SLOW_RESPONSE_MULTIPLIER:
                tags.append(CognitiveTag.REASONING_UNDER_LOAD.value)

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
