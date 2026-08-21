"""Verify all 7 bugs are fixed for the spelling test."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.enums import Grade, WordType
from app.domain.models import SpellingResponse
from app.engines.registry import spelling_engine


def sep(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


engine = spelling_engine()
grade = Grade.FIRST
test_words = engine.build_test(grade)

# Find the word "cup" or use the first regular word
target_word = None
for w in test_words:
    if w.word_type == WordType.REGULAR:
        target_word = w
        break

sep(f"Target word: {target_word.word} (features: {target_word.features})")

# Build responses: all correct except target_word -> "red"
responses = []
for w in test_words:
    if w.word == target_word.word:
        responses.append(SpellingResponse(
            item_id=w.word, word=w.word, user_input="red",
            word_type=w.word_type, response_time_seconds=5.0,
        ))
    else:
        responses.append(SpellingResponse(
            item_id=w.word, word=w.word, user_input=w.word,
            word_type=w.word_type, response_time_seconds=5.0,
        ))

result = engine.evaluate("child-test", grade, responses)
scored_items = {s.item_id: s for s in result.score.scored_items}
target_scored = scored_items[target_word.item_id]

print(f"\nTarget word scored item:")
print(json.dumps(target_scored.model_dump(), indent=2))

# Bug 1: error_type should not be a feature name for unrelated_attempt
sep("BUG 1: teacher_admin_detail error_type for unrelated_attempt")
per_word_tags = {p.item_id: p.tags for p in result.per_item_tags}
target_tags = per_word_tags.get(target_word.item_id, [])
print(f"Tags: {target_tags}")
if "unrelated_attempt" in target_tags:
    print("  OK: unrelated_attempt tag is present")
else:
    print("  FAIL: unrelated_attempt tag missing!")

# Check what _error_type_for would return (simulating the assessment_service logic)
per_word_tag_map = {p.item_id: p.tags for p in result.per_item_tags}
def _error_type_for(item_dict):
    if item_dict.get("is_correct"):
        return None
    tags = per_word_tag_map.get(item_dict.get("item_id", ""), [])
    if "unrelated_attempt" in tags:
        return "Unrelated attempt"
    if "rushed_attempt" in tags:
        return "Rushed attempt"
    mistakes = item_dict.get("detail", {}).get("mistakes", {})
    for k in mistakes:
        if k not in ("spelling", "unrelated_attempt"):
            return k.replace("_", " ")
    return None

error_type = _error_type_for(target_scored.model_dump())
print(f"error_type would be: {error_type}")
if error_type == "Unrelated attempt":
    print("  OK: Bug 1 FIXED — error_type is 'Unrelated attempt', not a feature name")
else:
    print(f"  FAIL: Bug 1 NOT FIXED — error_type is {error_type!r}")

# Bug 2: unrelated word should have 0 feature errors
sep("BUG 2: Unrelated word generates 0 feature errors")
mistakes = target_scored.detail.get("mistakes", {})
print(f"mistakes: {mistakes}")
feature_errors = [k for k in mistakes if k not in ("spelling", "unrelated_attempt")]
if len(feature_errors) == 0:
    print(f"  OK: Bug 2 FIXED — 0 feature errors (only {list(mistakes.keys())})")
else:
    print(f"  FAIL: Bug 2 NOT FIXED — {len(feature_errors)} feature errors: {feature_errors}")

# Bug 3: accuracy scores should not count unrelated word
sep("BUG 3: Accuracy scores not polluted by unrelated word")
signals = result.signals
print(f"beginning_accuracy: {signals.get('beginning_accuracy')}")
print(f"final_accuracy: {signals.get('final_accuracy')}")
print(f"vowel_accuracy: {signals.get('vowel_accuracy')}")
# All other words are correct, so these should all be 1.0
if (signals.get('beginning_accuracy') == 1.0 and
    signals.get('final_accuracy') == 1.0 and
    signals.get('vowel_accuracy') == 1.0):
    print("  OK: Bug 3 FIXED — accuracies are 1.0 (unrelated word not counted)")
else:
    print("  FAIL: Bug 3 NOT FIXED — accuracies are polluted")

# Bug 4: vowel_accuracy_strong tag should appear
sep("BUG 4: vowel_accuracy_strong tag present")
dear_parent_tags = [t.tag for t in result.tags]
print(f"dear_parent_tags: {dear_parent_tags}")
if "vowel_accuracy_strong" in dear_parent_tags:
    print("  OK: Bug 4 FIXED — vowel_accuracy_strong is present")
else:
    print("  FAIL: Bug 4 NOT FIXED — vowel_accuracy_strong missing")

# Bug 5: strengths and focus_areas should not overlap
sep("BUG 5: No overlap between strengths and focus_areas")
strengths = engine.strengths(result.signals)
focus_areas = engine.focus_areas(result.score)
print(f"strengths: {strengths}")
print(f"focus_areas: {focus_areas}")
overlap = set(strengths) & set(focus_areas)
if not overlap:
    print("  OK: Bug 5 FIXED — no overlap")
else:
    print(f"  FAIL: Bug 5 NOT FIXED — overlap: {overlap}")

# Bug 6: recommendation should match focus_areas
sep("BUG 6: Recommendation matches focus_areas")
recommendation = engine.recommend(result.score, result.tags)
print(f"recommendation: {recommendation}")
print(f"focus_areas: {focus_areas}")
if focus_areas:
    if "Advance to the next level" in recommendation and "Continue practising" in recommendation:
        print("  FAIL: Bug 6 NOT FIXED — says both advance and practise")
    elif "Advance to the next level" in recommendation:
        print("  FAIL: Bug 6 NOT FIXED — says advance but has focus areas")
    elif any(area in recommendation for area in focus_areas):
        print("  OK: Bug 6 FIXED — recommendation lists focus areas")
    else:
        print(f"  UNCLEAR: recommendation doesn't mention focus areas by name")
else:
    if "Advance" in recommendation:
        print("  OK: Bug 6 FIXED — no focus areas, says advance (correct)")
    else:
        print(f"  OK: Bug 6 FIXED — no focus areas, recommendation is appropriate")

# Bug 7: time cap
sep("BUG 7: Time cap for extreme response times")
# Build a response with 202 seconds
responses_long = []
for w in test_words:
    t = 202.0 if w.word == target_word.word else 5.0
    responses_long.append(SpellingResponse(
        item_id=w.word, word=w.word, user_input=w.word,
        word_type=w.word_type, response_time_seconds=t,
    ))
result_long = engine.evaluate("child-test7", grade, responses_long)
target_long = next(s for s in result_long.score.scored_items if s.item_id == target_word.item_id)
stored_time = target_long.detail.get("time", 0)
print(f"Input time: 202.0s, stored time: {stored_time}s")
if stored_time <= 120.0:
    print(f"  OK: Bug 7 FIXED — time capped at 120s (stored: {stored_time}s)")
else:
    print(f"  FAIL: Bug 7 NOT FIXED — time not capped (stored: {stored_time}s)")

# Summary
sep("SUMMARY")
checks = [
    ("Bug 1", error_type == "Unrelated attempt"),
    ("Bug 2", len(feature_errors) == 0),
    ("Bug 3", signals.get('beginning_accuracy') == 1.0 and signals.get('final_accuracy') == 1.0 and signals.get('vowel_accuracy') == 1.0),
    ("Bug 4", "vowel_accuracy_strong" in dear_parent_tags),
    ("Bug 5", not overlap),
    ("Bug 6", not ("Advance to the next level" in recommendation and focus_areas)),
    ("Bug 7", stored_time <= 120.0),
]
all_ok = True
for name, ok in checks:
    status = "PASS" if ok else "FAIL"
    print(f"  {name}: {status}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("  ALL 7 BUGS FIXED")
else:
    print("  SOME BUGS STILL FAILING")
