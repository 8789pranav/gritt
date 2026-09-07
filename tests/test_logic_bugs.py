"""Regression tests for the Logic Quest bug list.

One test per bug from the Dear Parent Project review, named for the bug number
so a future failure points straight back at the decision it encodes.
"""

from __future__ import annotations

import json

import pytest

from app.domain.enums import Grade
from app.domain.models import LogicResponse
from app.engines import registry


def _run(grade: Grade, wrong=(), times=None):
    """Answer every item, missing the ids in ``wrong``."""
    engine = registry.logic_engine()
    items = engine.get_items(grade)
    responses = [
        LogicResponse(
            item_id=item.item_id,
            selected_answer_index=(
                (item.correct_answer_index + 1) % len(item.options)
                if item.item_id in wrong
                else item.correct_answer_index
            ),
            response_time_seconds=(times or {}).get(item.item_id, 10.0),
        )
        for item in items
    ]
    result = engine.evaluate("child", grade, responses)
    return result, {t.tag for t in result.tags}


def _polarity(result, tag_id):
    return next(t.polarity.value for t in result.tags if t.tag == tag_id)


# ---------------------------------------------------------------------------
# G5 - pattern_detection_strong must be reachable, under its own name
# ---------------------------------------------------------------------------
class TestG5PatternRename:
    @pytest.mark.parametrize("grade", list(Grade))
    def test_perfect_pattern_items_fire_strong(self, grade: Grade):
        result, ids = _run(grade)
        assert "pattern_detection_strong" in ids
        assert "pattern_detection_emerging" not in ids
        assert _polarity(result, "pattern_detection_strong") == "strength"

    def test_two_of_two_hard_pattern_items(self):
        """The Grade 3 run from the report: 3-1 and 3-5, both hard, both right."""
        result, ids = _run(Grade.THIRD, wrong={"logic_3_3"})
        assert result.signals["pattern_accuracy"] == 1.0
        assert result.signals["pattern_hard_count"] == 2
        assert "pattern_detection_strong" in ids

    def test_emerging_is_a_growth_edge(self):
        result, ids = _run(Grade.THIRD, wrong={"logic_3_1", "logic_3_5"})
        assert "pattern_detection_emerging" in ids
        assert _polarity(result, "pattern_detection_emerging") == "growth_edge"

    def test_threshold_is_a_proportion_not_a_count(self):
        """No grade has three pattern items, so '>= 3' was unreachable."""
        for grade in Grade:
            result, _ = _run(grade)
            assert result.signals["pattern_items_count"] <= 3
            assert result.signals["pattern_accuracy"] == 1.0


# ---------------------------------------------------------------------------
# L-D7 - reasoning under load: strength above threshold, growth below
# ---------------------------------------------------------------------------
class TestLD7ReasoningUnderLoad:
    LOAD_ITEMS = {"logic_2_3", "logic_2_7"}

    def test_both_load_items_right_is_a_strength(self):
        result, ids = _run(Grade.SECOND)
        assert result.signals["load_success_count"] == 2
        assert result.signals["load_fails"] == 0
        assert "reasoning_under_load" in ids
        assert _polarity(result, "reasoning_under_load") == "strength"
        assert "reasoning_under_load_emerging" not in ids

    def test_both_load_items_wrong_is_a_growth_edge(self):
        result, ids = _run(Grade.SECOND, wrong=self.LOAD_ITEMS)
        assert "reasoning_under_load_emerging" in ids
        assert _polarity(result, "reasoning_under_load_emerging") == "growth_edge"
        assert "reasoning_under_load" not in ids

    def test_never_a_growth_edge_on_zero_failures(self):
        for grade in Grade:
            result, ids = _run(grade)
            if result.signals["load_fails"] == 0:
                assert "reasoning_under_load_emerging" not in ids

    def test_same_evidence_gives_the_same_outcome_across_grades(self):
        """K and Grade 3 disagreed on identical evidence."""
        outcomes = {}
        for grade in (Grade.FIRST, Grade.THIRD):
            result, ids = _run(grade)
            assert result.signals["load_accuracy"] == 1.0
            outcomes[grade] = "reasoning_under_load" in ids
        assert len(set(outcomes.values())) == 1


