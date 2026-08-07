"""
Tagging Engine Verification Tests
===================================
Hand-checked cases per the spec:
1. Three logic profiles (90% K, 60% 2nd, 80% 3rd) — confirm tags match expectations
2. Deliberately 'rushed' profile — confirm impulsive_response and rushed_spelling fire
3. 'Listens better than reads' profile — confirm listening_comprehension_strong + speaking strengths
4. Self-report tags emitted as low confidence, not high
"""

import json
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
    tag_all_tests,
    CONFIG,
)


# =============================================================================
# HELPERS
# =============================================================================

def tag_ids(tags):
    """Extract just the IDs from a tag array."""
    return [t["id"] for t in tags]


def has_tag(tags, tag_id):
    return tag_id in tag_ids(tags)


def get_tag(tags, tag_id):
    for t in tags:
        if t["id"] == tag_id:
            return t
    return None


def print_tags(label, tags):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if not tags:
        print("  (no tags emitted)")
    for t in tags:
        conf = t["confidence"].upper()
        pol = t["polarity"]
        print(f"  [{conf}] {t['id']:40s} ({pol})")
    print()


# =============================================================================
# TEST 1: High-performing Kindergartener (90% — 9/10 correct)
# =============================================================================

def test_logic_high_performer_k1():
    """90% K-1 student: should get pattern_detection_strong + relational_reasoning_present."""
    # Simulate 10 K-1 items: 4 pattern, 3 relational, 2 multistep, 1 self-report
    items_lookup = {
        "k1_1": {"correct_answer_index": 1, "expected_latency_seconds": 20, "item_type": "pattern"},
        "k1_2": {"correct_answer_index": 1, "expected_latency_seconds": 25, "item_type": "pattern"},
        "k1_3": {"correct_answer_index": 2, "expected_latency_seconds": 20, "item_type": "odd_one_out"},
        "k1_4": {"correct_answer_index": 1, "expected_latency_seconds": 15, "item_type": "matching"},
        "k1_5": {"correct_answer_index": 0, "expected_latency_seconds": 20, "item_type": "comparison"},
        "k1_6": {"correct_answer_index": 1, "expected_latency_seconds": 25, "item_type": "analogy"},
        "k1_7": {"correct_answer_index": 1, "expected_latency_seconds": 20, "item_type": "sequence"},
        "k1_8": {"correct_answer_index": 0, "expected_latency_seconds": 30, "item_type": "rule_application"},
        "k1_9": {"correct_answer_index": 2, "expected_latency_seconds": 25, "item_type": "categorization"},
        "k1_10": {"correct_answer_index": 1, "expected_latency_seconds": 20, "item_type": "pattern"},
    }

    # 9/10 correct, missed k1_8 (rule_application = multistep)
    responses = [
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

    tags = tag_logic_test(responses, items_lookup)
    print_tags("TEST 1: High-Performing K-1 (90%)", tags)

    # Expected: pattern_detection_strong (3 pattern correct: k1_1, k1_2, k1_10)
    assert has_tag(tags, "pattern_detection_strong"), \
        f"Expected pattern_detection_strong, got: {tag_ids(tags)}"

    # Expected: relational_reasoning_present (3 relational correct: k1_3, k1_4, k1_5, k1_6, k1_9)
    assert has_tag(tags, "relational_reasoning_present"), \
        f"Expected relational_reasoning_present, got: {tag_ids(tags)}"

    # Should NOT have any growth-edge tags
    assert not has_tag(tags, "reasoning_under_load_emerging")
    assert not has_tag(tags, "impulsive_response")
    assert not has_tag(tags, "trial_and_error_approach")

    print("  ✅ PASS: High-performing K-1 tags match expectations")
    return True


# =============================================================================
# TEST 2: Developing 2nd Grader (60% — 6/10 correct)
# =============================================================================

def test_logic_developing_2nd_grade():
    """60% 2-3 student: some strengths, but growth-edge tags should fire."""
    items_lookup = {
        "2_3_1": {"correct_answer_index": 2, "expected_latency_seconds": 30, "item_type": "skip_pattern"},
        "2_3_2": {"correct_answer_index": 1, "expected_latency_seconds": 25, "item_type": "alternating_pattern"},
        "2_3_3": {"correct_answer_index": 0, "expected_latency_seconds": 40, "item_type": "odd_one_out_explain"},
        "2_3_4": {"correct_answer_index": 1, "expected_latency_seconds": 50, "item_type": "matrix_2rule"},
        "2_3_5": {"correct_answer_index": 0, "expected_latency_seconds": 35, "item_type": "analogy_complex"},
        "2_3_6": {"correct_answer_index": 0, "expected_latency_seconds": 40, "item_type": "rule_logic"},
        "2_3_7": {"correct_answer_index": 1, "expected_latency_seconds": 40, "item_type": "multi_step_quantity"},
        "2_3_8": {"correct_answer_index": 0, "expected_latency_seconds": 60, "item_type": "complex_category_shift"},
        "2_3_9": {"correct_answer_index": 0, "expected_latency_seconds": 35, "item_type": "syllogism"},
        "2_3_10": {"correct_answer_index": 0, "expected_latency_seconds": 45, "item_type": "pattern_creation"},
    }

    # 6/10 correct. Missed: matrix(over-time), transitive(over-time), category_shift(self-report), pattern_creation
    # Multiple attempts on 2 items. Over-time on 2 incorrect items.
    responses = [
        {"item_id": "2_3_1", "selected_answer_index": 2, "response_time_seconds": 28, "attempts": 1, "self_corrected": False},  # correct
        {"item_id": "2_3_2", "selected_answer_index": 1, "response_time_seconds": 30, "attempts": 2, "self_corrected": True},   # correct, self-corrected
        {"item_id": "2_3_3", "selected_answer_index": 0, "response_time_seconds": 38, "attempts": 1, "self_corrected": False},  # correct
        {"item_id": "2_3_4", "selected_answer_index": 3, "response_time_seconds": 80, "attempts": 2, "self_corrected": False},  # WRONG, over-time, multiple attempts
        {"item_id": "2_3_5", "selected_answer_index": 0, "response_time_seconds": 32, "attempts": 1, "self_corrected": False},  # correct
        {"item_id": "2_3_6", "selected_answer_index": 2, "response_time_seconds": 65, "attempts": 1, "self_corrected": False},  # WRONG, over-time
        {"item_id": "2_3_7", "selected_answer_index": 1, "response_time_seconds": 45, "attempts": 3, "self_corrected": False},  # correct, 3 attempts
        {"item_id": "2_3_8", "selected_answer_index": 2, "response_time_seconds": 75, "attempts": 1, "self_corrected": False},  # WRONG (self-report negative)
        {"item_id": "2_3_9", "selected_answer_index": 0, "response_time_seconds": 30, "attempts": 1, "self_corrected": False},  # correct
        {"item_id": "2_3_10", "selected_answer_index": 2, "response_time_seconds": 55, "attempts": 1, "self_corrected": False}, # WRONG
    ]

    tags = tag_logic_test(responses, items_lookup)
    print_tags("TEST 2: Developing 2-3 (60%)", tags)

    # Pattern items: 2_3_1 (skip_pattern)=correct, 2_3_2 (alternating_pattern)=correct, 2_3_10 (pattern_creation)=wrong
    # pattern_items_correct = 2 → pattern_detection_emerging
    assert has_tag(tags, "pattern_detection_emerging"), \
        f"Expected pattern_detection_emerging, got: {tag_ids(tags)}"

    # Relational: 2_3_3 (odd_one_out_explain)=correct, 2_3_5 (analogy_complex)=correct → only 2, not 3
    # So relational_reasoning_present should NOT fire (need 3)
    # Actually let's check: odd_one_out_explain is relational, analogy_complex is relational
    # That's only 2 relational correct → no tag

    # Over-time + incorrect: 2_3_4 (80s > 50*1.5=75) and 2_3_6 (65s > 40*1.5=60) → 2 items
    assert has_tag(tags, "reasoning_under_load_emerging"), \
        f"Expected reasoning_under_load_emerging, got: {tag_ids(tags)}"

    # Multiple attempts: 2_3_4 (2 attempts), 2_3_7 (3 attempts) → 2 items (one is wrong, but both count)
    # Actually 2_3_2 also has 2 attempts. So items_multiple_attempts = 3 → trial_and_error fires
    assert has_tag(tags, "trial_and_error_approach"), \
        f"Expected trial_and_error_approach, got: {tag_ids(tags)}"

    # Self-report negative: 2_3_8 (complex_category_shift = self_report group) answered wrong
    assert has_tag(tags, "strategy_shift_difficulty"), \
        f"Expected strategy_shift_difficulty, got: {tag_ids(tags)}"

    # Self-correction present
    assert has_tag(tags, "self_correction_present"), \
        f"Expected self_correction_present, got: {tag_ids(tags)}"

    print("  ✅ PASS: Developing 2nd grader tags match expectations")
    return True


# =============================================================================
# TEST 3: Advanced 3rd Grader (80% — 8/10 correct)
# =============================================================================

def test_logic_advanced_3rd_grade():
    """80% 3-4 student: strong systematic + pattern, no growth-edges."""
    items_lookup = {
        "3_4_1": {"correct_answer_index": 1, "expected_latency_seconds": 35, "item_type": "pattern"},
        "3_4_2": {"correct_answer_index": 1, "expected_latency_seconds": 40, "item_type": "pattern"},
        "3_4_3": {"correct_answer_index": 3, "expected_latency_seconds": 45, "item_type": "odd_one_out"},
        "3_4_4": {"correct_answer_index": 2, "expected_latency_seconds": 60, "item_type": "matrix_multi"},
        "3_4_5": {"correct_answer_index": 1, "expected_latency_seconds": 50, "item_type": "analogy"},
        "3_4_6": {"correct_answer_index": 0, "expected_latency_seconds": 40, "item_type": "conditional_logic"},
        "3_4_7": {"correct_answer_index": 2, "expected_latency_seconds": 45, "item_type": "order_of_operations"},
        "3_4_8": {"correct_answer_index": 0, "expected_latency_seconds": 30, "item_type": "meta_cognitive"},
        "3_4_9": {"correct_answer_index": 0, "expected_latency_seconds": 40, "item_type": "dual_classification"},
        "3_4_10": {"correct_answer_index": 0, "expected_latency_seconds": 50, "item_type": "pattern_creation"},
    }

    # 8/10 correct. Missed: 3_4_5 (analogy) and 3_4_10 (pattern_creation)
    responses = [
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

    tags = tag_logic_test(responses, items_lookup)
    print_tags("TEST 3: Advanced 3-4 (80%)", tags)

    # Pattern correct: 3_4_1 (pattern), 3_4_2 (pattern), 3_4_10 (pattern_creation)=WRONG
    # pattern_creation is in "pattern" group → only 2 correct → pattern_detection_emerging
    assert has_tag(tags, "pattern_detection_emerging"), \
        f"Expected pattern_detection_emerging, got: {tag_ids(tags)}"

    # Multistep correct: 3_4_4 (matrix_multi), 3_4_6 (conditional_logic), 3_4_7 (order_of_operations), 3_4_9 (dual_classification)
    # That's 4 → systematic_problem_solving
    assert has_tag(tags, "systematic_problem_solving"), \
        f"Expected systematic_problem_solving, got: {tag_ids(tags)}"

    # No growth-edge tags (no over-time incorrect, no multiple attempts, no fast inaccurate)
    assert not has_tag(tags, "reasoning_under_load_emerging")
    assert not has_tag(tags, "impulsive_response")
    assert not has_tag(tags, "trial_and_error_approach")

    print("  ✅ PASS: Advanced 3rd grader tags match expectations")
    return True


# =============================================================================
# TEST 4: Deliberately 'rushed' profile — impulsive_response + rushed_spelling
# =============================================================================

def test_rushed_profile():
    """Fast + inaccurate across logic and spelling. Confirm impulsive_response and rushed_spelling fire."""

    # --- LOGIC: fast responses, many wrong ---
    items_lookup = {
        "k1_1": {"correct_answer_index": 1, "expected_latency_seconds": 20, "item_type": "pattern"},
        "k1_2": {"correct_answer_index": 1, "expected_latency_seconds": 25, "item_type": "pattern"},
        "k1_3": {"correct_answer_index": 2, "expected_latency_seconds": 20, "item_type": "odd_one_out"},
        "k1_4": {"correct_answer_index": 1, "expected_latency_seconds": 15, "item_type": "matching"},
        "k1_5": {"correct_answer_index": 0, "expected_latency_seconds": 20, "item_type": "comparison"},
    }

    # All answered in < 50% of expected time, most wrong
    responses = [
        {"item_id": "k1_1", "selected_answer_index": 0, "response_time_seconds": 5, "attempts": 1, "self_corrected": False},   # WRONG, fast
        {"item_id": "k1_2", "selected_answer_index": 3, "response_time_seconds": 8, "attempts": 1, "self_corrected": False},   # WRONG, fast
        {"item_id": "k1_3", "selected_answer_index": 0, "response_time_seconds": 6, "attempts": 1, "self_corrected": False},   # WRONG, fast
        {"item_id": "k1_4", "selected_answer_index": 1, "response_time_seconds": 4, "attempts": 1, "self_corrected": False},   # correct, fast
        {"item_id": "k1_5", "selected_answer_index": 2, "response_time_seconds": 7, "attempts": 1, "self_corrected": False},   # WRONG, fast
    ]

    logic_tags = tag_logic_test(responses, items_lookup)
    print_tags("TEST 4a: Rushed Logic Profile", logic_tags)

    # fast_inaccurate: k1_1 (5 < 20*0.5=10, wrong), k1_2 (8 < 25*0.5=12.5, wrong),
    #                  k1_3 (6 < 20*0.5=10, wrong), k1_5 (7 < 20*0.5=10, wrong) → 4 items
    assert has_tag(logic_tags, "impulsive_response"), \
        f"Expected impulsive_response, got: {tag_ids(logic_tags)}"

    # --- SPELLING: fast slips ---
    spelling_results = [
        {"word": "cat", "user_input": "cet", "type": "regular", "points": 2, "max_points": 3, "mistakes": {"short_vowels": "a"}, "time": 2, "hints_used": 0},
        {"word": "dog", "user_input": "dag", "type": "regular", "points": 2, "max_points": 3, "mistakes": {"short_vowels": "o"}, "time": 1, "hints_used": 0},
        {"word": "sun", "user_input": "sun", "type": "regular", "points": 3, "max_points": 3, "mistakes": {}, "time": 2, "hints_used": 0},
        {"word": "to", "user_input": "to", "type": "sight", "points": 1, "max_points": 1, "mistakes": {}, "time": 1, "hints_used": 0},
        {"word": "he", "user_input": "hi", "type": "sight", "points": 0, "max_points": 1, "mistakes": {"spelling": "Expected 'he', got 'hi'"}, "time": 1, "hints_used": 0},
    ]

    spelling_tags = tag_spelling_test(spelling_results, "Kindergarten")
    print_tags("TEST 4b: Rushed Spelling Profile", spelling_tags)

    # fast_slips: cat (time=2 < 3, wrong), dog (time=1 < 3, wrong), he (time=1 < 3, wrong) → 3
    assert has_tag(spelling_tags, "rushed_spelling"), \
        f"Expected rushed_spelling, got: {tag_ids(spelling_tags)}"

    print("  ✅ PASS: Rushed profile fires impulsive_response + rushed_spelling")
    return True


# =============================================================================
# TEST 5: 'Listens better than reads' profile
# =============================================================================

def test_listens_better_than_reads():
    """
    Strong listening comprehension + good speaking but weaker spelling.
    Confirm listening_comprehension_strong + speaking strength tags fire.
    """

    # --- COMPREHENSION: 7/8 correct (87.5%) ---
    comprehension_results = [
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
                {"question_id": "k2_q4", "is_correct": False},  # missed one
            ]
        }
    ]

    # All questions are literal for kindergarten
    question_types = {
        "k1_q1": "literal",
        "k1_q2": "literal",
        "k1_q3": "literal",
        "k1_q4": "literal",
        "k2_q1": "literal",
        "k2_q2": "literal",
        "k2_q3": "literal",
        "k2_q4": "vocabulary",  # the only vocabulary question, missed
    }

    comp_tags = tag_comprehension_test(comprehension_results, question_types)
    print_tags("TEST 5a: Strong Listening Comprehension", comp_tags)

    # overall_accuracy = 7/8 = 0.875 → listening_comprehension_strong (>= 0.75)
    assert has_tag(comp_tags, "listening_comprehension_strong"), \
        f"Expected listening_comprehension_strong, got: {tag_ids(comp_tags)}"

    # literal_accuracy = 7/7 = 1.0 → literal_comprehension_strong
    assert has_tag(comp_tags, "literal_comprehension_strong"), \
        f"Expected literal_comprehension_strong, got: {tag_ids(comp_tags)}"

    # --- SPEAKING: high fluency scores ---
    speaking_results = [
        {"sentence_id": "k1", "status": "Answered", "pronunciation": {"score": 90}, "fluency": {"score": 85}, "overall": {"score": 88}, "difficulty": "easy"},
        {"sentence_id": "k2", "status": "Answered", "pronunciation": {"score": 88}, "fluency": {"score": 82}, "overall": {"score": 85}, "difficulty": "easy"},
        {"sentence_id": "k3", "status": "Answered", "pronunciation": {"score": 92}, "fluency": {"score": 88}, "overall": {"score": 90}, "difficulty": "easy"},
        {"sentence_id": "k4", "status": "Answered", "pronunciation": {"score": 85}, "fluency": {"score": 80}, "overall": {"score": 83}, "difficulty": "medium"},
    ]

    speaking_tags = tag_speaking_test(speaking_results)
    print_tags("TEST 5b: Strong Speaking Skills", speaking_tags)

    # avg_pronunciation = (90+88+92+85)/4 / 100 = 0.8875 → pronunciation_accurate (>= 0.85)
    assert has_tag(speaking_tags, "pronunciation_accurate"), \
        f"Expected pronunciation_accurate, got: {tag_ids(speaking_tags)}"

    # avg_fluency = (85+82+88+80)/4 / 100 = 0.8375 → expressive_fluency_strong (>= 0.8)
    assert has_tag(speaking_tags, "expressive_fluency_strong"), \
        f"Expected expressive_fluency_strong, got: {tag_ids(speaking_tags)}"

    print("  ✅ PASS: Listens-better-than-reads profile confirmed")
    return True


