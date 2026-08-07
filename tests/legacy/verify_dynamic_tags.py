"""
End-to-end dynamic verification: simulate REAL API payloads for all 4 tests,
confirm tags are computed dynamically and correctly from the actual data.
"""
from tagging_engine import (
    tag_logic_test, tag_spelling_test, tag_speaking_test, tag_comprehension_test,
    derive_logic_signals, derive_spelling_signals, derive_speaking_signals, derive_comprehension_signals,
)
from logic_assessment import ALL_LOGIC_ITEMS
from main import COMPREHENSION_QUESTION_TYPES

def sep(t):
    print(f"\n{'='*70}\n  {t}\n{'='*70}")

# Build items_lookup exactly like main.py does
items_lookup = {
    item.item_id: {
        "correct_answer_index": item.correct_answer_index,
        "expected_latency_seconds": item.expected_latency_seconds,
        "item_type": item.item_type,
    }
    for item in ALL_LOGIC_ITEMS
}

all_ok = True

# =============================================================================
# 1. LOGIC — simulate POST /logic/submit_test/ payload
# =============================================================================
sep("1. LOGIC QUEST — Dynamic from real API payload")

# Simulate a Kindergarten child taking the test
logic_payload = [
    {"item_id": "k1_1", "selected_answer_index": 1, "response_time_seconds": 15, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_2", "selected_answer_index": 1, "response_time_seconds": 18, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_3", "selected_answer_index": 2, "response_time_seconds": 12, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_4", "selected_answer_index": 1, "response_time_seconds": 10, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_5", "selected_answer_index": 0, "response_time_seconds": 14, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_6", "selected_answer_index": 1, "response_time_seconds": 22, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_7", "selected_answer_index": 1, "response_time_seconds": 16, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_8", "selected_answer_index": 2, "response_time_seconds": 35, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_9", "selected_answer_index": 2, "response_time_seconds": 20, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_10", "selected_answer_index": 1, "response_time_seconds": 18, "attempts": 1, "self_corrected": False},
]

# Verify each item_id exists in lookup
missing_items = [r["item_id"] for r in logic_payload if r["item_id"] not in items_lookup]
if missing_items:
    print(f"  FAIL: item_ids not found in lookup: {missing_items}")
    all_ok = False
else:
    print(f"  All {len(logic_payload)} item_ids found in ALL_LOGIC_ITEMS lookup")

# Compute signals
signals = derive_logic_signals(logic_payload, items_lookup)
print(f"  Signals computed dynamically:")
for k, v in signals.items():
    if not k.startswith("_"):
        print(f"    {k:40s} = {v}")

# Verify correctness manually
correct = 0
for r in logic_payload:
    item = items_lookup[r["item_id"]]
    is_correct = r["selected_answer_index"] == item["correct_answer_index"]
    if is_correct:
        correct += 1
print(f"  Manual check: {correct}/{len(logic_payload)} correct = {correct/len(logic_payload)*100}%")

tags = tag_logic_test(logic_payload, items_lookup)
print(f"  Tags emitted: {len(tags)}")
for t in tags:
    print(f"    [{t['confidence'].upper():4s}] {t['id']:42s} ({t['polarity']})")
    print(f"           evidence: {t.get('evidence', {})}")

# Verify tags match expected for 90% score
tag_ids = [t["id"] for t in tags]
expected = ["pattern_detection_strong", "relational_reasoning_present"]
if set(expected).issubset(set(tag_ids)):
    print(f"  PASS: Expected tags present")
else:
    print(f"  FAIL: Missing {set(expected) - set(tag_ids)}")
    all_ok = False


# =============================================================================
# 2. SPELLING — simulate POST /submit_words/ payload
# =============================================================================
sep("2. WORD WIZARD — Dynamic from real API payload")

# Simulate what main.py builds: results list after scoring
spelling_payload = [
    {"word": "cat", "user_input": "cat", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 8, "hints_used": 0},
    {"word": "mat", "user_input": "mat", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 7, "hints_used": 0},
    {"word": "sit", "user_input": "sit", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 6, "hints_used": 0},
    {"word": "pot", "user_input": "pot", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 7, "hints_used": 0},
    {"word": "cup", "user_input": "cup", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 8, "hints_used": 0},
    {"word": "to", "user_input": "to", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
    {"word": "me", "user_input": "me", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
    {"word": "he", "user_input": "he", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
    {"word": "see", "user_input": "see", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 4, "hints_used": 0},
    {"word": "go", "user_input": "go", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
]

signals = derive_spelling_signals(spelling_payload, "Kindergarten")
print(f"  Signals computed dynamically:")
for k, v in signals.items():
    if not k.startswith("_"):
        print(f"    {k:40s} = {v}")

# Manual verify
correct_words = sum(1 for r in spelling_payload if r["points"] == r["max_points"])
print(f"  Manual check: {correct_words}/{len(spelling_payload)} words correct")

tags = tag_spelling_test(spelling_payload, "Kindergarten")
print(f"  Tags emitted: {len(tags)}")
for t in tags:
    print(f"    [{t['confidence'].upper():4s}] {t['id']:42s} ({t['polarity']})")
    print(f"           evidence: {t.get('evidence', {})}")

tag_ids = [t["id"] for t in tags]
expected = ["phonetic_strategy_strong", "vowel_accuracy_strong", "digraph_blend_competent",
            "sight_word_recognition_strong", "confident_attempt"]
if set(expected).issubset(set(tag_ids)):
    print(f"  PASS: All expected strength tags present")
else:
    print(f"  FAIL: Missing {set(expected) - set(tag_ids)}")
    all_ok = False


# =============================================================================
# 3. SPEAKING — simulate POST /speaking/submit/ payload (with enrichment)
# =============================================================================
sep("3. VOICE CHALLENGE — Dynamic from real API payload")

# Simulate what main.py builds: enriched results with difficulty from sentence_map
speaking_payload = [
    {"sentence_id": "k1", "status": "Answered", "pronunciation": {"score": 90}, "fluency": {"score": 85}, "overall": {"score": 88}, "difficulty": "easy"},
    {"sentence_id": "k2", "status": "Answered", "pronunciation": {"score": 88}, "fluency": {"score": 82}, "overall": {"score": 85}, "difficulty": "easy"},
    {"sentence_id": "k3", "status": "Answered", "pronunciation": {"score": 92}, "fluency": {"score": 88}, "overall": {"score": 90}, "difficulty": "easy"},
    {"sentence_id": "k4", "status": "Answered", "pronunciation": {"score": 85}, "fluency": {"score": 80}, "overall": {"score": 83}, "difficulty": "medium"},
]

signals = derive_speaking_signals(speaking_payload)
print(f"  Signals computed dynamically:")
for k, v in signals.items():
    if not k.startswith("_"):
        print(f"    {k:40s} = {v}")

# Manual verify
answered = [r for r in speaking_payload if r["status"] == "Answered"]
avg_pron = sum(r["pronunciation"]["score"] for r in answered) / len(answered) / 100
avg_flu = sum(r["fluency"]["score"] for r in answered) / len(answered) / 100
print(f"  Manual check: avg_pronunciation={avg_pron:.3f}, avg_fluency={avg_flu:.3f}")
print(f"  Manual check: {len(answered)} answered (min 3 required)")

tags = tag_speaking_test(speaking_payload)
print(f"  Tags emitted: {len(tags)}")
for t in tags:
    print(f"    [{t['confidence'].upper():4s}] {t['id']:42s} ({t['polarity']})")
    print(f"           evidence: {t.get('evidence', {})}")

tag_ids = [t["id"] for t in tags]
if "expressive_fluency_strong" in tag_ids and "pronunciation_accurate" in tag_ids:
    print(f"  PASS: Strong speaker tags present")
else:
    print(f"  FAIL: Missing strength tags")
    all_ok = False


# =============================================================================
# 4. COMPREHENSION — simulate POST /comprehension/submit/ payload
# =============================================================================
sep("4. STORY EXPLORER — Dynamic from real API payload")

# Simulate what main.py builds: results list with story questions
comprehension_payload = [
    {
        "story_id": "k_story1",
        "story_title": "The Friendly Dog",
        "questions": [
            {"question_id": "k1_q1", "is_correct": True},
            {"question_id": "k1_q2", "is_correct": True},
            {"question_id": "k1_q3", "is_correct": True},
            {"question_id": "k1_q4", "is_correct": True},
        ]
    },
    {
        "story_id": "k_story2",
        "story_title": "The Magic Garden",
        "questions": [
            {"question_id": "k2_q1", "is_correct": True},
            {"question_id": "k2_q2", "is_correct": True},
            {"question_id": "k2_q3", "is_correct": True},
            {"question_id": "k2_q4", "is_correct": False},
        ]
    }
]

# Verify question_ids exist in COMPREHENSION_QUESTION_TYPES
all_qids = []
for story in comprehension_payload:
    for q in story["questions"]:
        all_qids.append(q["question_id"])
missing_types = [qid for qid in all_qids if qid not in COMPREHENSION_QUESTION_TYPES]
if missing_types:
    print(f"  NOTE: question_ids not in mapping (will default to 'literal'): {missing_types}")
else:
    print(f"  All {len(all_qids)} question_ids found in COMPREHENSION_QUESTION_TYPES")

# Show the type mapping
print(f"  Question type mapping:")
for qid in all_qids:
    qtype = COMPREHENSION_QUESTION_TYPES.get(qid, "literal (default)")
    print(f"    {qid:15s} → {qtype}")

signals = derive_comprehension_signals(comprehension_payload, COMPREHENSION_QUESTION_TYPES)
print(f"  Signals computed dynamically:")
for k, v in signals.items():
    if not k.startswith("_"):
        print(f"    {k:40s} = {v}")

# Manual verify
total_correct = sum(1 for s in comprehension_payload for q in s["questions"] if q["is_correct"])
total_q = sum(len(s["questions"]) for s in comprehension_payload)
print(f"  Manual check: {total_correct}/{total_q} correct = {total_correct/total_q*100}%")

tags = tag_comprehension_test(comprehension_payload, COMPREHENSION_QUESTION_TYPES)
print(f"  Tags emitted: {len(tags)}")
for t in tags:
    print(f"    [{t['confidence'].upper():4s}] {t['id']:42s} ({t['polarity']})")
    print(f"           evidence: {t.get('evidence', {})}")

tag_ids = [t["id"] for t in tags]
if "literal_comprehension_strong" in tag_ids and "listening_comprehension_strong" in tag_ids:
    print(f"  PASS: Strong listener tags present")
else:
    print(f"  FAIL: Missing expected tags")
    all_ok = False


# =============================================================================
# SUMMARY
# =============================================================================
sep("FINAL RESULT")
if all_ok:
    print("  ALL 4 TESTS — Tags computed dynamically and correctly!")
    print()
    print("  Logic Quest:       tags from raw responses + item metadata")
    print("  Word Wizard:       tags from scored word results + grade")
    print("  Voice Challenge:   tags from scored sentences + difficulty")
    print("  Story Explorer:    tags from question results + type mapping")
    print()
    print("  Every tag value is derived from the actual submitted data.")
    print("  No hardcoded values. No AI. Pure deterministic rules.")
else:
    print("  SOME TESTS FAILED — check output above")
