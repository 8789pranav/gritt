"""Verify L-D7 and G1 from the bug report.

L-D7: Grade 2, both load items wrong must give a growth edge.
G1: 2+ fast wrong answers must fire impulsive_response.
"""
import sys
sys.path.insert(0, "Z:/grittt")

from app.domain.enums import CognitiveTag, Grade
from app.engines.logic.engine import LogicEngine
from app.domain.models import LogicResponse

engine = LogicEngine()

passed = 0
failed = 0

def check(label, cond, extra=""):
    global passed, failed
    if cond:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label} {extra}")
        failed += 1


def make_response(item, selected, time=5.0):
    return LogicResponse(
        item_id=item.item_id,
        selected_answer_index=selected,
        response_time_seconds=time,
        attempts=1,
        self_corrected=False,
    )


print("=" * 60)
print("L-D7: Grade 2, both load items wrong = growth edge")
print("=" * 60)

g2_items = engine.get_items(Grade.SECOND)
load_items = [
    item for item in g2_items
    if item.primary_tag in {CognitiveTag.REASONING_UNDER_LOAD, CognitiveTag.REASONING_UNDER_LOAD_EMERGING}
]
print(f"  Load items at Grade 2: {len(load_items)}")
check("Grade 2 has at least 3 load items", len(load_items) >= 3, f"count={len(load_items)}")

# Answer all items: load items wrong, everything else correct
responses = []
for item in g2_items:
    if item.primary_tag in {CognitiveTag.REASONING_UNDER_LOAD, CognitiveTag.REASONING_UNDER_LOAD_EMERGING}:
        # Pick a wrong answer
        wrong = (item.correct_answer_index + 1) % len(item.options)
        responses.append(make_response(item, wrong, time=10.0))
    else:
        responses.append(make_response(item, item.correct_answer_index, time=10.0))

result = engine.evaluate("test_child", Grade.SECOND, responses)
tag_ids = [t.tag for t in result.tags]
print(f"  Tags: {tag_ids}")
print(f"  load_accuracy={result.signals.get('load_accuracy')}")
print(f"  load_items_count={result.signals.get('load_items_count')}")
print(f"  load_fails={result.signals.get('load_fails')}")

check("reasoning_under_load_emerging fires", "reasoning_under_load_emerging" in tag_ids, f"tags={tag_ids}")
check("reasoning_under_load (strength) does NOT fire", "reasoning_under_load" not in tag_ids, f"tags={tag_ids}")

growth_edges = [t for t in result.tags if t.polarity.value == "growth_edge"]
check("At least one growth edge present", len(growth_edges) > 0, f"tags={tag_ids}")


print()
print("=" * 60)
print("G1: 2+ fast wrong answers = impulsive_response")
print("=" * 60)

# Use Grade 3. Answer 3 questions wrong and fast (below half the median).
# Answer the rest correctly at normal speed.
g3_items = engine.get_items(Grade.THIRD)
responses = []
wrong_indices = [0, 1, 2]  # First 3 items wrong and fast
for i, item in enumerate(g3_items):
    if i in wrong_indices:
        wrong = (item.correct_answer_index + 1) % len(item.options)
        responses.append(make_response(item, wrong, time=2.0))  # Very fast
    else:
        responses.append(make_response(item, item.correct_answer_index, time=15.0))

result = engine.evaluate("test_child", Grade.THIRD, responses)
tag_ids = [t.tag for t in result.tags]
print(f"  Tags: {tag_ids}")
print(f"  fast_and_wrong_count={result.signals.get('fast_and_wrong_count')}")

check("impulsive_response fires on fast wrong answers", "impulsive_response" in tag_ids, f"tags={tag_ids}")
check("fast_and_wrong_count >= 2", result.signals.get("fast_and_wrong_count", 0) >= 2, f"count={result.signals.get('fast_and_wrong_count')}")


print()
print("=" * 60)
print("L-D8: Tags need min 3 questions + confidence scaling")
print("=" * 60)

# All correct at Grade 3 — every construct has exactly 3 items
g3_all_correct = [make_response(item, item.correct_answer_index, time=10.0) for item in g3_items]
result = engine.evaluate("test_child", Grade.THIRD, g3_all_correct)
print(f"  Tags: {[(t.tag, t.confidence.value) for t in result.tags]}")

for tag in result.tags:
    count_signal = {
        "pattern_detection_strong": "pattern_items_count",
        "relational_reasoning_present": "relational_items_count",
        "systematic_problem_solving": "systematic_items_count",
        "flexible_strategy_use": "flexibility_items_count",
        "reasoning_under_load": "load_items_count",
    }.get(tag.tag)
    if count_signal:
        count = result.signals.get(count_signal, 0)
        check(f"{tag.tag} backed by {count} items, confidence={tag.confidence.value}",
              count >= 3, f"count={count}")
        # With 3 items (fewer than 5), confidence should be medium, not high
        if count < 5:
            check(f"{tag.tag} confidence is medium (not high) for {count} items",
                  tag.confidence.value == "medium", f"confidence={tag.confidence.value}")


print()
print("=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 60)
sys.exit(1 if failed else 0)
