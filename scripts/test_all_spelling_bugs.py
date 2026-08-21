"""Comprehensive verification of all spelling bug fixes (bugs 1-51)."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.enums import Grade, WordType
from app.domain.models import SpellingResponse
from app.engines.registry import spelling_engine
from app.engines.spelling.phonics import (
    PhonicsFeature, is_homophone, is_unrelated_attempt, sounds_like,
    parse_expectations, _phonetic_key,
)

engine = spelling_engine()

def sep(title):
    print(f"\n{'='*80}\n  {title}\n{'='*80}")

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} {detail}")
        failed += 1

# ── Bug 1,2,3: unrelated_attempt → 0 errors, no score pollution ──
sep("Bugs 1,2,3: unrelated_attempt → 0 errors")
g1 = engine.build_test(Grade.FIRST)
g1_words = {w.word: w for w in g1}
responses = []
for w in g1:
    if w.word == "mud":
        responses.append(SpellingResponse(item_id=w.word, word=w.word, user_input="red",
                                          word_type=w.word_type, response_time_seconds=5.0))
    else:
        responses.append(SpellingResponse(item_id=w.word, word=w.word, user_input=w.word,
                                          word_type=w.word_type, response_time_seconds=5.0))
result = engine.evaluate("child1", Grade.FIRST, responses)
mud_scored = [s for s in result.score.scored_items if s.label == "mud"][0]
check("mud→red has 0 feature errors", "unrelated_attempt" in mud_scored.detail.get("mistakes", {}) and
      len([k for k in mud_scored.detail.get("mistakes", {}) if k != "unrelated_attempt"]) == 0,
      f"mistakes={mud_scored.detail.get('mistakes')}")

# ── Bug 4: one source of truth for correct/wrong ──
sep("Bug 4: scorer and per_item_tags agree on correctness")
g2 = engine.build_test(Grade.SECOND)
g2_words = {w.word: w for w in g2}
responses2 = []
for w in g2:
    if w.word == "bombastic":
        responses2.append(SpellingResponse(item_id=w.word, word=w.word, user_input="bumbastic",
                                           word_type=w.word_type, response_time_seconds=5.0))
    else:
        responses2.append(SpellingResponse(item_id=w.word, word=w.word, user_input=w.word,
                                           word_type=w.word_type, response_time_seconds=5.0))
result2 = engine.evaluate("child2", Grade.SECOND, responses2)
bomb_scored = [s for s in result2.score.scored_items if s.label == "bombastic"][0]
bomb_tags = [p for p in result2.per_item_tags if "bombastic" in p.item_id]
if bomb_tags:
    check("bombastic scorer is_correct=False", not bomb_scored.is_correct)
    check("bombastic per_item_tags is_correct=False", not bomb_tags[0].is_correct)
else:
    check("bombastic per_item_tags exists", False, "no per_item_tags for bombastic")

# ── Bug 5: every wrong word gets at least 1 error tag ──
sep("Bug 5: every wrong word has 1+ error tag")
for p in result2.per_item_tags:
    if p.answered and not p.is_correct:
        has_error = any(t.endswith("_error") or t in ("unrelated_attempt", "unrelated_attempt_sightword",
                         "spelling_convention_error", "homophone_error") for t in p.tags)
        check(f"{p.item_id} has error tag", has_error, f"tags={p.tags}")

# ── Bug 6: silent-e words — no ending_consonant_error when correct ──
sep("Bug 6: silent-e words have no ending_consonant_error")
g3 = engine.build_test(Grade.THIRD)
g3_words = {w.word: w for w in g3}
responses3 = [SpellingResponse(item_id=w.word, word=w.word, user_input=w.word,
                               word_type=w.word_type, response_time_seconds=5.0) for w in g3]
result3 = engine.evaluate("child3", Grade.THIRD, responses3)
outline_tags = [p for p in result3.per_item_tags if "outline" in p.item_id][0]
check("outline (correct) has no ending_consonant_error",
      "ending_consonant_error" not in outline_tags.tags,
      f"tags={outline_tags.tags}")

# ── Bug 7: vowel-start words — no beginning_consonant_error when correct ──
sep("Bug 7: vowel-start words have no beginning_consonant_error")
amputate_tags = [p for p in result3.per_item_tags if "amputate" in p.item_id][0]
check("amputate (correct) has no beginning_consonant_error",
      "beginning_consonant_error" not in amputate_tags.tags,
      f"tags={amputate_tags.tags}")
entertain_tags = [p for p in result3.per_item_tags if "entertain" in p.item_id][0]
check("entertain (correct) has no beginning_consonant_error",
      "beginning_consonant_error" not in entertain_tags.tags,
      f"tags={entertain_tags.tags}")

# ── Bug 9,10: sounds_like checker ──
sep("Bugs 9,10: sounds_like phonetic checker")
check("phone/fone sounds alike", sounds_like("phone", "fone"))
check("graph/graff sounds alike", sounds_like("graph", "graff"))
check("standstill/standstil sounds alike", sounds_like("standstill", "standstil"))
check("candle/candel sounds alike", sounds_like("candle", "candel"))
check("friend/frend sounds alike", sounds_like("friend", "frend"))
check("puzzle/puzle sounds alike", sounds_like("puzzle", "puzle"))
check("bombastic/bumbastic NOT sounds alike", not sounds_like("bombastic", "bumbastic"))
check("cup/red NOT sounds alike", not sounds_like("cup", "red"))

# ── Bug 9: one change = one error ──
sep("Bug 9: one change = one error (sounds_like → 1 spelling_convention)")
responses_g2_errors = []
for w in g2:
    if w.word == "phone":
        responses_g2_errors.append(SpellingResponse(item_id=w.word, word=w.word, user_input="fone",
                                                      word_type=w.word_type, response_time_seconds=5.0))
    elif w.word == "graph":
        responses_g2_errors.append(SpellingResponse(item_id=w.word, word=w.word, user_input="graff",
                                                      word_type=w.word_type, response_time_seconds=5.0))
    else:
        responses_g2_errors.append(SpellingResponse(item_id=w.word, word=w.word, user_input=w.word,
                                                      word_type=w.word_type, response_time_seconds=5.0))
result_g2e = engine.evaluate("child_g2e", Grade.SECOND, responses_g2_errors)
fone_scored = [s for s in result_g2e.score.scored_items if s.label == "phone"][0]
fone_mistakes = fone_scored.detail.get("mistakes", {})
check("phone→fone has 1 mistake (spelling_convention)",
      len(fone_mistakes) == 1 and "spelling_convention" in fone_mistakes,
      f"mistakes={fone_mistakes}")
check("phone→fone gets full points", fone_scored.points == fone_scored.max_points,
      f"points={fone_scored.points}, max={fone_scored.max_points}")
graff_scored = [s for s in result_g2e.score.scored_items if s.label == "graph"][0]
graff_mistakes = graff_scored.detail.get("mistakes", {})
check("graph→graff has 1 mistake (spelling_convention)",
      len(graff_mistakes) == 1 and "spelling_convention" in graff_mistakes,
      f"mistakes={graff_mistakes}")

# ── Bug 11: time cap ──
sep("Bug 11: time cap at 120s")
the_scored = [s for s in result.score.scored_items if s.label == "the"]
if the_scored:
    check("time capped at 120", the_scored[0].detail.get("time", 0) <= 120)

# ── Bug 12,13,28: strengths/focus_areas no overlap ──
sep("Bugs 12,13,28: strengths/focus_areas no overlap")
strengths = engine.strengths(result.signals)
focus = engine.focus_areas(result.score)
check("no overlap (G1 all correct)", not set(strengths) & set(focus),
      f"strengths={strengths}, focus={focus}")

# ── Bug 14-21: Grade 1 word data fixes ──
sep("Bugs 14-21: Grade 1 word data")
she = g1_words.get("she")
if she:
    she_features = [e.feature for e in parse_expectations(she.features)]
    check("she has long_vowel", PhonicsFeature.LONG_VOWEL in she_features)
    check("she has no short_vowel", PhonicsFeature.SHORT_VOWEL not in she_features)

hi = g1_words.get("hi")
if hi:
    hi_features = [e.feature for e in parse_expectations(hi.features)]
    check("hi has long_vowel only", PhonicsFeature.LONG_VOWEL in hi_features and
          PhonicsFeature.SHORT_VOWEL not in hi_features)

stop = g1_words.get("stop")
if stop:
    stop_features = [e.feature for e in parse_expectations(stop.features)]
    check("stop has consonant_blend", PhonicsFeature.CONSONANT_BLEND in stop_features)
    check("stop has short_vowel o", PhonicsFeature.SHORT_VOWEL in stop_features)

home = g1_words.get("home")
if home:
    home_features = [e.feature for e in parse_expectations(home.features)]
    check("home has long_vowel", PhonicsFeature.LONG_VOWEL in home_features)

and_word = g1_words.get("and")
if and_word:
    check("'and' is regular", and_word.word_type == WordType.REGULAR)

# ── Bug 22: digraph_difficulty_emerging with sounds_like ──
sep("Bug 22: digraph_difficulty_emerging should not fire for ph errors (now spelling_convention)")
dear_parent = [t.tag for t in result_g2e.tags]
check("digraph_difficulty_emerging not fired (ph errors are convention)",
      "digraph_difficulty_emerging" not in dear_parent,
      f"tags={dear_parent}")

# ── Bug 24: 'from' is regular (phonics) in Grade 2 ──
sep("Bug 24: 'from' is regular in Grade 2")
from_word = g2_words.get("from")
if from_word:
    check("'from' is regular", from_word.word_type == WordType.REGULAR,
          f"type={from_word.word_type}")

# ── Bug 25: puzzle has no consonant_digraph (zz is double letter) ──
sep("Bug 25: puzzle has no consonant_digraph")
puzzle = g3_words.get("puzzle")
if puzzle:
    puzzle_features = [e.feature for e in parse_expectations(puzzle.features)]
    check("puzzle has no consonant_digraph", PhonicsFeature.CONSONANT_DIGRAPH not in puzzle_features,
          f"features={puzzle_features}")

# ── Bug 27: homophones ──
sep("Bug 27: homophone detection")
check("there/their is homophone", is_homophone("there", "their"))
check("which/witch is homophone", is_homophone("which", "witch"))
check("the/cat is NOT homophone", not is_homophone("the", "cat"))

# Test homophone in sight word scoring
g3_responses_homo = []
for w in g3:
    if w.word == "there":
        g3_responses_homo.append(SpellingResponse(item_id=w.word, word=w.word, user_input="their",
                                                    word_type=w.word_type, response_time_seconds=5.0))
    elif w.word == "which":
        g3_responses_homo.append(SpellingResponse(item_id=w.word, word=w.word, user_input="witch",
                                                    word_type=w.word_type, response_time_seconds=5.0))
    else:
        g3_responses_homo.append(SpellingResponse(item_id=w.word, word=w.word, user_input=w.word,
                                                    word_type=w.word_type, response_time_seconds=5.0))
result_homo = engine.evaluate("child_homo", Grade.THIRD, g3_responses_homo)
there_tags = [p for p in result_homo.per_item_tags if "there" in p.item_id][0]
check("there→their tagged homophone_error", "homophone_error" in there_tags.tags,
      f"tags={there_tags.tags}")

# ── Bug 29: rushed_spelling description ──
sep("Bug 29: rushed_spelling description (not 'careless')")
rushed_tag = [t for t in result_homo.tags if t.tag == "rushed_spelling"]
if rushed_tag:
    check("description doesn't say 'careless'", "careless" not in rushed_tag[0].description.lower(),
          f"desc={rushed_tag[0].description}")

# ── Bug 31: vowel_difficulty_emerging vs phonetic_strategy_strong ──
sep("Bug 31: vowel_difficulty and phonetic_strategy not both firing")
# If vowel_accuracy >= 0.7, vowel_difficulty should not fire
check("vowel_difficulty trigger has accuracy check",
      "vowel_accuracy < 0.7" in (engine.tag_config.get("vowel_difficulty_emerging").trigger if engine.tag_config.get("vowel_difficulty_emerging") else ""),
      "see spelling_tags.json")

# ── Bug 36-39: word list changes ──
sep("Bugs 36-39: Grade 1 word list changes")
check("chap replaced by chat", "chap" not in [w.word for w in g1] and "chat" in [w.word for w in g1])
check("bed replaced by leg", "bed" not in [w.word for w in g1] and "leg" in [w.word for w in g1])
check("cup replaced by mud", "cup" not in [w.word for w in g1] and "mud" in [w.word for w in g1])
check("quit replaced by stop", "quit" not in [w.word for w in g1] and "stop" in [w.word for w in g1])
check("go replaced by home", "go" not in [w.word for w in g1] and "home" in [w.word for w in g1])

# ── Bug 51: phonetic_strategy_strong should fire after sounds_like fix ──
sep("Bug 51: phonetic_strategy_strong fires in Grade 2 after sounds_like fix")
check("phonetic_strategy_strong fired in G2",
      "phonetic_strategy_strong" in dear_parent,
      f"tags={dear_parent}")

# ── Summary ──
sep("SUMMARY")
print(f"  {passed} passed, {failed} failed")
if failed == 0:
    print("  ALL CHECKS PASSED")
else:
    print(f"  {failed} CHECKS FAILED")
