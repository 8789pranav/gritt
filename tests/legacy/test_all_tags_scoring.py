"""
Comprehensive test for ALL test activities: Word Wizard, Voice Challenge, Story Explorer, Logic Quest.
Tests scoring, signal derivation, and tag emission for each.
"""
from tagging_engine import (
    tag_logic_test, tag_spelling_test, tag_speaking_test, tag_comprehension_test,
    derive_logic_signals, derive_spelling_signals, derive_speaking_signals, derive_comprehension_signals,
    emit_tags,
)
from logic_assessment import (
    GradeLevel, StudentResponse, get_items_by_grade, aggregate_test_results, ALL_LOGIC_ITEMS,
)

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {label}")
    else:
        FAIL += 1
        print(f"  FAIL: {label} -- {detail}")


def tag_ids(tags):
    return [t["id"] for t in tags]


# =============================================================================
# 1. WORD WIZARD (Spelling)
# =============================================================================
print("\n" + "=" * 70)
print("WORD WIZARD (Spelling)")
print("=" * 70)

# Test 1a: All perfect spelling
print("\n-- Test 1a: All perfect spelling --")
perfect_results = [
    {"word": "cat", "user_input": "cat", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 5, "hints_used": 0},
    {"word": "dog", "user_input": "dog", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 4, "hints_used": 0},
    {"word": "the", "user_input": "the", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
    {"word": "said", "user_input": "said", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
]
signals = derive_spelling_signals(perfect_results, "Kindergarten")
tags = tag_spelling_test(perfect_results, "Kindergarten")
print(f"  Signals: {signals}")
print(f"  Tags: {tag_ids(tags)}")
check("beginning_accuracy = 1.0", signals["beginning_accuracy"] == 1.0, f"got {signals['beginning_accuracy']}")
check("final_accuracy = 1.0", signals["final_accuracy"] == 1.0, f"got {signals['final_accuracy']}")
check("vowel_error_count = 0", signals["vowel_error_count"] == 0)
check("sight_word_accuracy = 1.0", signals["sight_word_accuracy"] == 1.0)
check("phonetic_strategy_strong", "phonetic_strategy_strong" in tag_ids(tags), f"got {tag_ids(tags)}")
check("vowel_accuracy_strong", "vowel_accuracy_strong" in tag_ids(tags))
check("sight_word_recognition_strong", "sight_word_recognition_strong" in tag_ids(tags))
check("confident_attempt", "confident_attempt" in tag_ids(tags))
check("NO vowel_difficulty_emerging", "vowel_difficulty_emerging" not in tag_ids(tags))
check("NO rushed_spelling", "rushed_spelling" not in tag_ids(tags))

# Test 1b: Vowel errors
print("\n-- Test 1b: Vowel errors (2+ vowel mistakes) --")
vowel_error_results = [
    {"word": "cat", "user_input": "cot", "type": "regular", "points": 2, "max_points": 3, "mistakes": {"short_vowels": "a"}, "time": 5, "hints_used": 0},
    {"word": "pig", "user_input": "peg", "type": "regular", "points": 2, "max_points": 3, "mistakes": {"short_vowels": "i"}, "time": 5, "hints_used": 0},
    {"word": "the", "user_input": "the", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
]
signals = derive_spelling_signals(vowel_error_results, "Kindergarten")
tags = tag_spelling_test(vowel_error_results, "Kindergarten")
print(f"  Signals: vowel_error_count={signals['vowel_error_count']}, vowel_accuracy={signals['vowel_accuracy']}")
print(f"  Tags: {tag_ids(tags)}")
check("vowel_error_count >= 2", signals["vowel_error_count"] >= 2, f"got {signals['vowel_error_count']}")
check("vowel_difficulty_emerging", "vowel_difficulty_emerging" in tag_ids(tags), f"got {tag_ids(tags)}")
check("NO vowel_accuracy_strong", "vowel_accuracy_strong" not in tag_ids(tags))

# Test 1c: Rushed spelling (fast + wrong)
print("\n-- Test 1c: Rushed spelling (fast slips) --")
rushed_results = [
    {"word": "cat", "user_input": "ct", "type": "regular", "points": 1, "max_points": 3, "mistakes": {"short_vowels": "a"}, "time": 2, "hints_used": 0},
    {"word": "dog", "user_input": "dg", "type": "regular", "points": 1, "max_points": 3, "mistakes": {"short_vowels": "o"}, "time": 2, "hints_used": 0},
    {"word": "the", "user_input": "the", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
]
signals = derive_spelling_signals(rushed_results, "Kindergarten")
tags = tag_spelling_test(rushed_results, "Kindergarten")
print(f"  Signals: fast_slips={signals['fast_slips']}")
print(f"  Tags: {tag_ids(tags)}")
check("fast_slips >= 2", signals["fast_slips"] >= 2, f"got {signals['fast_slips']}")
check("rushed_spelling", "rushed_spelling" in tag_ids(tags), f"got {tag_ids(tags)}")

# Test 1d: Audio support benefit
print("\n-- Test 1d: Audio support benefit --")
audio_results = [
    {"word": "cat", "user_input": "cat", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 5, "hints_used": 1},
    {"word": "dog", "user_input": "dog", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 5, "hints_used": 0},
    {"word": "the", "user_input": "the", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
]
signals = derive_spelling_signals(audio_results, "Kindergarten")
tags = tag_spelling_test(audio_results, "Kindergarten")
check("improved_with_audio = True", signals["improved_with_audio"] == True)
check("audio_support_benefit", "audio_support_benefit" in tag_ids(tags), f"got {tag_ids(tags)}")


# =============================================================================
# 2. VOICE CHALLENGE (Speaking)
# =============================================================================
print("\n" + "=" * 70)
print("VOICE CHALLENGE (Speaking)")
print("=" * 70)

# Test 2a: Strong speaker (all high scores)
print("\n-- Test 2a: Strong speaker (all 90+) --")
strong_speaking = [
    {"sentence_id": "s1", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 90}, "pronunciation": {"score": 92}, "grammar": {"score": 88},
     "overall": {"score": 90}},
    {"sentence_id": "s2", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 88}, "pronunciation": {"score": 90}, "grammar": {"score": 85},
     "overall": {"score": 88}},
    {"sentence_id": "s3", "status": "Answered", "difficulty": "hard",
     "fluency": {"score": 85}, "pronunciation": {"score": 87}, "grammar": {"score": 82},
     "overall": {"score": 85}},
]
signals = derive_speaking_signals(strong_speaking)
tags = tag_speaking_test(strong_speaking)
print(f"  Signals: fluency={signals['avg_fluency']}, pron={signals['avg_pronunciation']}, prosody={signals['avg_prosody']}, hard={signals['hard_band_avg']}")
print(f"  Tags: {tag_ids(tags)}")
check("avg_fluency >= 0.8", signals["avg_fluency"] >= 0.8, f"got {signals['avg_fluency']}")
check("avg_pronunciation >= 0.85", signals["avg_pronunciation"] >= 0.85, f"got {signals['avg_pronunciation']}")
check("expressive_fluency_strong", "expressive_fluency_strong" in tag_ids(tags), f"got {tag_ids(tags)}")
check("pronunciation_accurate", "pronunciation_accurate" in tag_ids(tags))
check("prosody_strong", "prosody_strong" in tag_ids(tags))
check("complex_syntax_confident (hard=85)", "complex_syntax_confident" in tag_ids(tags))
check("NO expressive_fluency_emerging", "expressive_fluency_emerging" not in tag_ids(tags))
check("NO pronunciation_developing", "pronunciation_developing" not in tag_ids(tags))
check("NO prosody_emerging", "prosody_emerging" not in tag_ids(tags))

# Test 2b: Developing speaker (low scores)
print("\n-- Test 2b: Developing speaker (low scores) --")
weak_speaking = [
    {"sentence_id": "s1", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 50}, "pronunciation": {"score": 55}, "grammar": {"score": 45},
     "overall": {"score": 50}},
    {"sentence_id": "s2", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 55}, "pronunciation": {"score": 60}, "grammar": {"score": 50},
     "overall": {"score": 55}},
    {"sentence_id": "s3", "status": "Answered", "difficulty": "hard",
     "fluency": {"score": 45}, "pronunciation": {"score": 50}, "grammar": {"score": 40},
     "overall": {"score": 45}},
]
signals = derive_speaking_signals(weak_speaking)
tags = tag_speaking_test(weak_speaking)
print(f"  Signals: fluency={signals['avg_fluency']}, pron={signals['avg_pronunciation']}, prosody={signals['avg_prosody']}, flat={signals['flat_delivery']}")
print(f"  Tags: {tag_ids(tags)}")
check("avg_fluency < 0.8", signals["avg_fluency"] < 0.8)
check("avg_pronunciation < 0.7", signals["avg_pronunciation"] < 0.7)
check("pronunciation_developing", "pronunciation_developing" in tag_ids(tags), f"got {tag_ids(tags)}")
check("NO expressive_fluency_strong", "expressive_fluency_strong" not in tag_ids(tags))
check("NO pronunciation_accurate", "pronunciation_accurate" not in tag_ids(tags))

# Test 2c: Flat delivery (low prosody)
print("\n-- Test 2c: Flat delivery (low prosody) --")
flat_speaking = [
    {"sentence_id": "s1", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 75}, "pronunciation": {"score": 80}, "grammar": {"score": 50},
     "overall": {"score": 68}},
    {"sentence_id": "s2", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 78}, "pronunciation": {"score": 82}, "grammar": {"score": 52},
     "overall": {"score": 70}},
    {"sentence_id": "s3", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 76}, "pronunciation": {"score": 81}, "grammar": {"score": 48},
     "overall": {"score": 69}},
]
signals = derive_speaking_signals(flat_speaking)
tags = tag_speaking_test(flat_speaking)
print(f"  Signals: prosody={signals['avg_prosody']}, flat={signals['flat_delivery']}")
print(f"  Tags: {tag_ids(tags)}")
check("flat_delivery = True", signals["flat_delivery"] == True, f"got {signals['flat_delivery']}")
check("prosody_emerging", "prosody_emerging" in tag_ids(tags), f"got {tag_ids(tags)}")
check("NO prosody_strong", "prosody_strong" not in tag_ids(tags))

