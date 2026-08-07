"""
Proper regression tests for the per-question tagging functions:
  tag_logic_per_item, tag_spelling_per_word,
  tag_speaking_per_sentence, tag_comprehension_per_question

Also exercises get_tag_info / attach_tag_scores (confidence + weight lookup).
Run: python test_per_question_tags.py
"""

from main import score_response, word_lists
from logic_assessment import get_items_by_grade, GradeLevel
from tagging_engine import (
    tag_logic_per_item,
    tag_spelling_per_word,
    tag_speaking_per_sentence,
    tag_comprehension_per_question,
    get_tag_info,
    attach_tag_scores,
    TAG_METADATA,
)

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {label}")
    else:
        failed += 1
        print(f"  FAIL: {label}")


# =============================================================================
# 1. TAG SCORE / CONFIDENCE LOOKUP
# =============================================================================
print("=" * 70)
print("TEST: get_tag_info / attach_tag_scores")
print("=" * 70)

info = get_tag_info("phonetic_strategy_strong")
check("phonetic_strategy_strong has confidence=high", info["confidence"] == "high")
check("phonetic_strategy_strong weight == 1.0", info["weight"] == 1.0)

info_low = get_tag_info("rule_maintenance_difficulty")
check("rule_maintenance_difficulty has confidence=low", info_low["confidence"] == "low")
check("rule_maintenance_difficulty weight == 0.3", info_low["weight"] == 0.3)

info_unknown = get_tag_info("0")
check("'0' sentinel has weight 0.0", info_unknown["weight"] == 0.0)

scored = attach_tag_scores(["phonetic_strategy_strong", "vowel_difficulty_emerging"])
check("attach_tag_scores returns 2 entries", len(scored) == 2)
check("attach_tag_scores entry has tag/confidence/weight/polarity keys",
      all(k in scored[0] for k in ["tag", "confidence", "weight", "polarity"]))

check("every tag in config has a valid confidence", all(
    v["confidence"] in ("high", "medium", "low") for v in TAG_METADATA.values()
))


# =============================================================================
# 2. LOGIC QUEST — tag_logic_per_item, all 4 grades, all items answered
# =============================================================================
print()
print("=" * 70)
print("TEST: tag_logic_per_item -- all grades, all items answered correctly")
print("=" * 70)

for grade in [GradeLevel.KINDERGARTEN_1, GradeLevel.GRADE_1_2, GradeLevel.GRADE_2_3, GradeLevel.GRADE_3_4]:
    items = get_items_by_grade(grade)
    items_lookup = {
        item.item_id: {
            "item_number": item.item_number,
            "correct_answer_index": item.correct_answer_index,
            "primary_tag": str(item.primary_tag.value),
            "conditional_tags": {k: v.value for k, v in item.conditional_tags.items()},
        }
        for item in items
    }
    responses = [{"item_id": item.item_id, "selected_answer_index": item.correct_answer_index} for item in items]
    result = tag_logic_per_item(responses, items_lookup)

    check(f"{grade.value}: {len(items)} items -> {len(result)} tagged entries", len(result) == len(items))
    check(f"{grade.value}: all answered", all(r["answered"] for r in result))
    check(f"{grade.value}: all correct", all(r["is_correct"] for r in result))
    check(f"{grade.value}: every item has non-empty tags", all(len(r["tags"]) > 0 for r in result))
    check(f"{grade.value}: all tags are known", all(
        get_tag_info(t)["confidence"] is not None for r in result for t in r["tags"]
    ))

# unanswered case
grade = GradeLevel.KINDERGARTEN_1
items = get_items_by_grade(grade)
items_lookup = {
    item.item_id: {
        "item_number": item.item_number,
        "correct_answer_index": item.correct_answer_index,
        "primary_tag": str(item.primary_tag.value),
        "conditional_tags": {k: v.value for k, v in item.conditional_tags.items()},
    }
    for item in items
}
result = tag_logic_per_item([], items_lookup)
check("K-1 with zero responses: all unanswered", all(not r["answered"] for r in result))
check("K-1 with zero responses: all tags == ['0']", all(r["tags"] == ["0"] for r in result))


# =============================================================================
# 3. WORD WIZARD — tag_spelling_per_word, all 4 grades, full word lists
# =============================================================================
print()
print("=" * 70)
print("TEST: tag_spelling_per_word -- all grades, full word lists, all correct")
print("=" * 70)

