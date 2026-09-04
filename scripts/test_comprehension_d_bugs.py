"""Comprehensive verification of comprehension Part 2 bug fixes (D1-D9)."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.enums import Grade, TestType, QuestionType
from app.domain.models import ComprehensionResponse
from app.engines.registry import comprehension_engine
from app.engines.comprehension.scorer import LEVEL_BANDS
from app.tagging.config_loader import load_tag_config, clear_cache

clear_cache()

engine = comprehension_engine()

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


def make_responses(grade, override=None):
    items = engine.get_items(grade)
    responses = []
    for story in items:
        for q in story.questions:
            idx = override.get(q.question_id, q.correct_index) if override else q.correct_index
            responses.append(ComprehensionResponse(
                item_id=q.question_id, question_id=q.question_id,
                selected_index=idx, response_time_seconds=5.0,
            ))
    return responses, items


def run_eval(grade, responses):
    items = engine.get_items(grade)
    return engine.evaluate("test-child", grade, responses, items=items)


# ============================================================
# D1: Grade 2 vocabulary question is a real vocabulary question
# ============================================================
sep("D1: Grade 2 vocabulary question tests word meaning")

g2_items = engine.get_items(Grade.SECOND)
vocab_qs = [q for s in g2_items for q in s.questions if q.question_type.value == "vocabulary"]
print(f"  Grade 2 vocab questions: {len(vocab_qs)}")
for q in vocab_qs:
    print(f"  Question: {q.question}")
    check("D1: vocab question asks about word meaning (not a fact)",
          "what does" in q.question.lower() or "mean" in q.question.lower(),
          f"question={q.question}")
    check("D1: vocab question is not about ribbon color",
          "ribbon" not in q.question.lower(),
          f"question={q.question}")


# ============================================================
# D2: Grade 3 with 2/3 inference gets an emerging tag
# ============================================================
sep("D2: Inference emerging tag fires at middle threshold")

g3_items = engine.get_items(Grade.THIRD)
inf_qs = [q for s in g3_items for q in s.questions if q.question_type.value == "inferential"]
print(f"  Grade 3 inference questions: {len(inf_qs)}")

# Get 2 of 3 inference correct, all others correct
override = {}
for s in g3_items:
    for q in s.questions:
        override[q.question_id] = q.correct_index
# Make 1 inference wrong
if len(inf_qs) >= 3:
    override[inf_qs[0].question_id] = (inf_qs[0].correct_index + 1) % len(inf_qs[0].options)

responses, _ = make_responses(Grade.THIRD, override)
result = run_eval(Grade.THIRD, responses)
signals = result.signals
tags = [t.tag for t in result.tags]
print(f"  Inference accuracy: {signals['inferential_accuracy']}, attempted: {signals['inferential_attempted']}")
print(f"  Tags: {tags}")

check("D2: inferential_comprehension_emerging fires at 2/3 (67%)",
      "inferential_comprehension_emerging" in tags,
      f"tags={tags}")
check("D2: inferential_comprehension_strong does NOT fire at 2/3",
      "inferential_comprehension_strong" not in tags,
      f"tags={tags}")

# Get 3/3 inference correct -> strong should fire
override2 = {}
for s in g3_items:
    for q in s.questions:
        override2[q.question_id] = q.correct_index
responses2, _ = make_responses(Grade.THIRD, override2)
result2 = run_eval(Grade.THIRD, responses2)
tags2 = [t.tag for t in result2.tags]
print(f"  All correct tags: {tags2}")
check("D2: inferential_comprehension_strong fires at 3/3 (100%)",
      "inferential_comprehension_strong" in tags2,
      f"tags={tags2}")
check("D2: inferential_comprehension_emerging does NOT fire at 3/3",
      "inferential_comprehension_emerging" not in tags2,
      f"tags={tags2}")


# ============================================================
# D3: Kindergarten inference question is a real inference question
# ============================================================
sep("D3: Kindergarten inference question requires reasoning")

k_items = engine.get_items(Grade.KINDERGARTEN)
inf_qs_k = [q for s in k_items for q in s.questions if q.question_type.value == "inferential"]
print(f"  K inference questions: {len(inf_qs_k)}")
for q in inf_qs_k:
    print(f"  Question: {q.question}")
    check("D3: K inference is NOT 'what was NOT mentioned'",
          "not mentioned" not in q.question.lower(),
          f"question={q.question}")
    check("D3: K inference asks about feelings or reasoning",
          "feel" in q.question.lower() or "why" in q.question.lower() or "think" in q.question.lower(),
          f"question={q.question}")


# ============================================================
# D4: Repeating pattern detection signal exists
# ============================================================
sep("D4: Repeating pattern detection signal")

# Normal responses - no pattern
responses_normal, _ = make_responses(Grade.KINDERGARTEN)
result_normal = run_eval(Grade.KINDERGARTEN, responses_normal)
signals_normal = result_normal.signals
print(f"  Normal: repeating_pattern_detected={signals_normal.get('repeating_pattern_detected')}")
check("D4: repeating_pattern_detected signal exists",
      "repeating_pattern_detected" in signals_normal,
      f"signals={list(signals_normal.keys())}")
check("D4: normal responses don't trigger pattern detection",
      signals_normal.get("repeating_pattern_detected") == False,
      f"value={signals_normal.get('repeating_pattern_detected')}")

# Pattern responses - always pick index 0
k_items = engine.get_items(Grade.KINDERGARTEN)
pattern_responses = []
for s in k_items:
    for q in s.questions:
        pattern_responses.append(ComprehensionResponse(
            item_id=q.question_id, question_id=q.question_id,
            selected_index=0, response_time_seconds=5.0,
        ))
result_pattern = run_eval(Grade.KINDERGARTEN, pattern_responses)
signals_pattern = result_pattern.signals
print(f"  Pattern (all 0): repeating_pattern_detected={signals_pattern.get('repeating_pattern_detected')}")
check("D4: all-same-index triggers pattern detection",
      signals_pattern.get("repeating_pattern_detected") == True,
      f"value={signals_pattern.get('repeating_pattern_detected')}")


# ============================================================
# D5: No identity labels in level bands
# ============================================================
sep("D5: No identity labels in level bands")

from app.engines.comprehension.scorer import LEVEL_BANDS as COMP_BANDS
from app.engines.logic.scorer import LEVEL_BANDS as LOGIC_BANDS
from app.engines.speaking.scorer import LEVEL_BANDS as SPEAKING_BANDS

identity_words = ["reader", "thinker", "speaker", "excellent", "good", "developing", "needs practice", "exceptional", "advanced", "emerging"]

for name, bands in [("comprehension", COMP_BANDS), ("logic", LOGIC_BANDS), ("speaking", SPEAKING_BANDS)]:
    for _, label in bands:
        label_lower = label.lower()
        has_identity = any(word in label_lower for word in identity_words)
        check(f"D5: {name} level '{label}' has no identity label",
              not has_identity,
              f"label={label}")


# ============================================================
# D7: Grade 2 story doesn't say blue ribbon for second place
# ============================================================
sep("D7: Grade 2 story ribbon color fix")

g2_items = engine.get_items(Grade.SECOND)
story2_text = g2_items[1].story_text
print(f"  Story text contains 'red ribbon': {'red ribbon' in story2_text}")
print(f"  Story text contains 'blue ribbon': {'blue ribbon' in story2_text}")
check("D7: story says 'red ribbon' not 'blue ribbon'",
      "red ribbon" in story2_text and "blue ribbon" not in story2_text,
      "check story text")


# ============================================================
# D8: overall_score doesn't have decimal
# ============================================================
sep("D8: overall_score formatting (no decimal)")

import inspect
from app.services.assessment_service import AssessmentService
source = inspect.getsource(AssessmentService.comprehension_complete_result)
check("D8: overall_score uses int() for max_score",
      "int(latest.get('max_score'" in source,
          "check source")
check("D8: overall_score does NOT use raw max_score",
      "f\"{latest.get('correct_answers', 0)}/{latest.get('max_score'" not in source,
      "check source")


# ============================================================
# D9: Each grade has at least 3 inference questions
# ============================================================
sep("D9: At least 3 inference questions per grade")

for grade in [Grade.KINDERGARTEN, Grade.FIRST, Grade.SECOND, Grade.THIRD]:
    items = engine.get_items(grade)
    inf_count = sum(1 for s in items for q in s.questions if q.question_type.value == "inferential")
    total = sum(len(s.questions) for s in items)
    print(f"  {grade.value}: {inf_count} inference / {total} total")
    check(f"D9: {grade.value} has >= 3 inference questions",
          inf_count >= 3,
          f"inf_count={inf_count}")


# ============================================================
# CROSS: All grades have vocab + inference + well-distributed positions
# ============================================================
sep("CROSS: Final sanity check across all grades")

for grade in [Grade.KINDERGARTEN, Grade.FIRST, Grade.SECOND, Grade.THIRD]:
    items = engine.get_items(grade)
    positions = [q.correct_index for s in items for q in s.questions]
    types = {}
    for s in items:
        for q in s.questions:
            types[q.question_type.value] = types.get(q.question_type.value, 0) + 1

    n = len(positions)
    max_count = max(positions.count(i) for i in range(4))
    max_ratio = max_count / n

    print(f"  {grade.value}: {n} questions, types={types}, max_pos_ratio={max_ratio:.2f}")
    check(f"CROSS: {grade.value} has vocab question", types.get("vocabulary", 0) >= 1)
    check(f"CROSS: {grade.value} has >= 3 inference", types.get("inferential", 0) >= 3)
    check(f"CROSS: {grade.value} positions well distributed", max_ratio <= 0.5)

    # Run full evaluation with all correct
    responses, _ = make_responses(grade)
    result = run_eval(grade, responses)
    tag_ids = [t.tag for t in result.tags]
    print(f"    Tags (all correct): {tag_ids}")

    # Verify no raw tag ids in strengths
    strengths = [t.description for t in result.tags if t.polarity.value == "strength"]
    for s in strengths:
        check(f"CROSS: {grade.value} strength is readable",
              "your child" in s.lower(),
              f"strength={s!r}")


# ============================================================
# SUMMARY
# ============================================================
sep("SUMMARY")
print(f"  {passed} passed, {failed} failed")
if failed == 0:
    print("  ALL CHECKS PASSED")
else:
    print(f"  {failed} CHECKS FAILED")