# Test 2d: Insufficient data (only 2 answered)
print("\n-- Test 2d: Insufficient data (only 2 answered) --")
insufficient = [
    {"sentence_id": "s1", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 90}, "pronunciation": {"score": 90}, "grammar": {"score": 90},
     "overall": {"score": 90}},
    {"sentence_id": "s2", "status": "Answered", "difficulty": "medium",
     "fluency": {"score": 90}, "pronunciation": {"score": 90}, "grammar": {"score": 90},
     "overall": {"score": 90}},
]
signals = derive_speaking_signals(insufficient)
tags = tag_speaking_test(insufficient)
check("_insufficient_data flag", signals.get("_insufficient_data") == True)
check("no tags emitted", len(tags) == 0, f"got {tag_ids(tags)}")


# =============================================================================
# 3. STORY EXPLORER (Comprehension)
# =============================================================================
print("\n" + "=" * 70)
print("STORY EXPLORER (Comprehension)")
print("=" * 70)

question_types = {
    "q1": "literal", "q2": "literal", "q3": "literal",
    "q4": "inferential", "q5": "inferential",
    "q6": "vocabulary", "q7": "vocabulary",
    "q8": "inferential",
}

# Test 3a: All correct
print("\n-- Test 3a: All correct --")
all_correct = [{
    "story_id": "story1", "story_title": "Test Story",
    "questions": [
        {"question_id": "q1", "is_correct": True},
        {"question_id": "q2", "is_correct": True},
        {"question_id": "q3", "is_correct": True},
        {"question_id": "q4", "is_correct": True},
        {"question_id": "q5", "is_correct": True},
        {"question_id": "q6", "is_correct": True},
        {"question_id": "q7", "is_correct": True},
        {"question_id": "q8", "is_correct": True},
    ]
}]
signals = derive_comprehension_signals(all_correct, question_types)
tags = tag_comprehension_test(all_correct, question_types)
print(f"  Signals: {signals}")
print(f"  Tags: {tag_ids(tags)}")
check("literal_accuracy = 1.0", signals["literal_accuracy"] == 1.0)
check("inferential_accuracy = 1.0", signals["inferential_accuracy"] == 1.0)
check("vocabulary_accuracy = 1.0", signals["vocabulary_accuracy"] == 1.0)
check("overall_accuracy = 1.0", signals["overall_accuracy"] == 1.0)
check("literal_comprehension_strong", "literal_comprehension_strong" in tag_ids(tags))
check("inferential_comprehension_strong", "inferential_comprehension_strong" in tag_ids(tags))
check("vocabulary_in_context_strong", "vocabulary_in_context_strong" in tag_ids(tags))
check("listening_comprehension_strong", "listening_comprehension_strong" in tag_ids(tags))
check("NO inferential_comprehension_emerging", "inferential_comprehension_emerging" not in tag_ids(tags))

