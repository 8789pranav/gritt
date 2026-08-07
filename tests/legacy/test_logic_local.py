"""Test Logic Quest questions and scoring locally (no server needed)."""
import json
from logic_assessment import (
    ALL_LOGIC_ITEMS, get_items_by_grade, GradeLevel,
    score_response, aggregate_test_results, StudentResponse,
)
from tagging_engine import tag_logic_test, tag_logic_per_item

print("=" * 70)
print("LOGIC QUEST — LOCAL TEST (QUESTIONS + SCORING)")
print("=" * 70)

# ── 1. Verify question bank ──────────────────────────────────────────────
print("\n1. QUESTION BANK VERIFICATION")
print("-" * 70)

grade_map = {
    "Kindergarten": GradeLevel.KINDERGARTEN_1,
    "1st Grade": GradeLevel.GRADE_1_2,
    "2nd Grade": GradeLevel.GRADE_2_3,
    "3rd Grade": GradeLevel.GRADE_3_4,
}

expected_counts = {
    "Kindergarten": 8,
    "1st Grade": 8,
    "2nd Grade": 8,
    "3rd Grade": 8,
}

all_pass = True
for grade_name, grade_level in grade_map.items():
    items = get_items_by_grade(grade_level)
    count = len(items)
    expected = expected_counts[grade_name]
    status = "PASS" if count == expected else "FAIL"
    if count != expected:
        all_pass = False
    print(f"\n  {grade_name}: {count} items (expected {expected}) [{status}]")
    for item in items:
        tag = item.primary_tag.value
        print(f"    {item.item_number}: [{item.item_type}] {item.question_text[:55]}...")
        print(f"      Tag: {tag} | Difficulty: {item.difficulty} | Correct: idx={item.correct_answer_index}")

# ── 2. Test scoring with all-correct answers ─────────────────────────────
print("\n\n2. SCORING TEST — ALL CORRECT ANSWERS")
print("-" * 70)

for grade_name, grade_level in grade_map.items():
    items = get_items_by_grade(grade_level)
    responses = []
    for item in items:
        responses.append(StudentResponse(
            student_id="test_child",
            item_id=item.item_id,
            selected_answer_index=item.correct_answer_index,
            response_time_seconds=item.expected_latency_seconds,
        ))

    result = aggregate_test_results(responses, grade_level)
    print(f"\n  {grade_name}:")
    print(f"    Score: {result.total_correct}/{result.total_items} ({result.score_percentage:.0f}%)")
    print(f"    Final Tags: {[t.value for t in result.final_tags]}")
    for to in result.tag_outputs:
        print(f"      {to.tag.value}: {to.evidence}")

    # Also test tagging engine
    items_lookup = {
        item.item_id: {
            "correct_answer_index": item.correct_answer_index,
            "expected_latency_seconds": item.expected_latency_seconds,
            "item_type": item.item_type,
            "difficulty": item.difficulty,
            "primary_tag": item.primary_tag.value,
            "conditional_tags": {k: v.value for k, v in item.conditional_tags.items()},
            "item_number": item.item_number,
        }
        for item in items
    }
    raw_responses = [
        {
            "item_id": item.item_id,
            "selected_answer_index": item.correct_answer_index,
            "response_time_seconds": item.expected_latency_seconds,
            "attempts": 1,
            "self_corrected": False,
        }
        for item in items
    ]
    dp_tags = tag_logic_test(raw_responses, items_lookup)
    print(f"    Dear Parent Tags: {[t['id'] for t in dp_tags]}")

    per_item = tag_logic_per_item(raw_responses, items_lookup)
    answered = sum(1 for p in per_item if p["answered"])
    correct = sum(1 for p in per_item if p["is_correct"])
    print(f"    Per-item tags: {answered} answered, {correct} correct")

# ── 3. Test scoring with all-wrong answers ───────────────────────────────
print("\n\n3. SCORING TEST — ALL WRONG ANSWERS")
print("-" * 70)

for grade_name, grade_level in grade_map.items():
    items = get_items_by_grade(grade_level)
    responses = []
    for item in items:
        wrong_idx = (item.correct_answer_index + 1) % 4
        responses.append(StudentResponse(
            student_id="test_child",
            item_id=item.item_id,
            selected_answer_index=wrong_idx,
            response_time_seconds=item.expected_latency_seconds,
        ))

    result = aggregate_test_results(responses, grade_level)
    print(f"\n  {grade_name}:")
    print(f"    Score: {result.total_correct}/{result.total_items} ({result.score_percentage:.0f}%)")
    print(f"    Final Tags: {[t.value for t in result.final_tags]}")

# ── 4. Verify item IDs are unique ────────────────────────────────────────
print("\n\n4. ITEM ID UNIQUENESS CHECK")
print("-" * 70)
ids = [item.item_id for item in ALL_LOGIC_ITEMS]
duplicates = [iid for iid in ids if ids.count(iid) > 1]
if duplicates:
    print(f"  FAIL: Duplicate item_ids found: {set(duplicates)}")
    all_pass = False
else:
    print(f"  PASS: All {len(ids)} item_ids are unique")

# ── 5. Verify all items have 4 options ───────────────────────────────────
print("\n\n5. OPTION COUNT CHECK")
print("-" * 70)
bad_items = [item for item in ALL_LOGIC_ITEMS if len(item.options) != 4]
if bad_items:
    print(f"  FAIL: {len(bad_items)} items don't have exactly 4 options:")
    for item in bad_items:
        print(f"    {item.item_number}: {len(item.options)} options")
    all_pass = False
else:
    print(f"  PASS: All {len(ALL_LOGIC_ITEMS)} items have exactly 4 options")

# ── Summary ──────────────────────────────────────────────────────────────
print("\n\n" + "=" * 70)
if all_pass:
    print("ALL TESTS PASSED")
else:
    print("SOME TESTS FAILED — see above")
print("=" * 70)