# =============================================================================
# TEST 6: Self-report tags emitted as LOW confidence
# =============================================================================

def test_self_report_low_confidence():
    """Self-report items (strategy_shift_difficulty) must emit as confidence=low."""
    items_lookup = {
        "1_2_8": {"correct_answer_index": 0, "expected_latency_seconds": 45, "item_type": "category_shift"},
        "1_2_1": {"correct_answer_index": 2, "expected_latency_seconds": 25, "item_type": "pattern"},
    }

    # Only answer the self-report item wrong to trigger strategy_shift_difficulty
    responses = [
        {"item_id": "1_2_8", "selected_answer_index": 2, "response_time_seconds": 40, "attempts": 1, "self_corrected": False},  # WRONG self-report
        {"item_id": "1_2_1", "selected_answer_index": 2, "response_time_seconds": 20, "attempts": 1, "self_corrected": False},  # correct
    ]

    tags = tag_logic_test(responses, items_lookup)
    print_tags("TEST 6: Self-Report Low Confidence Check", tags)

    # strategy_shift_difficulty should fire with confidence=low
    ssd_tag = get_tag(tags, "strategy_shift_difficulty")
    assert ssd_tag is not None, f"Expected strategy_shift_difficulty, got: {tag_ids(tags)}"
    assert ssd_tag["confidence"] == "low", \
        f"Expected confidence='low', got: '{ssd_tag['confidence']}'"

    # Verify other tags are high confidence
    for t in tags:
        if t["id"] != "strategy_shift_difficulty":
            assert t["confidence"] == "high", \
                f"Non-self-report tag {t['id']} should be high confidence, got: {t['confidence']}"

    print("  ✅ PASS: Self-report tags correctly emit as low confidence")
    return True