# Test 3b: Literal OK, inferential weak (gap)
print("\n-- Test 3b: Literal OK, inferential weak (gap) --")
gap_results = [{
    "story_id": "story1", "story_title": "Test Story",
    "questions": [
        {"question_id": "q1", "is_correct": True},
        {"question_id": "q2", "is_correct": True},
        {"question_id": "q3", "is_correct": True},
        {"question_id": "q4", "is_correct": False},
        {"question_id": "q5", "is_correct": False},
        {"question_id": "q6", "is_correct": True},
        {"question_id": "q7", "is_correct": True},
        {"question_id": "q8", "is_correct": False},
    ]
}]
signals = derive_comprehension_signals(gap_results, question_types)
tags = tag_comprehension_test(gap_results, question_types)
print(f"  Signals: literal={signals['literal_accuracy']}, inferential={signals['inferential_accuracy']}, gap={signals['literal_inferential_gap']}")
print(f"  Tags: {tag_ids(tags)}")
check("literal_accuracy = 1.0", signals["literal_accuracy"] == 1.0)
check("inferential_accuracy < 0.6", signals["inferential_accuracy"] < 0.6, f"got {signals['inferential_accuracy']}")
check("literal_inferential_gap >= 0.3", signals["literal_inferential_gap"] >= 0.3, f"got {signals['literal_inferential_gap']}")
check("literal_comprehension_strong", "literal_comprehension_strong" in tag_ids(tags))
check("inferential_comprehension_emerging", "inferential_comprehension_emerging" in tag_ids(tags), f"got {tag_ids(tags)}")
check("NO inferential_comprehension_strong", "inferential_comprehension_strong" not in tag_ids(tags))

