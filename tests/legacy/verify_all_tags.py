"""
Comprehensive Tagging Verification
Prints ALL derived signals and ALL emitted tags for every test scenario,
plus checks for tags that SHOULD have fired but didn't.
"""

from tagging_engine import (
    derive_logic_signals,
    derive_spelling_signals,
    derive_speaking_signals,
    derive_comprehension_signals,
    emit_tags,
    tag_logic_test,
    tag_spelling_test,
    tag_speaking_test,
    tag_comprehension_test,
    CONFIG,
)
from logic_assessment import ALL_LOGIC_ITEMS

def sep(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def print_signals(signals):
    print("  DERIVED SIGNALS:")
    for k, v in signals.items():
        if not k.startswith("_"):
            print(f"    {k:40s} = {v}")

def print_tags(tags):
    print("  EMITTED TAGS:")
    if not tags:
        print("    (none)")
    for t in tags:
        print(f"    [{t['confidence'].upper():4s}] {t['id']:42s} ({t['polarity']})")
        if t.get("evidence"):
            print(f"           evidence: {t['evidence']}")

def check_expected(tags, expected_ids, test_name):
    """Check that expected tags fired and report any missing."""
    actual_ids = [t["id"] for t in tags]
    missing = [e for e in expected_ids if e not in actual_ids]
    unexpected = [a for a in actual_ids if a not in expected_ids]
    if missing:
        print(f"  ⚠️  MISSING TAGS: {missing}")
    if unexpected:
        print(f"  ℹ️  EXTRA TAGS (not necessarily wrong): {unexpected}")
    if not missing:
        print(f"  ✅ All expected tags present")
    return len(missing) == 0


# =============================================================================
# 1. LOGIC — High Performer K-1 (90%)
# =============================================================================
sep("LOGIC TEST 1: High-Performing K-1 (90% — 9/10 correct)")

items_lookup = {
    item.item_id: {
        "correct_answer_index": item.correct_answer_index,
        "expected_latency_seconds": item.expected_latency_seconds,
        "item_type": item.item_type,
    }
    for item in ALL_LOGIC_ITEMS
}

responses_1 = [
    {"item_id": "k1_1", "selected_answer_index": 1, "response_time_seconds": 15, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_2", "selected_answer_index": 1, "response_time_seconds": 18, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_3", "selected_answer_index": 2, "response_time_seconds": 12, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_4", "selected_answer_index": 1, "response_time_seconds": 10, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_5", "selected_answer_index": 0, "response_time_seconds": 14, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_6", "selected_answer_index": 1, "response_time_seconds": 22, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_7", "selected_answer_index": 1, "response_time_seconds": 16, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_8", "selected_answer_index": 2, "response_time_seconds": 35, "attempts": 1, "self_corrected": False},  # WRONG
    {"item_id": "k1_9", "selected_answer_index": 2, "response_time_seconds": 20, "attempts": 1, "self_corrected": False},
    {"item_id": "k1_10", "selected_answer_index": 1, "response_time_seconds": 18, "attempts": 1, "self_corrected": False},
]

signals_1 = derive_logic_signals(responses_1, items_lookup)
print_signals(signals_1)
tags_1 = tag_logic_test(responses_1, items_lookup)
print_tags(tags_1)
# pattern: k1_1,k1_2,k1_7,k1_10 = 4 correct → strong
# relational: k1_3,k1_4,k1_5,k1_6,k1_9 = 5 correct → present
# multistep: k1_8 wrong → 0 correct
check_expected(tags_1, ["pattern_detection_strong", "relational_reasoning_present"], "K-1 90%")


# =============================================================================
# 2. LOGIC — Developing 2nd Grader (60%)
# =============================================================================
sep("LOGIC TEST 2: Developing 2-3 (60% — 6/10 correct)")

responses_2 = [
    {"item_id": "2_3_1", "selected_answer_index": 2, "response_time_seconds": 28, "attempts": 1, "self_corrected": False},
    {"item_id": "2_3_2", "selected_answer_index": 1, "response_time_seconds": 30, "attempts": 2, "self_corrected": True},
    {"item_id": "2_3_3", "selected_answer_index": 0, "response_time_seconds": 38, "attempts": 1, "self_corrected": False},
    {"item_id": "2_3_4", "selected_answer_index": 3, "response_time_seconds": 80, "attempts": 2, "self_corrected": False},  # WRONG, over-time
    {"item_id": "2_3_5", "selected_answer_index": 0, "response_time_seconds": 32, "attempts": 1, "self_corrected": False},
    {"item_id": "2_3_6", "selected_answer_index": 2, "response_time_seconds": 65, "attempts": 1, "self_corrected": False},  # WRONG, over-time
    {"item_id": "2_3_7", "selected_answer_index": 1, "response_time_seconds": 45, "attempts": 3, "self_corrected": False},
    {"item_id": "2_3_8", "selected_answer_index": 2, "response_time_seconds": 75, "attempts": 1, "self_corrected": False},  # WRONG (self-report)
    {"item_id": "2_3_9", "selected_answer_index": 0, "response_time_seconds": 30, "attempts": 1, "self_corrected": False},
    {"item_id": "2_3_10", "selected_answer_index": 2, "response_time_seconds": 55, "attempts": 1, "self_corrected": False}, # WRONG
]

signals_2 = derive_logic_signals(responses_2, items_lookup)
print_signals(signals_2)
tags_2 = tag_logic_test(responses_2, items_lookup)
print_tags(tags_2)
# pattern: 2_3_1(skip_pattern)=correct, 2_3_2(alternating_pattern)=correct, 2_3_10(pattern_creation)=wrong → 2 → emerging
# relational: 2_3_3(odd_one_out_explain)=correct, 2_3_5(analogy_complex)=correct → 2 → no tag (need 3)
# multistep: 2_3_4(matrix_2rule)=wrong, 2_3_6(rule_logic)=wrong, 2_3_7(multi_step_quantity)=correct, 2_3_9(syllogism)=correct → 2 → no tag (need 3)
# self_corrected: 2_3_2 → 1 → self_correction_present
# over_time_incorrect: 2_3_4(80>75), 2_3_6(65>60) → 2 → reasoning_under_load_emerging
# multiple_attempts: 2_3_2(2), 2_3_4(2), 2_3_7(3) → 3 → trial_and_error_approach
# selfreport_negative: 2_3_8(complex_category_shift)=wrong → 1 → strategy_shift_difficulty (LOW)
check_expected(tags_2, [
    "pattern_detection_emerging", "self_correction_present",
    "reasoning_under_load_emerging", "trial_and_error_approach",
    "strategy_shift_difficulty"
], "2-3 60%")


# =============================================================================
# 3. LOGIC — Advanced 3rd Grader (80%)
# =============================================================================
sep("LOGIC TEST 3: Advanced 3-4 (80% — 8/10 correct)")

responses_3 = [
    {"item_id": "3_4_1", "selected_answer_index": 1, "response_time_seconds": 30, "attempts": 1, "self_corrected": False},
    {"item_id": "3_4_2", "selected_answer_index": 1, "response_time_seconds": 35, "attempts": 1, "self_corrected": False},
    {"item_id": "3_4_3", "selected_answer_index": 3, "response_time_seconds": 40, "attempts": 1, "self_corrected": False},
    {"item_id": "3_4_4", "selected_answer_index": 2, "response_time_seconds": 55, "attempts": 1, "self_corrected": False},
    {"item_id": "3_4_5", "selected_answer_index": 0, "response_time_seconds": 60, "attempts": 1, "self_corrected": False},  # WRONG
    {"item_id": "3_4_6", "selected_answer_index": 0, "response_time_seconds": 35, "attempts": 1, "self_corrected": False},
    {"item_id": "3_4_7", "selected_answer_index": 2, "response_time_seconds": 40, "attempts": 1, "self_corrected": False},
    {"item_id": "3_4_8", "selected_answer_index": 0, "response_time_seconds": 25, "attempts": 1, "self_corrected": False},
    {"item_id": "3_4_9", "selected_answer_index": 0, "response_time_seconds": 38, "attempts": 1, "self_corrected": False},
    {"item_id": "3_4_10", "selected_answer_index": 2, "response_time_seconds": 52, "attempts": 1, "self_corrected": False}, # WRONG
]

signals_3 = derive_logic_signals(responses_3, items_lookup)
print_signals(signals_3)
tags_3 = tag_logic_test(responses_3, items_lookup)
print_tags(tags_3)
# pattern: 3_4_1(pattern)=correct, 3_4_2(pattern)=correct, 3_4_10(pattern_creation)=wrong → 2 → emerging
# relational: 3_4_3(odd_one_out)=correct, 3_4_5(analogy)=wrong, 3_4_9(dual_classification)=correct → 2 → no tag (need 3)
# multistep: 3_4_4(matrix_multi)=correct, 3_4_6(conditional_logic)=correct, 3_4_7(order_of_operations)=correct → 3 → systematic_problem_solving
# self_report: 3_4_8(meta_cognitive)=correct → 0 negative → no strategy_shift_difficulty
check_expected(tags_3, ["pattern_detection_emerging", "systematic_problem_solving"], "3-4 80%")


# =============================================================================
# 4. LOGIC — Rushed Profile (fast + inaccurate)
# =============================================================================
sep("LOGIC TEST 4: Rushed Profile (fast + inaccurate)")

rush_items = {
    "k1_1": {"correct_answer_index": 1, "expected_latency_seconds": 20, "item_type": "pattern"},
    "k1_2": {"correct_answer_index": 1, "expected_latency_seconds": 25, "item_type": "pattern"},
    "k1_3": {"correct_answer_index": 2, "expected_latency_seconds": 20, "item_type": "odd_one_out"},
    "k1_4": {"correct_answer_index": 1, "expected_latency_seconds": 15, "item_type": "matching"},
    "k1_5": {"correct_answer_index": 0, "expected_latency_seconds": 20, "item_type": "comparison"},
}

rush_responses = [
    {"item_id": "k1_1", "selected_answer_index": 0, "response_time_seconds": 5, "attempts": 1, "self_corrected": False},   # WRONG, fast
    {"item_id": "k1_2", "selected_answer_index": 3, "response_time_seconds": 8, "attempts": 1, "self_corrected": False},   # WRONG, fast
    {"item_id": "k1_3", "selected_answer_index": 0, "response_time_seconds": 6, "attempts": 1, "self_corrected": False},   # WRONG, fast
    {"item_id": "k1_4", "selected_answer_index": 1, "response_time_seconds": 4, "attempts": 1, "self_corrected": False},   # correct, fast
    {"item_id": "k1_5", "selected_answer_index": 2, "response_time_seconds": 7, "attempts": 1, "self_corrected": False},   # WRONG, fast
]

signals_4 = derive_logic_signals(rush_responses, rush_items)
print_signals(signals_4)
tags_4 = tag_logic_test(rush_responses, rush_items)
print_tags(tags_4)
# fast_inaccurate: k1_1(5<10,wrong), k1_2(8<12.5,wrong), k1_3(6<10,wrong), k1_5(7<10,wrong) → 4 → impulsive_response
check_expected(tags_4, ["impulsive_response"], "Rushed Logic")


# =============================================================================
# 5. SPELLING — Strong Profile (all correct)
# =============================================================================
sep("SPELLING TEST 1: Strong Profile (all correct)")

spelling_strong = [
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

signals_sp1 = derive_spelling_signals(spelling_strong, "Kindergarten")
print_signals(signals_sp1)
tags_sp1 = tag_spelling_test(spelling_strong, "Kindergarten")
print_tags(tags_sp1)
# All correct → beginning=1.0, final=1.0, vowel=1.0, vowel_errors=0
# digraph: no digraph features in these words → digraph_accuracy=1.0 (no errors), digraph_error_count=0
# blend: same → blend_accuracy=1.0
# sight: 5/5=1.0
# hard_words: words with max_points>=3 → 5 words, all attempted → 1.0
# fast_slips: all time >= 3 → 0
check_expected(tags_sp1, [
    "phonetic_strategy_strong", "vowel_accuracy_strong",
    "digraph_blend_competent", "sight_word_recognition_strong",
    "confident_attempt"
], "Spelling Strong")


# =============================================================================
# 6. SPELLING — Rushed Profile (fast slips)
# =============================================================================
sep("SPELLING TEST 2: Rushed Profile (fast slips)")

spelling_rushed = [
    {"word": "cat", "user_input": "cet", "type": "regular", "points": 2, "max_points": 3, "mistakes": {"short_vowels": "a"}, "time": 2, "hints_used": 0},
    {"word": "dog", "user_input": "dag", "type": "regular", "points": 2, "max_points": 3, "mistakes": {"short_vowels": "o"}, "time": 1, "hints_used": 0},
    {"word": "sun", "user_input": "sun", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 2, "hints_used": 0},
    {"word": "to", "user_input": "to", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 1, "hints_used": 0},
    {"word": "he", "user_input": "hi", "type": "sight", "points": 0, "max_points": 1, "mistakes": {"spelling": "Expected 'he', got 'hi'"}, "time": 1, "hints_used": 0},
]

signals_sp2 = derive_spelling_signals(spelling_rushed, "Kindergarten")
print_signals(signals_sp2)
tags_sp2 = tag_spelling_test(spelling_rushed, "Kindergarten")
print_tags(tags_sp2)
# vowel_errors: cat(short_vowels), dog(short_vowels) → 2 → vowel_difficulty_emerging
# fast_slips: cat(time=2<3,wrong), dog(time=1<3,wrong), he(time=1<3,wrong) → 3 → rushed_spelling
# sight: 1/2=0.5, regular: 1/3=0.333 → sight > regular? No, 0.5 > 0.333 → sight_word_emerging does NOT fire (needs sight < regular)
# Actually sight=0.5, regular=0.333 → sight > regular → condition not met
# hard_words: cat,dog,sun have max_points=3 → 3 words, all attempted → 1.0 → confident_attempt
# digraph: no digraph mistakes → digraph_accuracy=1.0, digraph_error_count=0 → digraph_blend_competent
check_expected(tags_sp2, [
    "vowel_difficulty_emerging", "rushed_spelling",
    "confident_attempt", "digraph_blend_competent"
], "Spelling Rushed")


# =============================================================================
# 7. SPELLING — Vowel + Digraph Difficulty
# =============================================================================
sep("SPELLING TEST 3: Vowel + Digraph Difficulty")

spelling_diff = [
    {"word": "chap", "user_input": "cap", "type": "regular", "points": 2, "max_points": 4, "mistakes": {"consonant_digraphs": "ch"}, "time": 8, "hints_used": 0},
    {"word": "ship", "user_input": "sip", "type": "regular", "points": 2, "max_points": 4, "mistakes": {"consonant_digraphs": "sh"}, "time": 7, "hints_used": 0},
    {"word": "cat", "user_input": "cet", "type": "regular", "points": 2, "max_points": 3, "mistakes": {"short_vowels": "a"}, "time": 6, "hints_used": 0},
    {"word": "dog", "user_input": "dag", "type": "regular", "points": 2, "max_points": 3, "mistakes": {"short_vowels": "o"}, "time": 7, "hints_used": 0},
    {"word": "sit", "user_input": "sit", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 8, "hints_used": 0},
    {"word": "is", "user_input": "is", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
    {"word": "the", "user_input": "the", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 3, "hints_used": 0},
]

signals_sp3 = derive_spelling_signals(spelling_diff, "First")
print_signals(signals_sp3)
tags_sp3 = tag_spelling_test(spelling_diff, "First")
print_tags(tags_sp3)
# vowel_errors: cat, dog → 2 → vowel_difficulty_emerging
# digraph_errors: chap, ship → 2 → digraph_difficulty_emerging
# sight: 2/2=1.0 → sight_word_recognition_strong
# digraph_blend_competent: digraph_accuracy = 1 - 2/2 = 0.0 → NOT >= 0.7 → does NOT fire
check_expected(tags_sp3, [
    "vowel_difficulty_emerging", "digraph_difficulty_emerging",
    "sight_word_recognition_strong"
], "Spelling Vowel+Digraph Difficulty")


# =============================================================================
# 8. SPELLING — Sight Word Difficulty
# =============================================================================
sep("SPELLING TEST 4: Sight Word Difficulty (sight < regular)")

spelling_sight = [
    {"word": "cat", "user_input": "cat", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 8, "hints_used": 0},
    {"word": "mat", "user_input": "mat", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 7, "hints_used": 0},
    {"word": "sit", "user_input": "sit", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 6, "hints_used": 0},
    {"word": "to", "user_input": "ta", "type": "sight", "points": 0, "max_points": 1, "mistakes": {"spelling": "Expected 'to', got 'ta'"}, "time": 3, "hints_used": 0},
    {"word": "me", "user_input": "mi", "type": "sight", "points": 0, "max_points": 1, "mistakes": {"spelling": "Expected 'me', got 'mi'"}, "time": 3, "hints_used": 0},
    {"word": "he", "user_input": "hi", "type": "sight", "points": 0, "max_points": 1, "mistakes": {"spelling": "Expected 'he', got 'hi'"}, "time": 3, "hints_used": 0},
]

signals_sp4 = derive_spelling_signals(spelling_sight, "Kindergarten")
print_signals(signals_sp4)
tags_sp4 = tag_spelling_test(spelling_sight, "Kindergarten")
print_tags(tags_sp4)
# sight: 0/3=0.0, regular: 3/3=1.0 → sight < regular AND sight < 0.7 → sight_word_emerging
# vowel_errors: 0 → vowel_accuracy_strong
# beginning=1.0, final=1.0, vowel=1.0 → phonetic_strategy_strong
check_expected(tags_sp4, [
    "phonetic_strategy_strong", "vowel_accuracy_strong",
    "sight_word_emerging", "confident_attempt"
], "Sight Word Difficulty")


# =============================================================================
# 9. SPEAKING — Strong Profile
# =============================================================================
sep("SPEAKING TEST 1: Strong Profile (high scores)")

speaking_strong = [
    {"sentence_id": "k1", "status": "Answered", "pronunciation": {"score": 90}, "fluency": {"score": 85}, "overall": {"score": 88}, "difficulty": "easy"},
    {"sentence_id": "k2", "status": "Answered", "pronunciation": {"score": 88}, "fluency": {"score": 82}, "overall": {"score": 85}, "difficulty": "easy"},
    {"sentence_id": "k3", "status": "Answered", "pronunciation": {"score": 92}, "fluency": {"score": 88}, "overall": {"score": 90}, "difficulty": "easy"},
    {"sentence_id": "k4", "status": "Answered", "pronunciation": {"score": 85}, "fluency": {"score": 80}, "overall": {"score": 83}, "difficulty": "medium"},
]

signals_sk1 = derive_speaking_signals(speaking_strong)
print_signals(signals_sk1)
tags_sk1 = tag_speaking_test(speaking_strong)
print_tags(tags_sk1)
# avg_pronunciation = (90+88+92+85)/4/100 = 0.8875 → pronunciation_accurate (>= 0.85)
# avg_fluency = (85+82+88+80)/4/100 = 0.8375 → expressive_fluency_strong (>= 0.8)
# hard_band: no hard sentences → hard_band_avg = 0.0 → complex_syntax_confident does NOT fire
check_expected(tags_sk1, [
    "pronunciation_accurate", "expressive_fluency_strong"
], "Speaking Strong")


# =============================================================================
# 10. SPEAKING — Developing Profile
# =============================================================================
sep("SPEAKING TEST 2: Developing Profile (low scores)")

speaking_developing = [
    {"sentence_id": "k1", "status": "Answered", "pronunciation": {"score": 60}, "fluency": {"score": 65}, "overall": {"score": 62}, "difficulty": "easy"},
    {"sentence_id": "k2", "status": "Answered", "pronunciation": {"score": 58}, "fluency": {"score": 62}, "overall": {"score": 60}, "difficulty": "easy"},
    {"sentence_id": "k3", "status": "Answered", "pronunciation": {"score": 62}, "fluency": {"score": 68}, "overall": {"score": 65}, "difficulty": "easy"},
    {"sentence_id": "k4", "status": "Answered", "pronunciation": {"score": 55}, "fluency": {"score": 60}, "overall": {"score": 58}, "difficulty": "medium"},
]

signals_sk2 = derive_speaking_signals(speaking_developing)
print_signals(signals_sk2)
tags_sk2 = tag_speaking_test(speaking_developing)
print_tags(tags_sk2)
# avg_pronunciation = (60+58+62+55)/4/100 = 0.5875 → pronunciation_developing (< 0.7)
# avg_fluency = (65+62+68+60)/4/100 = 0.6375 → expressive_fluency_emerging (0.6 <= x < 0.8)
check_expected(tags_sk2, [
    "pronunciation_developing", "expressive_fluency_emerging"
], "Speaking Developing")


# =============================================================================
# 11. SPEAKING — Hard Band Confidence
# =============================================================================
sep("SPEAKING TEST 3: Hard Band Confidence (strong on hard sentences)")

speaking_hard = [
    {"sentence_id": "s1", "status": "Answered", "pronunciation": {"score": 90}, "fluency": {"score": 85}, "overall": {"score": 88}, "difficulty": "medium"},
    {"sentence_id": "s2", "status": "Answered", "pronunciation": {"score": 88}, "fluency": {"score": 82}, "overall": {"score": 85}, "difficulty": "medium"},
    {"sentence_id": "s3", "status": "Answered", "pronunciation": {"score": 92}, "fluency": {"score": 88}, "overall": {"score": 90}, "difficulty": "medium"},
    {"sentence_id": "s5", "status": "Answered", "pronunciation": {"score": 87}, "fluency": {"score": 83}, "overall": {"score": 85}, "difficulty": "hard"},
    {"sentence_id": "s6", "status": "Answered", "pronunciation": {"score": 85}, "fluency": {"score": 82}, "overall": {"score": 84}, "difficulty": "hard"},
    {"sentence_id": "s7", "status": "Answered", "pronunciation": {"score": 89}, "fluency": {"score": 86}, "overall": {"score": 88}, "difficulty": "hard"},
]

signals_sk3 = derive_speaking_signals(speaking_hard)
print_signals(signals_sk3)
tags_sk3 = tag_speaking_test(speaking_hard)
print_tags(tags_sk3)
# avg_fluency = (85+82+88+83+82+86)/6/100 = 0.843 → expressive_fluency_strong
# avg_pronunciation = (90+88+92+87+85+89)/6/100 = 0.885 → pronunciation_accurate
# hard_band_avg = (85+84+88)/3/100 = 0.856 → complex_syntax_confident (>= 0.8)
check_expected(tags_sk3, [
    "expressive_fluency_strong", "pronunciation_accurate",
    "complex_syntax_confident"
], "Speaking Hard Band")


# =============================================================================
# 12. COMPREHENSION — Strong Listener
# =============================================================================
sep("COMPREHENSION TEST 1: Strong Listener (7/8 correct)")

comp_results_1 = [
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
            {"question_id": "k2_q4", "is_correct": False},  # missed inferential
        ]
    }
]

from main import COMPREHENSION_QUESTION_TYPES

signals_c1 = derive_comprehension_signals(comp_results_1, COMPREHENSION_QUESTION_TYPES)
print_signals(signals_c1)
tags_c1 = tag_comprehension_test(comp_results_1, COMPREHENSION_QUESTION_TYPES)
print_tags(tags_c1)
# literal: 7/7 = 1.0 → literal_comprehension_strong
# inferential: 0/1 = 0.0 → inferential_comprehension_emerging (gap = 1.0-0.0 = 1.0 >= 0.3 AND inferential < 0.6)
# vocabulary: 0/0 → 0.0 (no vocab questions) → vocabulary_in_context_emerging (< 0.6) — hmm, edge case
# overall: 7/8 = 0.875 → listening_comprehension_strong (>= 0.75)
check_expected(tags_c1, [
    "literal_comprehension_strong", "listening_comprehension_strong",
    "inferential_comprehension_emerging"
], "Comprehension Strong Listener")


# =============================================================================
# 13. COMPREHENSION — Inferential Strength
# =============================================================================
sep("COMPREHENSION TEST 2: All Correct (8/8)")

comp_results_2 = [
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
            {"question_id": "k2_q4", "is_correct": True},  # inferential correct
        ]
    }
]