# ---------------------------------------------------------------------------
# G1 - impulsive_response
# ---------------------------------------------------------------------------
class TestG1Impulsive:
    FAST = {"logic_3_3": 1.0, "logic_3_4": 1.0}

    def _times(self, overrides):
        times = {f"logic_3_{i}": 10.0 for i in range(1, 9)}
        times.update(overrides)
        return times

    def test_fires_on_fast_wrong_answers(self):
        result, ids = _run(
            Grade.THIRD, wrong=set(self.FAST), times=self._times(self.FAST)
        )
        assert result.signals["fast_and_wrong_count"] == 2
        assert "impulsive_response" in ids

    def test_does_not_fire_on_slow_wrong_answers(self):
        times = {f"logic_3_{i}": 2.0 for i in range(1, 9)}
        times.update({"logic_3_3": 8.0, "logic_3_4": 3.0})
        result, ids = _run(Grade.THIRD, wrong={"logic_3_3", "logic_3_4"}, times=times)
        assert result.signals["fast_and_wrong_count"] == 0
        assert "impulsive_response" not in ids

    def test_rollup_and_item_tags_agree(self):
        """The rollup took the median of wrong answers, the items took all."""
        result, ids = _run(
            Grade.THIRD, wrong=set(self.FAST), times=self._times(self.FAST)
        )
        flagged = {
            p.item_id for p in result.per_item_tags if "impulsive_response" in p.tags
        }
        assert flagged == set(self.FAST)
        assert result.signals["fast_and_wrong_count"] == len(flagged)

    def test_never_fires_without_timing_data(self):
        times = {f"logic_3_{i}": 0.0 for i in range(1, 9)}
        result, ids = _run(Grade.THIRD, wrong={"logic_3_3", "logic_3_4"}, times=times)
        assert result.signals["fast_and_wrong_count"] == 0
        assert "impulsive_response" not in ids


# ---------------------------------------------------------------------------
# L-N1 - every construct needs an _emerging partner
# ---------------------------------------------------------------------------
class TestLN1EmergingPartners:
    def test_missed_systematic_and_flexible_reach_the_rollup(self):
        """The Grade 3 run: one systematic and one flexible item missed."""
        result, ids = _run(Grade.THIRD, wrong={"logic_3_4", "logic_3_8"})
        assert "systematic_problem_solving_emerging" in ids
        assert "flexible_strategy_emerging" in ids

    def test_missed_relational_reaches_the_rollup(self):
        result, ids = _run(Grade.THIRD, wrong={"logic_3_3"})
        assert "relational_reasoning_emerging" in ids

    @pytest.mark.parametrize(
        "tag_id",
        [
            "relational_reasoning_emerging",
            "systematic_problem_solving_emerging",
            "flexible_strategy_emerging",
        ],
    )
    def test_partners_exist_and_are_growth_edges(self, tag_id):
        config = json.load(open("data/tags/logic_tags.json", encoding="utf-8"))
        definition = next(t for t in config["tags"] if t["id"] == tag_id)
        assert definition["polarity"] == "growth_edge"

    def test_a_construct_never_shown_stays_silent(self):
        """Kindergarten has no flexibility items; it must not report on them."""
        result, ids = _run(Grade.KINDERGARTEN)
        assert result.signals["flexibility_items_count"] == 0
        assert "flexible_strategy_use" not in ids
        assert "flexible_strategy_emerging" not in ids


# ---------------------------------------------------------------------------
# Cap - every tag that clears its threshold reaches the parent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("grade", [Grade.FIRST, Grade.SECOND, Grade.THIRD])
def test_no_cap_on_the_rollup(grade: Grade):
    result, ids = _run(grade)
    assert len(result.tags) >= 5, sorted(ids)
    assert not result.growth_edges, [t.tag for t in result.growth_edges]