# Test 3c: Vocabulary weak
print("\n-- Test 3c: Vocabulary weak --")
vocab_weak = [{
    "story_id": "story1", "story_title": "Test Story",
    "questions": [
        {"question_id": "q1", "is_correct": True},
        {"question_id": "q2", "is_correct": True},
        {"question_id": "q3", "is_correct": True},
        {"question_id": "q4", "is_correct": True},
        {"question_id": "q5", "is_correct": True},
        {"question_id": "q6", "is_correct": False},
        {"question_id": "q7", "is_correct": False},
        {"question_id": "q8", "is_correct": True},
    ]
}]
signals = derive_comprehension_signals(vocab_weak, question_types)
tags = tag_comprehension_test(vocab_weak, question_types)
print(f"  Signals: vocab={signals['vocabulary_accuracy']}")
print(f"  Tags: {tag_ids(tags)}")
check("vocabulary_accuracy < 0.6", signals["vocabulary_accuracy"] < 0.6, f"got {signals['vocabulary_accuracy']}")
check("vocabulary_in_context_emerging", "vocabulary_in_context_emerging" in tag_ids(tags), f"got {tag_ids(tags)}")
check("NO vocabulary_in_context_strong", "vocabulary_in_context_strong" not in tag_ids(tags))

# Test 3d: All wrong
print("\n-- Test 3d: All wrong --")
all_wrong = [{
    "story_id": "story1", "story_title": "Test Story",
    "questions": [
        {"question_id": "q1", "is_correct": False},
        {"question_id": "q2", "is_correct": False},
        {"question_id": "q3", "is_correct": False},
        {"question_id": "q4", "is_correct": False},
        {"question_id": "q5", "is_correct": False},
        {"question_id": "q6", "is_correct": False},
        {"question_id": "q7", "is_correct": False},
        {"question_id": "q8", "is_correct": False},
    ]
}]
signals = derive_comprehension_signals(all_wrong, question_types)
tags = tag_comprehension_test(all_wrong, question_types)
print(f"  Signals: {signals}")
print(f"  Tags: {tag_ids(tags)}")
check("overall_accuracy = 0.0", signals["overall_accuracy"] == 0.0)
check("NO listening_comprehension_strong", "listening_comprehension_strong" not in tag_ids(tags))
check("vocabulary_in_context_emerging", "vocabulary_in_context_emerging" in tag_ids(tags))
# inferential_comprehension_emerging requires gap >= 0.3; with all wrong, gap=0.0, so it correctly does NOT fire
check("NO inferential_comprehension_emerging (no gap when all wrong)", "inferential_comprehension_emerging" not in tag_ids(tags))