for grade in ["Kindergarten", "First", "Second", "Third"]:
    regular_words = list(word_lists[grade]["regular_words"].keys())
    sight_words = list(word_lists[grade].get("sight_words", {}).keys())
    results = []
    for w in regular_words:
        scored = score_response(w, w, grade, "regular")
        results.append({"word": w, "user_input": w, "type": "regular",
                         "points": scored["points"], "max_points": scored["max_points"],
                         "mistakes": scored["mistakes"], "hints_used": 0, "time": 5})
    for w in sight_words:
        scored = score_response(w, w, grade, "sight")
        results.append({"word": w, "user_input": w, "type": "sight",
                         "points": scored["points"], "max_points": scored["max_points"],
                         "mistakes": scored["mistakes"], "hints_used": 0, "time": 5})

    tagged = tag_spelling_per_word(results)
    check(f"{grade}: {len(results)} words -> {len(tagged)} tagged entries", len(tagged) == len(results))
    check(f"{grade}: every regular word has max_points > 0", all(
        r["max_points"] > 0 for r in results if r["type"] == "regular"
    ))
    check(f"{grade}: all correct -> is_correct True everywhere", all(t["is_correct"] for t in tagged))
    check(f"{grade}: every regular word tagged phonetic_strategy_strong", all(
        "phonetic_strategy_strong" in t["tags"] for t, r in zip(tagged, results) if r["type"] == "regular"
    ))
    check(f"{grade}: every sight word tagged sight_word_recognition_strong", all(
        "sight_word_recognition_strong" in t["tags"] for t, r in zip(tagged, results) if r["type"] == "sight"
    ))

# unanswered
unanswered_case = [{"word": "cat", "user_input": "", "type": "regular", "points": 0, "max_points": 3, "mistakes": {}}]
tagged = tag_spelling_per_word(unanswered_case)
check("unanswered word -> tags == ['0']", tagged[0]["tags"] == ["0"])
check("unanswered word -> answered == False", tagged[0]["answered"] is False)


# =============================================================================
# 4. VOICE CHALLENGE — tag_speaking_per_sentence
# =============================================================================
print()
print("=" * 70)
print("TEST: tag_speaking_per_sentence")
print("=" * 70)

speaking_cases = [
    {"sentence_id": "s1", "status": "Answered", "fluency": {"score": 0.9}, "pronunciation": {"score": 0.9},
     "overall": {"score": 0.9}, "grammar": {"score": 0.85}, "difficulty": "hard"},
    {"sentence_id": "s2", "status": "Answered", "fluency": {"score": 0.5}, "pronunciation": {"score": 0.5},
     "overall": {"score": 0.5}, "grammar": {"score": 0.4}, "difficulty": "easy"},
    {"sentence_id": "s3", "status": "Not Attempted"},
]
tagged = tag_speaking_per_sentence(speaking_cases)
check("3 sentences -> 3 tagged entries", len(tagged) == 3)
check("s1 (high scores, hard) -> expressive_fluency_strong", "expressive_fluency_strong" in tagged[0]["tags"])
check("s1 (high scores, hard) -> complex_syntax_confident", "complex_syntax_confident" in tagged[0]["tags"])
check("s2 (low scores) -> pronunciation_developing", "pronunciation_developing" in tagged[1]["tags"])
check("s2 (low scores) -> prosody_emerging", "prosody_emerging" in tagged[1]["tags"])
check("s3 (not attempted) -> tags == ['0']", tagged[2]["tags"] == ["0"])


# =============================================================================
# 5. STORY EXPLORER — tag_comprehension_per_question
# =============================================================================
print()
print("=" * 70)
print("TEST: tag_comprehension_per_question")
print("=" * 70)

comp_results = [{
    "story_id": "st1",
    "questions": [
        {"question_id": "q_lit_correct", "selected_index": 0, "is_correct": True},
        {"question_id": "q_lit_wrong", "selected_index": 1, "is_correct": False},
        {"question_id": "q_inf_correct", "selected_index": 0, "is_correct": True},
        {"question_id": "q_inf_wrong", "selected_index": 1, "is_correct": False},
        {"question_id": "q_voc_correct", "selected_index": 0, "is_correct": True},
        {"question_id": "q_voc_wrong", "selected_index": 1, "is_correct": False},
        {"question_id": "q_unanswered", "selected_index": -1, "is_correct": False},
    ]
}]
q_types = {
    "q_lit_correct": "literal", "q_lit_wrong": "literal",
    "q_inf_correct": "inferential", "q_inf_wrong": "inferential",
    "q_voc_correct": "vocabulary", "q_voc_wrong": "vocabulary",
    "q_unanswered": "literal",
}
tagged = tag_comprehension_per_question(comp_results, q_types)
by_id = {t["question_id"]: t for t in tagged}

check("7 questions -> 7 tagged entries", len(tagged) == 7)
check("literal correct -> literal_comprehension_strong", "literal_comprehension_strong" in by_id["q_lit_correct"]["tags"])
check("literal wrong -> sentinel tag '0' (no official weak tag)", by_id["q_lit_wrong"]["tags"] == ["0"])
check("inferential correct -> inferential_comprehension_strong", "inferential_comprehension_strong" in by_id["q_inf_correct"]["tags"])
check("inferential wrong -> inferential_comprehension_emerging", "inferential_comprehension_emerging" in by_id["q_inf_wrong"]["tags"])
check("vocabulary correct -> vocabulary_in_context_strong", "vocabulary_in_context_strong" in by_id["q_voc_correct"]["tags"])
check("vocabulary wrong -> vocabulary_in_context_emerging", "vocabulary_in_context_emerging" in by_id["q_voc_wrong"]["tags"])
check("unanswered -> tags == ['0']", by_id["q_unanswered"]["tags"] == ["0"])


# =============================================================================
print()
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 70)
if failed == 0:
    print("ALL TESTS PASSED")
else:
    print("SOME TESTS FAILED")
    exit(1)