# ---------------------------------------------------------------------------
# L-B1 / L-B2 / L-B3 - question bank
# ---------------------------------------------------------------------------
class TestBankRetags:
    def _items(self, grade):
        return {i.item_id: i for i in registry.logic_engine().get_items(grade)}

    def test_lb1_size_comparison_is_not_a_load_item(self):
        item = self._items(Grade.KINDERGARTEN)["logic_k_7"]
        assert item.primary_tag.value == "relational_reasoning_present"

    @pytest.mark.parametrize(
        "grade,item_id", [(Grade.SECOND, "logic_2_8"), (Grade.THIRD, "logic_3_7")]
    )
    def test_lb2_rule_conjunction_is_not_strategy_shift(self, grade, item_id):
        item = self._items(grade)[item_id]
        assert item.primary_tag.value == "systematic_problem_solving"

    @pytest.mark.parametrize(
        "grade,item_id",
        [
            (Grade.FIRST, "logic_1_6"),
            (Grade.SECOND, "logic_2_6"),
            (Grade.THIRD, "logic_3_8"),
        ],
    )
    def test_lb2_genuine_shift_items_keep_the_tag(self, grade, item_id):
        item = self._items(grade)[item_id]
        assert item.primary_tag.value == "flexible_strategy_use"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_lb3_no_item_carries_a_judgement(self, grade: Grade):
        for item in registry.logic_engine().get_items(grade):
            assert item.primary_tag.value != "reasoning_under_load_emerging"

    def test_lb1_comparison_dropped_from_the_load_group(self):
        config = json.load(open("data/tags/logic_tags.json", encoding="utf-8"))
        assert "comparison" not in config["item_type_groups"]["load"]


# ---------------------------------------------------------------------------
# L-D5 / L-D6 - dead signals and the evidence string
# ---------------------------------------------------------------------------
def test_ld5_dead_signals_are_not_published():
    result, _ = _run(Grade.FIRST)
    assert "shift_result" not in result.signals
    assert "rule_inferred" not in result.signals


def test_ld5_tags_built_on_dead_signals_are_gone():
    config = json.load(open("data/tags/logic_tags.json", encoding="utf-8"))
    ids = {t["id"] for t in config["tags"]}
    assert "cognitive_flexibility_intact" not in ids
    assert "strategy_shift_difficulty" not in ids


def test_ld6_evidence_never_cites_rule_inferred():
    result, _ = _run(Grade.THIRD)
    for tag in result.tags:
        assert "rule_inferred" not in tag.evidence, f"{tag.tag}: {tag.evidence}"


# ---------------------------------------------------------------------------
# L-D1 - the teacher table reads the keys the scorer writes
# ---------------------------------------------------------------------------
def test_ld1_scored_items_carry_time_and_indices():
    result, _ = _run(Grade.THIRD, wrong={"logic_3_3"})
    for item in result.score.scored_items:
        detail = item.detail
        assert detail.get("selected_answer_index") is not None
        assert detail.get("correct_answer_index") is not None
        assert detail.get("response_time_seconds") == 10.0


def test_ld1_service_reads_the_same_keys():
    """The teacher table built the same way assessment_service builds it."""
    result, _ = _run(Grade.THIRD, wrong={"logic_3_3"})
    rows = [
        {
            "selected_index": s.detail.get("selected_answer_index"),
            "correct_index": s.detail.get("correct_answer_index"),
            "time": s.detail.get("response_time_seconds", 0.0),
        }
        for s in result.score.scored_items
    ]
    assert all(r["selected_index"] is not None for r in rows)
    assert all(r["correct_index"] is not None for r in rows)
    assert all(r["time"] > 0 for r in rows)


# ---------------------------------------------------------------------------
# Parent-facing copy stays in step with the config
# ---------------------------------------------------------------------------
def test_every_logic_tag_has_parent_copy():
    from app.services.report_service import ReportService

    config = json.load(open("data/tags/logic_tags.json", encoding="utf-8"))
    ids = {t["id"] for t in config["tags"]}
    missing = ids - set(ReportService._TAG_SENTENCE_MAP)
    assert not missing, missing