# =============================================================================
# 4. LOGIC QUEST (quick re-verify)
# =============================================================================
print("\n" + "=" * 70)
print("LOGIC QUEST (quick re-verify)")
print("=" * 70)

items = get_items_by_grade(GradeLevel.GRADE_1_2)
items_lookup = {
    item.item_id: {
        "correct_answer_index": item.correct_answer_index,
        "expected_latency_seconds": item.expected_latency_seconds,
        "item_type": item.item_type,
        "difficulty": item.difficulty,
        "primary_tag": str(item.primary_tag.value),
    }
    for item in items
}

# All correct (Q10 is now two_step, no sort tasks remain)
print("\n-- 4a: All correct --")
responses_raw = []
for item in items:
    r = {"item_id": item.item_id, "selected_answer_index": item.correct_answer_index,
         "response_time_seconds": 20, "attempts": 1, "self_corrected": False}
    responses_raw.append(r)

tags = tag_logic_test(responses_raw, items_lookup)
student_resps = []
for r in responses_raw:
    sr = StudentResponse(student_id="t", item_id=r["item_id"],
                         selected_answer_index=r["selected_answer_index"],
                         response_time_seconds=r["response_time_seconds"],
                         post_shift_accuracy=r.get("post_shift_accuracy"))
    student_resps.append(sr)
result = aggregate_test_results(student_resps, GradeLevel.GRADE_1_2)
print(f"  Score: {result.total_correct}/{result.total_items}")
print(f"  Tags (engine): {tag_ids(tags)}")
print(f"  Tags (agg): {[t.value for t in result.final_tags]}")
check("Score 10/10", result.total_correct == 10)
check("systematic_problem_solving in engine", "systematic_problem_solving" in tag_ids(tags))
check("engine == aggregation", set(tag_ids(tags)) == set(t.value for t in result.final_tags),
      f"engine: {tag_ids(tags)}, agg: {[t.value for t in result.final_tags]}")

# All wrong (Q10 is now two_step, no sort tasks remain)
print("\n-- 4b: All wrong --")
responses_raw2 = []
for item in items:
    r = {"item_id": item.item_id, "selected_answer_index": (item.correct_answer_index + 1) % 4,
         "response_time_seconds": 5, "attempts": 3, "self_corrected": False}
    responses_raw2.append(r)

tags2 = tag_logic_test(responses_raw2, items_lookup)
student_resps2 = []
for r in responses_raw2:
    sr = StudentResponse(student_id="t", item_id=r["item_id"],
                         selected_answer_index=r["selected_answer_index"],
                         response_time_seconds=r["response_time_seconds"],
                         attempts=r["attempts"],
                         post_shift_accuracy=r.get("post_shift_accuracy"))
    student_resps2.append(sr)
result2 = aggregate_test_results(student_resps2, GradeLevel.GRADE_1_2)
print(f"  Score: {result2.total_correct}/{result2.total_items}")
print(f"  Tags (engine): {tag_ids(tags2)}")
print(f"  Tags (agg): {[t.value for t in result2.final_tags]}")
check("Score 0/10", result2.total_correct == 0)
check("reasoning_under_load_emerging in engine", "reasoning_under_load_emerging" in tag_ids(tags2))
check("impulsive_response in engine", "impulsive_response" in tag_ids(tags2))
check("engine == aggregation", set(tag_ids(tags2)) == set(t.value for t in result2.final_tags),
      f"engine: {tag_ids(tags2)}, agg: {[t.value for t in result2.final_tags]}")


# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)
if FAIL == 0:
    print("ALL TESTS PASSED")
else:
    print(f"{FAIL} TESTS FAILED -- review above")
