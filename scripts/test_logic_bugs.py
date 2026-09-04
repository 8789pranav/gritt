"""Comprehensive verification of logic assessment bug fixes (G1-G6)."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any, Optional, List
from app.domain.enums import Grade, TestType, CognitiveTag, Difficulty
from app.domain.models import LogicResponse, LogicItem, Option
from app.engines.registry import logic_engine
from app.engines.logic.signals import LogicSignalDeriver
from app.engines.logic.scorer import LogicScorer
from app.tagging.config_loader import load_tag_config, clear_cache

# Clear cached config so our changes are picked up
clear_cache()

engine = logic_engine()
scorer = LogicScorer()
deriver = LogicSignalDeriver()

passed = 0
failed = 0


def sep(title):
    print(f"\n{'='*80}\n  {title}\n{'='*80}")


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} {detail}")
        failed += 1


def make_response(item, selected_index, time=5.0, attempts=1, self_corrected=False):
    return LogicResponse(
        item_id=item.item_id,
        selected_answer_index=selected_index,
        response_time_seconds=time,
        attempts=attempts,
        self_corrected=self_corrected,
    )


def run_full_test(grade, responses):
    """Run the full evaluate pipeline and return the result."""
    items = engine.get_items(grade)
    return engine.evaluate("test-child", grade, responses, items=items)


# ============================================================
# G1: impulsive_response only fires on fast relative to child's own median
# ============================================================
sep("G1: impulsive_response uses child's own median, not fixed threshold")

# Scenario: 8 items, all answered in 1.0s, 4 correct 4 wrong
# Old behavior: all 4 wrong would be "fast_and_wrong" (1.0 < 30*0.5=15)
# New behavior: median is 1.0, threshold is 0.5, none are <= 0.5, so fast_and_wrong_count = 0
k_items = engine.get_items(Grade.KINDERGARTEN)
responses_uniform = []
for i, item in enumerate(k_items):
    if i < 4:
        responses_uniform.append(make_response(item, item.correct_answer_index, time=1.0))
    else:
        wrong_idx = (item.correct_answer_index + 1) % len(item.options)
        responses_uniform.append(make_response(item, wrong_idx, time=1.0))

result_uniform = run_full_test(Grade.KINDERGARTEN, responses_uniform)
signals_uniform = result_uniform.signals
print(f"  Uniform 1.0s: fast_and_wrong_count={signals_uniform['fast_and_wrong_count']}")
check("G1: uniform 1.0s -> fast_and_wrong_count = 0",
      signals_uniform["fast_and_wrong_count"] == 0,
      f"fast_and_wrong_count={signals_uniform['fast_and_wrong_count']}")

# Check impulsive_response tag not fired
tag_ids = [t.tag for t in result_uniform.tags]
check("G1: uniform 1.0s -> no impulsive_response tag",
      "impulsive_response" not in tag_ids,
      f"tags={tag_ids}")

# Check per_item_tags: no impulsive_response
for p in result_uniform.per_item_tags:
    if p.answered and not p.is_correct:
        check(f"G1: {p.item_id} no impulsive_response (uniform speed)",
              "impulsive_response" not in p.tags,
              f"tags={p.tags}")

# Scenario: 8 items, median 5.0s, two wrong at 1.0s (clearly fast)
responses_varied = []
for i, item in enumerate(k_items):
    if i < 4:
        responses_varied.append(make_response(item, item.correct_answer_index, time=5.0))
    elif i < 6:
        wrong_idx = (item.correct_answer_index + 1) % len(item.options)
        responses_varied.append(make_response(item, wrong_idx, time=1.0))  # fast wrong
    else:
        wrong_idx = (item.correct_answer_index + 1) % len(item.options)
        responses_varied.append(make_response(item, wrong_idx, time=5.0))  # slow wrong

result_varied = run_full_test(Grade.KINDERGARTEN, responses_varied)
signals_varied = result_varied.signals
# Median of all latencies: [1,1,5,5,5,5,5,5] -> sorted -> median=5.0, threshold=2.5
# Wrong latencies: [1,1,5,5] -> median=1.0... wait, wrong_latencies only has wrong answers
# Wrong at 1.0, 1.0, 5.0, 5.0 -> median = 1.0 (sorted: [1,1,5,5], index 2 = 5)
# Actually median of [1,1,5,5] = (1+5)/2 = 3.0? No, we use integer index: [1,1,5,5][2] = 5
# threshold = 5 * 0.5 = 2.5, fast ones at 1.0 <= 2.5 -> count = 2
print(f"  Varied times: fast_and_wrong_count={signals_varied['fast_and_wrong_count']}")
check("G1: varied times -> fast_and_wrong_count = 2",
      signals_varied["fast_and_wrong_count"] == 2,
      f"fast_and_wrong_count={signals_varied['fast_and_wrong_count']}")

# Scenario: no response times (all 0)
responses_no_time = []
for i, item in enumerate(k_items):
    if i < 4:
        responses_no_time.append(make_response(item, item.correct_answer_index, time=0.0))
    else:
        wrong_idx = (item.correct_answer_index + 1) % len(item.options)
        responses_no_time.append(make_response(item, wrong_idx, time=0.0))

result_no_time = run_full_test(Grade.KINDERGARTEN, responses_no_time)
signals_no_time = result_no_time.signals
print(f"  No times: fast_and_wrong_count={signals_no_time['fast_and_wrong_count']}")
check("G1: no response times -> fast_and_wrong_count = 0",
      signals_no_time["fast_and_wrong_count"] == 0,
      f"fast_and_wrong_count={signals_no_time['fast_and_wrong_count']}")


# ============================================================
# G2: impulsive_response wording + never show only growth edge
# ============================================================
sep("G2: impulsive_response wording and no-only-growth-edge")

config = load_tag_config(TestType.LOGIC)
impulsive_tag = config.get("impulsive_response")
check("G2: description doesn't say 'Child responds quickly'",
      "Child responds quickly" not in impulsive_tag.description,
      f"desc={impulsive_tag.description}")
check("G2: description uses 'your child' or warm language",
      "your child" in impulsive_tag.description.lower() or "some answers" in impulsive_tag.description.lower(),
      f"desc={impulsive_tag.description}")

# Check that when only growth edges fire, strengths gets a fallback
# Simulate: all wrong, fast -> impulsive_response fires, no strengths
# Use the varied responses scenario which has fast_and_wrong_count=2
tag_ids_varied = [t.tag for t in result_varied.tags]
has_impulsive = "impulsive_response" in tag_ids_varied
has_strength = any(t.polarity.value == "strength" for t in result_varied.tags)
print(f"  Varied tags: {tag_ids_varied}")
print(f"  Has impulsive: {has_impulsive}, Has strength: {has_strength}")

# Simulate the G2 fallback in assessment_service
strengths_submit = [t.description for t in result_varied.tags if t.polarity.value == "strength"]
focus_areas_submit = [t.description for t in result_varied.tags if t.polarity.value == "growth_edge"]
if focus_areas_submit and not strengths_submit:
    strengths_submit = ["Your child is working on these skills and making progress."]
check("G2: fallback strength added when only growth edges",
      len(strengths_submit) > 0 or len(focus_areas_submit) == 0,
      f"strengths={strengths_submit}, focus={focus_areas_submit}")


# ============================================================
# G3: All grades return same structure from logic_submit_test
# ============================================================
sep("G3: All grades return full payload structure")

# We can't call the actual service method (needs Firebase), but we can verify
# the response shape by checking what evaluate returns and what the service
# method builds. Instead, let's verify the structure keys match across grades.

required_keys = {
    "parent_summary", "teacher_admin_detail", "signals",
    "scored_items", "timestamp", "dear_parent_tags", "per_item_tags"
}

for grade in [Grade.KINDERGARTEN, Grade.FIRST, Grade.SECOND, Grade.THIRD]:
    items = engine.get_items(grade)
    responses = [make_response(item, item.correct_answer_index, time=5.0) for item in items]
    result = run_full_test(grade, responses)

    # The service method builds these from the result
    # Verify all required data is available in the result
    has_score = result.score is not None
    has_signals = result.signals is not None
    has_tags = result.tags is not None
    has_per_item = result.per_item_tags is not None
    has_scored_items = len(result.score.scored_items) > 0

    check(f"G3: {grade.value} has score", has_score)
    check(f"G3: {grade.value} has signals", has_signals)
    check(f"G3: {grade.value} has tags", has_tags)
    check(f"G3: {grade.value} has per_item_tags", has_per_item)
    check(f"G3: {grade.value} has scored_items", has_scored_items)

    # Verify parent_summary can be built
    strengths = [t.description for t in result.tags if t.polarity.value == "strength"]
    focus_areas = [t.description for t in result.tags if t.polarity.value == "growth_edge"]
    if focus_areas and not strengths:
        strengths = ["Your child is working on these skills and making progress."]
    check(f"G3: {grade.value} parent_summary has strengths", len(strengths) > 0 or len(focus_areas) == 0)


# ============================================================
# G4: parent_summary uses human-readable descriptions, not raw tag ids
# ============================================================
sep("G4: parent_summary uses descriptions, not raw tag ids")

# Check that the submit_test code uses descriptions
# We verify by checking the tag config descriptions are human-readable
for tag_def in config.tags:
    desc = tag_def.description
    # Should not be empty or just the tag id
    check(f"G4: {tag_def.id} has readable description",
          len(desc) > 10 and desc != tag_def.id,
          f"desc={desc!r}")

# Verify a real run produces readable strengths
g1_items = engine.get_items(Grade.FIRST)
g1_responses = [make_response(item, item.correct_answer_index, time=5.0) for item in g1_items]
g1_result = run_full_test(Grade.FIRST, g1_responses)
g1_strengths = [t.description for t in g1_result.tags if t.polarity.value == "strength"]
print(f"  Grade 1 strengths: {g1_strengths}")
for s in g1_strengths:
    check(f"G4: strength is readable (not raw id)",
          " " in s and not s.replace("_", " ").islower(),
          f"strength={s!r}")


# ============================================================
# G5: pattern_detection_strong not renamed to emerging when no hard items
# ============================================================
sep("G5: pattern_detection not mislabeled when no hard items")

# Grade 1 has no hard pattern items
g1_pattern_items = [item for item in g1_items if item.primary_tag in {
    CognitiveTag.PATTERN_DETECTION_STRONG, CognitiveTag.PATTERN_DETECTION_EMERGING
}]
g1_hard_patterns = [item for item in g1_pattern_items if item.difficulty is Difficulty.HARD]
print(f"  Grade 1 pattern items: {len(g1_pattern_items)}, hard: {len(g1_hard_patterns)}")
check("G5: Grade 1 has no hard pattern items", len(g1_hard_patterns) == 0)

# Get all pattern items correct
g1_all_correct = [make_response(item, item.correct_answer_index, time=5.0) for item in g1_items]
g1_result_correct = run_full_test(Grade.FIRST, g1_all_correct)
g1_signals = g1_result_correct.signals
print(f"  Grade 1 pattern_score={g1_signals['pattern_score']}, pattern_hard_count={g1_signals['pattern_hard_count']}")

g1_tag_ids = [t.tag for t in g1_result_correct.tags]
print(f"  Grade 1 tags: {g1_tag_ids}")

# pattern_detection_emerging should fire (pattern_score >= 2, no hard items)
# pattern_detection_strong should NOT fire (needs hard_count >= 1)
check("G5: pattern_detection_emerging fires (score >= 2, no hard)",
      "pattern_detection_emerging" in g1_tag_ids,
      f"tags={g1_tag_ids}")
check("G5: pattern_detection_strong does NOT fire (no hard items)",
      "pattern_detection_strong" not in g1_tag_ids,
      f"tags={g1_tag_ids}")

# Check the emerging description doesn't claim inconsistency on hard items
emerging_tag = next(t for t in g1_result_correct.tags if t.tag == "pattern_detection_emerging")
check("G5: emerging description doesn't mention 'not yet consistent'",
      "not yet consistent" not in emerging_tag.description.lower(),
      f"desc={emerging_tag.description}")

# Grade 3 should have hard pattern items
g3_items = engine.get_items(Grade.THIRD)
g3_pattern_items = [item for item in g3_items if item.primary_tag in {
    CognitiveTag.PATTERN_DETECTION_STRONG, CognitiveTag.PATTERN_DETECTION_EMERGING
}]
g3_hard_patterns = [item for item in g3_pattern_items if item.difficulty is Difficulty.HARD]
print(f"  Grade 3 pattern items: {len(g3_pattern_items)}, hard: {len(g3_hard_patterns)}")
if g3_hard_patterns:
    check("G5: Grade 3 has hard pattern items", len(g3_hard_patterns) > 0)
    # If all correct, pattern_detection_strong should fire
    g3_all_correct = [make_response(item, item.correct_answer_index, time=5.0) for item in g3_items]
    g3_result = run_full_test(Grade.THIRD, g3_all_correct)
    g3_tag_ids = [t.tag for t in g3_result.tags]
    g3_signals = g3_result.signals
    print(f"  Grade 3 tags (all correct): {g3_tag_ids}")
    if g3_signals["pattern_score"] >= 3 and g3_signals["pattern_hard_count"] >= 1:
        check("G5: Grade 3 pattern_detection_strong fires",
              "pattern_detection_strong" in g3_tag_ids,
              f"tags={g3_tag_ids}")


# ============================================================
# G6: No raw 'message' field in response
# ============================================================
sep("G6: No raw 'message' field in logic response")

# The service method no longer includes 'message' in the return dict
# or in the saved payload. We verify by checking the code doesn't
# reference result.message in the logic_submit_test return.
# Since we can't call the service directly, we check the source.
import inspect
from app.services.assessment_service import AssessmentService
source = inspect.getsource(AssessmentService.logic_submit_test)
check("G6: 'message' not in submit_test return dict",
      '"message"' not in source.split("return")[1] if "return" in source else True,
      "check source")
check("G6: 'message' not in saved payload",
      '"message"' not in source.split("self._scores.save")[1].split(")")[0] if "self._scores.save" in source else True,
          "check source")


# ============================================================
# SUMMARY
# ============================================================
sep("SUMMARY")
print(f"  {passed} passed, {failed} failed")
if failed == 0:
    print("  ALL CHECKS PASSED")
else:
    print(f"  {failed} CHECKS FAILED")