signals_c2 = derive_comprehension_signals(comp_results_2, COMPREHENSION_QUESTION_TYPES)
print_signals(signals_c2)
tags_c2 = tag_comprehension_test(comp_results_2, COMPREHENSION_QUESTION_TYPES)
print_tags(tags_c2)
# literal: 7/7 = 1.0 → literal_comprehension_strong
# inferential: 1/1 = 1.0 → inferential_comprehension_strong
# overall: 8/8 = 1.0 → listening_comprehension_strong
check_expected(tags_c2, [
    "literal_comprehension_strong", "inferential_comprehension_strong",
    "listening_comprehension_strong"
], "Comprehension All Correct")


# =============================================================================
# 14. COMPREHENSION — Third Grade (inferential + vocabulary)
# =============================================================================
sep("COMPREHENSION TEST 3: Third Grade Mixed (6/8 correct)")

comp_results_3 = [
    {
        "story_id": "t_story1",
        "story_title": "The Mysterious Letter",
        "questions": [
            {"question_id": "t1_q1", "is_correct": True},   # literal
            {"question_id": "t1_q2", "is_correct": True},   # literal
            {"question_id": "t1_q3", "is_correct": False},  # literal - WRONG
            {"question_id": "t1_q4", "is_correct": True},   # inferential
        ]
    },
    {
        "story_id": "t_story2",
        "story_title": "The Courage to Try",
        "questions": [
            {"question_id": "t2_q1", "is_correct": True},   # inferential
            {"question_id": "t2_q2", "is_correct": True},   # literal
            {"question_id": "t2_q3", "is_correct": False},  # literal - WRONG
            {"question_id": "t2_q4", "is_correct": True},   # inferential
        ]
    }
]