# =============================================================================
# TEST 7: Spelling strength profile
# =============================================================================

def test_spelling_strength_profile():
    """All features correct → phonetic_strategy_strong + vowel_accuracy_strong + sight_word_recognition_strong."""
    spelling_results = [
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

    tags = tag_spelling_test(spelling_results, "Kindergarten")
    print_tags("TEST 7: Spelling Strength Profile", tags)

    # All regular correct, no mistakes → beginning=1.0, final=1.0, vowel=1.0
    assert has_tag(tags, "phonetic_strategy_strong"), \
        f"Expected phonetic_strategy_strong, got: {tag_ids(tags)}"

    # vowel_error_count == 0
    assert has_tag(tags, "vowel_accuracy_strong"), \
        f"Expected vowel_accuracy_strong, got: {tag_ids(tags)}"

    # All sight words correct: 5/5 = 1.0
    assert has_tag(tags, "sight_word_recognition_strong"), \
        f"Expected sight_word_recognition_strong, got: {tag_ids(tags)}"

    # No growth-edge tags
    assert not has_tag(tags, "vowel_difficulty_emerging")
    assert not has_tag(tags, "rushed_spelling")

    print("  ✅ PASS: Spelling strength profile confirmed")
    return True


# =============================================================================
# TEST 8: Full pipeline — tag_all_tests
# =============================================================================

def test_tag_all_tests():
    """Run all four tests together through the orchestrator."""
    items_lookup = {
        "k1_1": {"correct_answer_index": 1, "expected_latency_seconds": 20, "item_type": "pattern"},
        "k1_2": {"correct_answer_index": 1, "expected_latency_seconds": 25, "item_type": "pattern"},
        "k1_3": {"correct_answer_index": 2, "expected_latency_seconds": 20, "item_type": "odd_one_out"},
    }

    logic_responses = [
        {"item_id": "k1_1", "selected_answer_index": 1, "response_time_seconds": 15, "attempts": 1, "self_corrected": False},
        {"item_id": "k1_2", "selected_answer_index": 1, "response_time_seconds": 18, "attempts": 1, "self_corrected": False},
        {"item_id": "k1_3", "selected_answer_index": 2, "response_time_seconds": 12, "attempts": 1, "self_corrected": False},
    ]

    result = tag_all_tests(
        logic_responses=logic_responses,
        logic_items_lookup=items_lookup,
        spelling_results=None,
        spelling_grade=None,
        speaking_results=None,
        comprehension_results=None,
        comprehension_question_types=None,
    )

    assert "logic_quest" in result
    assert isinstance(result["logic_quest"], list)
    # word_wizard, voice_challenge, story_explorer should not be present
    assert "word_wizard" not in result
    assert "voice_challenge" not in result
    assert "story_explorer" not in result

    print_tags("TEST 8: tag_all_tests (logic only)", result["logic_quest"])
    print("  ✅ PASS: tag_all_tests orchestrator works correctly")
    return True


# =============================================================================
# RUNNER
# =============================================================================

def run_all_tests():
    print("\n" + "=" * 70)
    print("  DEAR PARENT TAGGING ENGINE — VERIFICATION SUITE")
    print("=" * 70)

    tests = [
        ("1. High-Performing K-1 (90%)", test_logic_high_performer_k1),
        ("2. Developing 2nd Grader (60%)", test_logic_developing_2nd_grade),
        ("3. Advanced 3rd Grader (80%)", test_logic_advanced_3rd_grade),
        ("4. Rushed Profile (impulsive)", test_rushed_profile),
        ("5. Listens Better Than Reads", test_listens_better_than_reads),
        ("6. Self-Report Low Confidence", test_self_report_low_confidence),
        ("7. Spelling Strength Profile", test_spelling_strength_profile),
        ("8. Full Pipeline Orchestrator", test_tag_all_tests),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_fn in tests:
        try:
            result = test_fn()
            if result:
                passed += 1
            else:
                failed += 1
                errors.append(f"  ❌ {name}: returned False")
        except AssertionError as e:
            failed += 1
            errors.append(f"  ❌ {name}: {str(e)}")
        except Exception as e:
            failed += 1
            errors.append(f"  ❌ {name}: EXCEPTION — {type(e).__name__}: {str(e)}")

    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    if errors:
        print("\n  FAILURES:")
        for e in errors:
            print(e)

    if failed == 0:
        print("\n  🎉 ALL TESTS PASSED — Tagging engine verified!\n")
    else:
        print(f"\n  ⚠️  {failed} test(s) need attention.\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
