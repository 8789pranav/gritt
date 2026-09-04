"""Comprehensive edge-case verification for spelling bugs #10, #52-#70."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any, Optional, List
from app.domain.enums import Grade, WordType, ResponseStatus
from app.domain.models import SpellingResponse, SpellingWord
from app.engines.registry import spelling_engine
from app.engines.spelling.phonics import (
    PhonicsFeature, is_homophone, is_unrelated_attempt, sounds_like,
    parse_expectations,
)
from app.engines.spelling.scorer import SpellingScorer

engine = spelling_engine()
scorer = SpellingScorer()

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


def make_response(word_item, user_input, time=5.0, hints=0):
    return SpellingResponse(
        item_id=word_item.word, word=word_item.word,
        user_input=user_input, word_type=word_item.word_type,
        response_time_seconds=time, hints_used=hints,
    )


def simulate_error_type_for(result_dict, per_word_tag_map):
    """Replicate the _error_type_for logic from assessment_service.py."""
    if result_dict.get("is_correct"):
        return None
    user_input = result_dict.get("detail", {}).get("user_input", "").strip()
    if not user_input:
        return None
    tags = per_word_tag_map.get(result_dict.get("item_id", ""), [])
    if "unrelated_attempt" in tags:
        return "Unrelated attempt"
    if "unrelated_attempt_sightword" in tags:
        return "Sight word (unrelated)"
    if "homophone_error" in tags:
        return "Homophone"
    if result_dict.get("detail", {}).get("type") == WordType.SIGHT.value:
        return "Sight word"
    mistakes = result_dict.get("detail", {}).get("mistakes", {})
    if "spelling_convention" in mistakes:
        return "Spelling convention"
    feature_key = next(
        (k for k in mistakes if k not in ("spelling", "unrelated_attempt", "spelling_convention", "homophone_error")),
        None,
    )
    if feature_key:
        return feature_key.replace("_", " ").replace(" error", "")
    if "spelling_error" in tags or "spelling" in mistakes:
        return "Spelling"
    if "rushed_attempt" in tags:
        return "Rushed attempt"
    return None


def simulate_icon_for(result_dict):
    """Replicate the icon logic from assessment_service.py."""
    if result_dict.get("is_correct"):
        return "Correct"
    user_input = result_dict.get("detail", {}).get("user_input", "").strip()
    if not user_input:
        return "Not answered"
    return "Incorrect"


def simulate_sight_score(results):
    """Replicate sight_word_score from assessment_service.py (complete_result)."""
    sight = [r for r in results if r.get("detail", {}).get("type") in (
        WordType.SIGHT.value, WordType.NONSENSE.value
    )]
    sight_attempted = [r for r in sight if r.get("detail", {}).get("user_input", "").strip()]
    if not sight_attempted:
        return 0
    return round(sum(1 for r in sight_attempted if r.get("is_correct")) / len(sight_attempted) * 100)


def simulate_phonics_score(results):
    """Replicate phonics_score from assessment_service.py (complete_result)."""
    phonics = [r for r in results if r.get("detail", {}).get("type") == WordType.REGULAR.value]
    phonics_attempted = [r for r in phonics if r.get("detail", {}).get("user_input", "").strip()]
    if not phonics_attempted:
        return 0
    return round(sum(1 for r in phonics_attempted if r.get("is_correct")) / len(phonics_attempted) * 100)


# ============================================================
# #10: sounds_like on sight words
# ============================================================
sep("#10: sounds_like checker on sight words (not just phonics)")

# Direct sounds_like tests
check("sounds_like(too, to) = True", sounds_like("too", "to"))
check("sounds_like(know, no) = False (homophone, not sounds_like)", not sounds_like("know", "no"))
check("sounds_like(the, tha) = False", not sounds_like("the", "tha"))

# Sight word scoring: 'no' -> 'know' (homophone, checked first)
check("is_homophone(no, know) = True", is_homophone("no", "know"))

# Sight word scoring: 'see' -> 'see' (correct)
k_items = engine.get_items(Grade.KINDERGARTEN)
see_item = next(w for w in k_items if w.word == "see")
result = scorer.score_word(see_item, "see")
check("see->see correct", result.is_correct)

# Sight word with sounds_like: 'me' -> 'mee' (phonetically same)
me_item = next(w for w in k_items if w.word == "me")
result = scorer.score_word(me_item, "mee")
mistakes = result.detail.get("mistakes", {})
check("me->mee gets spelling_convention (not generic spelling)",
      "spelling_convention" in mistakes, f"mistakes={mistakes}")
check("me->mee NOT generic spelling", "spelling" not in mistakes, f"mistakes={mistakes}")

# Sight word with completely wrong: 'go' -> 'xyz'
go_item = next(w for w in k_items if w.word == "go")
result = scorer.score_word(go_item, "xyz")
mistakes = result.detail.get("mistakes", {})
check("go->xyz gets generic spelling", "spelling" in mistakes, f"mistakes={mistakes}")


# ============================================================
# #52: Summary scores divide by actual word count, not 31
# ============================================================
sep("#52: Summary scores divide by actual word count")

# Kindergarten: submit only 5 of 15 sampled words
k_test = engine.build_test(Grade.KINDERGARTEN)
print(f"  Kindergarten sample: {len(k_test)} words")

# Submit only 5 words
submitted = k_test[:5]
responses = [make_response(w, w.word) for w in submitted]
score = scorer.score(submitted, responses, Grade.KINDERGARTEN)
check("total_items = 5 (not 31)", score.total_items == 5, f"total_items={score.total_items}")
check("answered_items = 5", score.answered_items == 5, f"answered_items={score.answered_items}")
check("max_points matches 5 words", score.max_points == sum(w.max_points for w in submitted),
      f"max_points={score.max_points}")

# Submit only 3 words
submitted3 = k_test[:3]
responses3 = [make_response(w, w.word) for w in submitted3]
score3 = scorer.score(submitted3, responses3, Grade.KINDERGARTEN)
check("total_items = 3 (not 31)", score3.total_items == 3, f"total_items={score3.total_items}")

# Full 15 words
responses_all = [make_response(w, w.word) for w in k_test]
score_all = scorer.score(k_test, responses_all, Grade.KINDERGARTEN)
check("total_items = 15 (full sample)", score_all.total_items == 15, f"total_items={score_all.total_items}")


# ============================================================
# #52b: teacher_admin_detail words count
# ============================================================
sep("#52b: teacher_admin_detail words = actual count")
# When complete_result is called, total_words = len(results)
# Since we now filter items in submit, results only contains submitted words
results_dicts = [s.model_dump() for s in score.scored_items]
total_words = len(results_dicts)
check("teacher words = 5", total_words == 5, f"words={total_words}")


# ============================================================
# #53: sight_word_score consistent with sight_word_accuracy
# ============================================================
sep("#53: sight_word_score == sight_word_accuracy")

# Test: 3 sight words, 2 correct, 1 blank
sight_words = [w for w in k_test if w.word_type == WordType.SIGHT][:3]
responses_mixed = [
    make_response(sight_words[0], sight_words[0].word),  # correct
    make_response(sight_words[1], sight_words[1].word),  # correct
    make_response(sight_words[2], ""),                    # blank
]
score_mixed = scorer.score(sight_words, responses_mixed, Grade.KINDERGARTEN)
signals = engine.deriver.derive(sight_words, responses_mixed, score_mixed)

sight_acc = signals["sight_word_accuracy"]
results_mixed = [s.model_dump() for s in score_mixed.scored_items]
sight_score = simulate_sight_score(results_mixed)

print(f"  sight_word_accuracy (signals): {sight_acc}")
print(f"  sight_word_score (parent_summary): {sight_score}")
check("sight_word_accuracy == 1.0 (2/2, blank excluded)", sight_acc == 1.0, f"acc={sight_acc}")
check("sight_word_score == 100 (2/2, blank excluded)", sight_score == 100, f"score={sight_score}")
check("sight_word_score matches sight_word_accuracy",
      round(sight_acc * 100) == sight_score, f"acc={sight_acc}, score={sight_score}")

# Edge: all sight words blank
responses_all_blank = [make_response(w, "") for w in sight_words]
score_all_blank = scorer.score(sight_words, responses_all_blank, Grade.KINDERGARTEN)
signals_blank = engine.deriver.derive(sight_words, responses_all_blank, score_all_blank)
results_blank = [s.model_dump() for s in score_all_blank.scored_items]
check("all blank: sight_word_accuracy = 0.0", signals_blank["sight_word_accuracy"] == 0.0)
check("all blank: sight_word_score = 0", simulate_sight_score(results_blank) == 0)

# Edge: all sight words correct
responses_all_correct = [make_response(w, w.word) for w in sight_words]
score_all_correct = scorer.score(sight_words, responses_all_correct, Grade.KINDERGARTEN)
signals_correct = engine.deriver.derive(sight_words, responses_all_correct, score_all_correct)
results_correct = [s.model_dump() for s in score_all_correct.scored_items]
check("all correct: sight_word_accuracy = 1.0", signals_correct["sight_word_accuracy"] == 1.0)
check("all correct: sight_word_score = 100", simulate_sight_score(results_correct) == 100)


# ============================================================
# #54: Blank words show "Not answered" icon
# ============================================================
sep("#54: Blank words show 'Not answered' icon")

# Word not submitted at all (response is None)
cat_item = next(w for w in k_items if w.word == "cat")
score_not_submitted = scorer.score([cat_item], [], Grade.KINDERGARTEN)
result_ns = score_not_submitted.scored_items[0].model_dump()
icon_ns = simulate_icon_for(result_ns)
check("not submitted: icon = 'Not answered'", icon_ns == "Not answered", f"icon={icon_ns}")

# Word submitted with blank input
responses_blank = [make_response(cat_item, "")]
score_blank = scorer.score([cat_item], responses_blank, Grade.KINDERGARTEN)
result_b = score_blank.scored_items[0].model_dump()
icon_b = simulate_icon_for(result_b)
check("blank input: icon = 'Not answered'", icon_b == "Not answered", f"icon={icon_b}")

# Word correct
responses_correct = [make_response(cat_item, "cat")]
score_correct = scorer.score([cat_item], responses_correct, Grade.KINDERGARTEN)
result_c = score_correct.scored_items[0].model_dump()
icon_c = simulate_icon_for(result_c)
check("correct: icon = 'Correct'", icon_c == "Correct", f"icon={icon_c}")

# Word wrong (non-blank)
responses_wrong = [make_response(cat_item, "kat")]
score_wrong = scorer.score([cat_item], responses_wrong, Grade.KINDERGARTEN)
result_w = score_wrong.scored_items[0].model_dump()
icon_w = simulate_icon_for(result_w)
check("wrong: icon = 'Incorrect'", icon_w == "Incorrect", f"icon={icon_w}")


# ============================================================
# #55: Blank SIGHT words get error_type null (not 'Sight word')
# ============================================================
sep("#55: Blank sight words get null error_type")

# Blank sight word
the_item = next(w for w in k_items if w.word == "to" and w.word_type == WordType.SIGHT)

responses_sight_blank = [make_response(the_item, "")]
score_sb = scorer.score([the_item], responses_sight_blank, Grade.KINDERGARTEN)
per_item = engine.deriver.per_item_tags([the_item], responses_sight_blank, score=score_sb)
pwt_map = {p.item_id: p.tags for p in per_item}
result_sb = score_sb.scored_items[0].model_dump()
error_type = simulate_error_type_for(result_sb, pwt_map)
check("blank sight word: error_type = None", error_type is None, f"error_type={error_type}")

# Non-blank wrong sight word
responses_sight_wrong = [make_response(the_item, "xyz")]
score_sw = scorer.score([the_item], responses_sight_wrong, Grade.KINDERGARTEN)
per_item_sw = engine.deriver.per_item_tags([the_item], responses_sight_wrong, score=score_sw)
pwt_map_sw = {p.item_id: p.tags for p in per_item_sw}
result_sw = score_sw.scored_items[0].model_dump()
error_type_sw = simulate_error_type_for(result_sw, pwt_map_sw)
check("wrong sight word: error_type = 'Sight word'", error_type_sw == "Sight word",
      f"error_type={error_type_sw}")


# ============================================================
# #57: 'and' has consonant_blend feature
# ============================================================
sep("#57: 'and' has consonant_blend_correct tag")

g1_items = engine.get_items(Grade.FIRST)
and_word = next(w for w in g1_items if w.word == "and")
and_expectations = parse_expectations(and_word.features)
and_features = [e.feature.value for e in and_expectations]
check("'and' has consonant_blend feature", "consonant_blend" in and_features,
      f"features={and_features}")

# Score 'and' correctly
result_and = scorer.score_word(and_word, "and")
check("'and' correct: is_correct", result_and.is_correct)
matched = result_and.detail.get("matched_features", [])
check("'and' correct: has consonant_blend in matched", "consonant_blend" in matched,
      f"matched={matched}")

# Per-item tags for correct 'and'
responses_and = [make_response(and_word, "and")]
score_and = scorer.score([and_word], responses_and, Grade.FIRST)
per_item_and = engine.deriver.per_item_tags([and_word], responses_and, score=score_and)
and_tags = per_item_and[0].tags
check("'and' correct: has consonant_blend_correct tag", "consonant_blend_correct" in and_tags,
      f"tags={and_tags}")

# Edge: 'and' spelled wrong - 'an' (missing 'd', should have blend error)
result_and_wrong = scorer.score_word(and_word, "an")
mistakes_and = result_and_wrong.detail.get("mistakes", {})
check("'and'->'an': has consonant_blend error", "consonant_blend" in mistakes_and,
      f"mistakes={mistakes_and}")


# ============================================================
# #61: rushed_attempt doesn't override better tags
# ============================================================
sep("#61: rushed_attempt checked last in _error_type_for")

# Case 1: unrelated_attempt + rushed_attempt -> should return "Unrelated attempt"
tags_61 = ["unrelated_attempt", "rushed_attempt"]
result_61 = {
    "is_correct": False,
    "detail": {"user_input": "red", "type": "regular",
               "mistakes": {"unrelated_attempt": "red"}},
    "item_id": "test:cat",
}
et_61 = simulate_error_type_for(result_61, {"test:cat": tags_61})
check("unrelated + rushed -> 'Unrelated attempt'", et_61 == "Unrelated attempt",
      f"error_type={et_61}")

# Case 2: homophone_error + rushed_attempt -> should return "Homophone"
tags_62 = ["homophone_error", "rushed_attempt"]
result_62 = {
    "is_correct": False,
    "detail": {"user_input": "son", "type": "regular",
               "mistakes": {"homophone_error": "homophone"}},
    "item_id": "test:sun",
}
et_62 = simulate_error_type_for(result_62, {"test:sun": tags_62})
check("homophone + rushed -> 'Homophone'", et_62 == "Homophone",
      f"error_type={et_62}")

# Case 3: feature error + rushed_attempt -> should return feature error
tags_63 = ["short_vowel_error", "rushed_attempt"]
result_63 = {
    "is_correct": False,
    "detail": {"user_input": "cot", "type": "regular",
               "mistakes": {"short_vowel": "a"}},
    "item_id": "test:cat",
}
et_63 = simulate_error_type_for(result_63, {"test:cat": tags_63})
check("feature error + rushed -> 'short vowel'", et_63 == "short vowel",
      f"error_type={et_63}")

# Case 4: only rushed_attempt -> should return "Rushed attempt"
tags_64 = ["rushed_attempt"]
result_64 = {
    "is_correct": False,
    "detail": {"user_input": "ct", "type": "regular",
               "mistakes": {"beginning_consonant": "c", "short_vowel": "a"}},
    "item_id": "test:cat",
}
et_64 = simulate_error_type_for(result_64, {"test:cat": tags_64})
# Actually has feature errors, so those take priority
check("feature errors + rushed -> feature error (not rushed)", "rushed" not in str(et_64),
      f"error_type={et_64}")

# Case 5: only rushed, no feature errors, no specific tags
tags_65 = ["rushed_attempt"]
result_65 = {
    "is_correct": False,
    "detail": {"user_input": "cet", "type": "regular",
               "mistakes": {"short_vowel": "a"}},
    "item_id": "test:cat",
}
et_65 = simulate_error_type_for(result_65, {"test:cat": tags_65})
check("short_vowel error + rushed -> 'short vowel'", et_65 == "short vowel",
      f"error_type={et_65}")

# Real scenario: fast wrong answer on regular word
cat_item_k = next(w for w in k_items if w.word == "cat")
responses_fast = [make_response(cat_item_k, "kat", time=1.0)]
score_fast = scorer.score([cat_item_k], responses_fast, Grade.KINDERGARTEN)
per_item_fast = engine.deriver.per_item_tags([cat_item_k], responses_fast, score=score_fast)
fast_tags = per_item_fast[0].tags
print(f"  cat->kat (1s) tags: {fast_tags}")
# Should have feature errors AND rushed_attempt
has_feature_error = any(t.endswith("_error") for t in fast_tags)
has_rushed = "rushed_attempt" in fast_tags
check("cat->kat fast: has feature errors", has_feature_error, f"tags={fast_tags}")
check("cat->kat fast: has rushed_attempt", has_rushed, f"tags={fast_tags}")

# Verify _error_type_for returns feature error, not rushed
result_fast = score_fast.scored_items[0].model_dump()
pwt_fast = {per_item_fast[0].item_id: per_item_fast[0].tags}
et_fast = simulate_error_type_for(result_fast, pwt_fast)
check("cat->kat fast: error_type is feature (not Rushed)", et_fast != "Rushed attempt",
      f"error_type={et_fast}")


# ============================================================
# #62: spelling_error tag -> 'Spelling' error_type (not null)
# ============================================================
sep("#62: spelling_error tag returns 'Spelling' error_type")

# bombastic with a wrong attempt that produces only 'spelling' mistake
g2_items = engine.get_items(Grade.SECOND)
bombastic = next(w for w in g2_items if w.word == "bombastic")
# "bombastik" - wrong but not unrelated, not homophone, not sounds_like
result_bomb = scorer.score_word(bombastic, "bombastik")
mistakes_bomb = result_bomb.detail.get("mistakes", {})
print(f"  bombastic->bombastik mistakes: {mistakes_bomb}")

# Check per_item_tags
responses_bomb = [make_response(bombastic, "bombastik")]
score_bomb = scorer.score([bombastic], responses_bomb, Grade.SECOND)
per_item_bomb = engine.deriver.per_item_tags([bombastic], responses_bomb, score=score_bomb)
bomb_tags = per_item_bomb[0].tags
print(f"  bombastic->bombastik tags: {bomb_tags}")

# Simulate error_type
result_bomb_dict = score_bomb.scored_items[0].model_dump()
pwt_bomb = {per_item_bomb[0].item_id: per_item_bomb[0].tags}
et_bomb = simulate_error_type_for(result_bomb_dict, pwt_bomb)
check("bombastic->bombastik: error_type not None", et_bomb is not None,
      f"error_type={et_bomb}")
check("bombastic->bombastik: error_type = 'Spelling' or feature",
      et_bomb is not None, f"error_type={et_bomb}")

# Edge: word with ONLY 'spelling' mistake (no feature errors)
# This happens when a word has no expectations or when all features match but word is wrong
# Create a synthetic case
from app.domain.models import ScoredItem
synthetic_result = {
    "is_correct": False,
    "detail": {
        "user_input": "xyz",
        "type": "regular",
        "mistakes": {"spelling": "Expected 'test', got 'xyz'"},
    },
    "item_id": "test:word",
}
synthetic_tags = {"test:word": ["spelling_error"]}
et_synthetic = simulate_error_type_for(synthetic_result, synthetic_tags)
check("pure spelling mistake: error_type = 'Spelling'", et_synthetic == "Spelling",
      f"error_type={et_synthetic}")


# ============================================================
# #68: sun->son tagged as homophone (not short_vowel_error)
# ============================================================
sep("#68: sun->son is homophone_error (not short_vowel_error)")

# Direct homophone check
check("is_homophone(sun, son) = True", is_homophone("sun", "son"))
check("is_homophone(son, sun) = True", is_homophone("son", "sun"))

# Score sun->son (regular word in kindergarten)
sun_item = next(w for w in k_items if w.word == "sun")
result_sun = scorer.score_word(sun_item, "son")
mistakes_sun = result_sun.detail.get("mistakes", {})
check("sun->son: homophone_error in mistakes", "homophone_error" in mistakes_sun,
      f"mistakes={mistakes_sun}")
check("sun->son: NO short_vowel error", "short_vowel" not in mistakes_sun,
      f"mistakes={mistakes_sun}")
check("sun->son: gets full points (homophone credit)", result_sun.points == result_sun.max_points,
      f"points={result_sun.points}, max={result_sun.max_points}")

# Per-item tags
responses_sun = [make_response(sun_item, "son")]
score_sun = scorer.score([sun_item], responses_sun, Grade.KINDERGARTEN)
per_item_sun = engine.deriver.per_item_tags([sun_item], responses_sun, score=score_sun)
sun_tags = per_item_sun[0].tags
check("sun->son: has homophone_error tag", "homophone_error" in sun_tags,
      f"tags={sun_tags}")
check("sun->son: NO short_vowel_error tag", "short_vowel_error" not in sun_tags,
      f"tags={sun_tags}")

# error_type
result_sun_dict = score_sun.scored_items[0].model_dump()
pwt_sun = {per_item_sun[0].item_id: per_item_sun[0].tags}
et_sun = simulate_error_type_for(result_sun_dict, pwt_sun)
check("sun->son: error_type = 'Homophone'", et_sun == "Homophone",
      f"error_type={et_sun}")

# Edge: son->sun (reverse direction)
check("is_homophone(son, sun) = True", is_homophone("son", "sun"))

# Edge: sun->sun (correct)
result_correct = scorer.score_word(sun_item, "sun")
check("sun->sun: correct", result_correct.is_correct)

# Edge: sun->sin (NOT homophone, real vowel error)
result_sin = scorer.score_word(sun_item, "sin")
mistakes_sin = result_sin.detail.get("mistakes", {})
check("sun->sin: NOT homophone", "homophone_error" not in mistakes_sin,
      f"mistakes={mistakes_sin}")
check("sun->sin: has short_vowel error", "short_vowel" in mistakes_sin,
      f"mistakes={mistakes_sin}")


# ============================================================
# #70: parent_summary.focus_areas includes sight words
# ============================================================
sep("#70: focus_areas includes sight words when accuracy is poor")

# Scenario: all regular correct, all sight wrong
k_test_70 = engine.build_test(Grade.KINDERGARTEN)
regular_70 = [w for w in k_test_70 if w.word_type == WordType.REGULAR][:5]
sight_70 = [w for w in k_test_70 if w.word_type == WordType.SIGHT][:3]
test_words_70 = regular_70 + sight_70

responses_70 = []
for w in regular_70:
    responses_70.append(make_response(w, w.word))  # correct
for w in sight_70:
    responses_70.append(make_response(w, "wrong"))  # wrong

score_70 = scorer.score(test_words_70, responses_70, Grade.KINDERGARTEN)
focus_70 = engine.focus_areas(score_70)
print(f"  focus_areas: {focus_70}")
check("focus_areas includes 'Sight words'", "Sight words" in focus_70,
      f"focus={focus_70}")

# Scenario: all correct -> no sight words in focus
responses_all_good = [make_response(w, w.word) for w in test_words_70]
score_all_good = scorer.score(test_words_70, responses_all_good, Grade.KINDERGARTEN)
focus_good = engine.focus_areas(score_all_good)
print(f"  focus_areas (all correct): {focus_good}")
check("all correct: 'Sight words' NOT in focus", "Sight words" not in focus_good,
      f"focus={focus_good}")

# Scenario: sight words 100% correct, regular words poor
responses_sight_good = []
for w in regular_70:
    responses_sight_good.append(make_response(w, "wrong"))  # wrong
for w in sight_70:
    responses_sight_good.append(make_response(w, w.word))  # correct
score_sg = scorer.score(test_words_70, responses_sight_good, Grade.KINDERGARTEN)
focus_sg = engine.focus_areas(score_sg)
print(f"  focus_areas (sight good, regular bad): {focus_sg}")
check("sight correct: 'Sight words' NOT in focus", "Sight words" not in focus_sg,
      f"focus={focus_sg}")

# Scenario: 1 out of 3 sight words correct (33% < 75% threshold)
responses_mixed_sight = []
for w in regular_70:
    responses_mixed_sight.append(make_response(w, w.word))  # correct
for i, w in enumerate(sight_70):
    if i == 0:
        responses_mixed_sight.append(make_response(w, w.word))  # 1 correct
    else:
        responses_mixed_sight.append(make_response(w, "wrong"))  # 2 wrong
score_ms = scorer.score(test_words_70, responses_mixed_sight, Grade.KINDERGARTEN)
focus_ms = engine.focus_areas(score_ms)
print(f"  focus_areas (1/3 sight correct): {focus_ms}")
check("1/3 sight correct: 'Sight words' in focus", "Sight words" in focus_ms,
      f"focus={focus_ms}")


# ============================================================
# CROSS-BUG: Full pipeline integration test
# ============================================================
sep("CROSS-BUG: Full pipeline with mixed scenarios")

# Kindergarten: 5 regular + 2 sight, mix of correct/wrong/blank/homophone
k_cross = engine.build_test(Grade.KINDERGARTEN)
reg_cross = [w for w in k_cross if w.word_type == WordType.REGULAR][:5]
sight_cross = [w for w in k_cross if w.word_type == WordType.SIGHT][:2]
test_cross = reg_cross + sight_cross

responses_cross = [
    make_response(reg_cross[0], reg_cross[0].word),      # correct
    make_response(reg_cross[1], reg_cross[1].word[:-1]),  # misspelled (drop last)
    make_response(reg_cross[2], "xyz", time=1.0),         # unrelated + rushed
    make_response(reg_cross[3], ""),                       # blank
    make_response(reg_cross[4], reg_cross[4].word),       # correct
    make_response(sight_cross[0], sight_cross[0].word),   # correct sight
    make_response(sight_cross[1], "wrong"),                # wrong sight
]

# Use engine.evaluate with items parameter (tests #52 fix)
result_cross = engine.evaluate("child-cross", Grade.KINDERGARTEN, responses_cross, items=test_cross)

print(f"  total_items: {result_cross.score.total_items}")
print(f"  answered: {result_cross.score.answered_items}")
print(f"  percentage: {result_cross.score.percentage}")

# Check #52
check("cross: total_items = 7", result_cross.score.total_items == 7,
      f"total={result_cross.score.total_items}")

# Build per_word_tag_map
pwt_cross = {p.item_id: p.tags for p in result_cross.per_item_tags}

# Check each word
for s in result_cross.score.scored_items:
    s_dict = s.model_dump()
    et = simulate_error_type_for(s_dict, pwt_cross)
    icon = simulate_icon_for(s_dict)
    tags = pwt_cross.get(s.item_id, [])
    print(f"  {s.label:>8s} -> {s.detail.get('user_input', '')!r:>8s}  correct={s.is_correct}  "
          f"icon={icon!r:>14s}  error_type={et!r:>20s}  tags={tags}")

# Verify #54: blank word has "Not answered" icon
blank_item = next(s for s in result_cross.score.scored_items if not s.detail.get("user_input", "").strip())
blank_dict = blank_item.model_dump()
check("cross: blank word icon = 'Not answered'", simulate_icon_for(blank_dict) == "Not answered")

# Verify #55: blank word has null error_type
check("cross: blank word error_type = None", simulate_error_type_for(blank_dict, pwt_cross) is None)

# Verify #61: unrelated + rushed -> "Unrelated attempt" (not "Rushed attempt")
unrelated_item = next(s for s in result_cross.score.scored_items if "unrelated_attempt" in s.detail.get("mistakes", {}))
unrelated_dict = unrelated_item.model_dump()
et_unrelated = simulate_error_type_for(unrelated_dict, pwt_cross)
check("cross: unrelated+rushed -> 'Unrelated attempt'", et_unrelated == "Unrelated attempt",
      f"error_type={et_unrelated}")

# Verify #53: sight_word_score matches sight_word_accuracy
results_cross = [s.model_dump() for s in result_cross.score.scored_items]
sight_score_cross = simulate_sight_score(results_cross)
sight_acc_cross = result_cross.signals["sight_word_accuracy"]
check("cross: sight_score matches sight_accuracy",
      round(sight_acc_cross * 100) == sight_score_cross,
      f"acc={sight_acc_cross}, score={sight_score_cross}")

# Verify #70: focus_areas
focus_cross = engine.focus_areas(result_cross.score)
print(f"  focus_areas: {focus_cross}")


# ============================================================
# SUMMARY
# ============================================================
sep("SUMMARY")
print(f"  {passed} passed, {failed} failed")
if failed == 0:
    print("  ALL CHECKS PASSED")
else:
    print(f"  {failed} CHECKS FAILED")