signals_c3 = derive_comprehension_signals(comp_results_3, COMPREHENSION_QUESTION_TYPES)
print_signals(signals_c3)
tags_c3 = tag_comprehension_test(comp_results_3, COMPREHENSION_QUESTION_TYPES)
print_tags(tags_c3)
# literal: t1_q1, t1_q2, t2_q2 correct; t1_q3, t2_q3 wrong → 3/5 = 0.6 → no literal_comprehension_strong
# inferential: t1_q4, t2_q1, t2_q4 correct → 3/3 = 1.0 → inferential_comprehension_strong
# vocabulary: 0/0 → 0.0 → vocabulary_in_context_emerging (edge case - no vocab questions)
# overall: 6/8 = 0.75 → listening_comprehension_strong (>= 0.75)
# gap = 0.6 - 1.0 = -0.4 → no inferential_comprehension_emerging
check_expected(tags_c3, [
    "inferential_comprehension_strong", "listening_comprehension_strong",
    "vocabulary_in_context_emerging"
], "Third Grade Mixed")


# =============================================================================
# 15. COMPREHENSION — Weak Profile (2/8 correct)
# =============================================================================
sep("COMPREHENSION TEST 4: Weak Profile (2/8 correct)")

comp_results_4 = [
    {
        "story_id": "k_story1",
        "story_title": "The Friendly Dog",
        "questions": [
            {"question_id": "k1_q1", "is_correct": True},   # literal
            {"question_id": "k1_q2", "is_correct": False},  # literal
            {"question_id": "k1_q3", "is_correct": False},  # literal
            {"question_id": "k1_q4", "is_correct": False},  # literal
        ]
    },
    {
        "story_id": "k_story2",
        "story_title": "The Magic Garden",
        "questions": [
            {"question_id": "k2_q1", "is_correct": True},   # literal
            {"question_id": "k2_q2", "is_correct": False},  # literal
            {"question_id": "k2_q3", "is_correct": False},  # literal
            {"question_id": "k2_q4", "is_correct": False},  # inferential
        ]
    }
]