# ---------------------------------------------------------------------------
# Signals captured but not used - the last table in Part B
# ---------------------------------------------------------------------------
class TestUnusedSignals:
    """Every signal the review listed as captured-but-unused now feeds a tag."""

    def _rule_items(self, grade):
        config = json.load(open("data/tags/logic_tags.json", encoding="utf-8"))
        types = set(config["item_type_groups"]["rule_application"])
        return {
            i.item_id
            for i in registry.logic_engine().get_items(grade)
            if i.item_type in types
        }

    @pytest.mark.parametrize("grade", list(Grade))
    def test_rule_maintenance_is_reachable_at_every_grade(self, grade: Grade):
        """It counted two hardcoded item types, present only at Grade 1."""
        rule_items = self._rule_items(grade)
        assert rule_items, f"{grade.value}: no rule-application items"
        result, ids = _run(grade, wrong=rule_items)
        assert "rule_maintenance_difficulty" in ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_rule_maintenance_silent_when_rules_were_held(self, grade: Grade):
        result, ids = _run(grade)
        assert result.signals["rule_maintenance_accuracy"] == 1.0
        assert "rule_maintenance_difficulty" not in ids

    def test_response_time_feeds_a_pace_observation(self):
        """A child who works slowly and gets the hard items right left no record."""
        items = registry.logic_engine().get_items(Grade.SECOND)
        times = {
            i.item_id: (60.0 if i.difficulty.value == "hard" else 5.0) for i in items
        }
        result, ids = _run(Grade.SECOND, times=times)
        assert result.signals["slow_and_correct_count"] >= 2
        assert "deliberate_pace" in ids
        assert _polarity(result, "deliberate_pace") == "neutral"

    def test_a_fast_perfect_run_is_not_deliberate(self):
        items = registry.logic_engine().get_items(Grade.SECOND)
        result, ids = _run(Grade.SECOND, times={i.item_id: 2.0 for i in items})
        assert result.signals["slow_and_correct_count"] == 0
        assert "deliberate_pace" not in ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_attempts_and_self_correction_already_feed_tags(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=10.0,
                attempts=3,
                self_corrected=True,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)
        ids = {t.tag for t in result.tags}
        assert "trial_and_error_strategy" in ids
        assert "self_correction_present" in ids


# ---------------------------------------------------------------------------
# Part B preconditions
# ---------------------------------------------------------------------------
PART_B_POLARITY = {
    "pattern_detection_strong": "strength",
    "pattern_detection_emerging": "growth_edge",
    "relational_reasoning_present": "strength",
    "relational_reasoning_emerging": "growth_edge",
    "systematic_problem_solving": "strength",
    "systematic_problem_solving_emerging": "growth_edge",
    "flexible_strategy_use": "strength",
    "flexible_strategy_emerging": "growth_edge",
    "reasoning_under_load": "strength",
    "reasoning_under_load_emerging": "growth_edge",
    "impulsive_response": "growth_edge",
}


@pytest.mark.parametrize("tag_id,polarity", sorted(PART_B_POLARITY.items()))
def test_polarity_comes_from_the_table_not_the_name(tag_id, polarity):
    config = json.load(open("data/tags/logic_tags.json", encoding="utf-8"))
    definition = next(t for t in config["tags"] if t["id"] == tag_id)
    assert definition["polarity"] == polarity


@pytest.mark.parametrize(
    "grade,item_id,construct",
    [
        (Grade.THIRD, "logic_3_1", "pattern_detection_strong"),
        (Grade.THIRD, "logic_3_3", "relational_reasoning_present"),
        (Grade.THIRD, "logic_3_4", "systematic_problem_solving"),
        (Grade.THIRD, "logic_3_8", "flexible_strategy_use"),
        (Grade.THIRD, "logic_3_2", "reasoning_under_load"),
    ],
)
def test_item_level_construct_and_missed_pairs(grade, item_id, construct):
    result, _ = _run(grade)
    right = next(p for p in result.per_item_tags if p.item_id == item_id)
    assert construct in right.tags

    result, _ = _run(grade, wrong={item_id})
    missed = next(p for p in result.per_item_tags if p.item_id == item_id)
    assert f"{construct}_missed" in missed.tags