signals_c4 = derive_comprehension_signals(comp_results_4, COMPREHENSION_QUESTION_TYPES)
print_signals(signals_c4)
tags_c4 = tag_comprehension_test(comp_results_4, COMPREHENSION_QUESTION_TYPES)
print_tags(tags_c4)
# literal: 2/7 = 0.286 → no literal_comprehension_strong
# inferential: 0/1 = 0.0, gap = 0.286 - 0.0 = 0.286 < 0.3 → no inferential_comprehension_emerging
# overall: 2/8 = 0.25 → no listening_comprehension_strong
# vocabulary: 0/0 → 0.0 → vocabulary_in_context_emerging (edge case)
check_expected(tags_c4, [
    "vocabulary_in_context_emerging"
], "Weak Profile")


# =============================================================================
# 16. EDGE CASE — Speaking with insufficient data
# =============================================================================
sep("SPEAKING EDGE: Insufficient Data (only 1 answered)")

speaking_insufficient = [
    {"sentence_id": "k1", "status": "Answered", "pronunciation": {"score": 90}, "fluency": {"score": 85}, "overall": {"score": 88}, "difficulty": "easy"},
    {"sentence_id": "k2", "status": "Not Attempted", "pronunciation": {}, "fluency": {}, "overall": {"score": 0}, "difficulty": "easy"},
    {"sentence_id": "k3", "status": "Not Attempted", "pronunciation": {}, "fluency": {}, "overall": {"score": 0}, "difficulty": "easy"},
]

signals_sk_edge = derive_speaking_signals(speaking_insufficient)
print_signals(signals_sk_edge)
tags_sk_edge = tag_speaking_test(speaking_insufficient)
print_tags(tags_sk_edge)
if not tags_sk_edge:
    print("  ✅ Correctly emitted NO tags (insufficient data)")
else:
    print("  ⚠️  Should have emitted no tags for insufficient data!")


# =============================================================================
# SUMMARY
# =============================================================================
sep("VERIFICATION COMPLETE")
print("  Review the signals and tags above for correctness.")
print("  If any ⚠️  MISSING TAGS appear, those need investigation.")
print()
