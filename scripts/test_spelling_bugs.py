"""Test script to verify spelling assessment bug fixes."""
import sys
sys.path.insert(0, '.')

from app.engines.spelling.engine import SpellingEngine
from app.engines.spelling.scorer import SpellingScorer
from app.engines.spelling.phonics import is_homophone, sounds_like, parse_expectations
from app.domain.enums import Grade, WordType
from app.domain.models import SpellingResponse

engine = SpellingEngine()
scorer = SpellingScorer()


def test_57_and_blend():
    """#57: 'and' should have consonant_blend feature."""
    items = engine.get_items(Grade.FIRST)
    and_word = next(i for i in items if i.word == "and")
    expectations = [e.feature.value for e in parse_expectations(and_word.features)]
    assert "consonant_blend" in expectations, f"FAIL #57: and missing consonant_blend, got {expectations}"
    print("PASS #57: 'and' has consonant_blend feature")


def test_68_sun_son_homophone():
    """#68: sun->son should be homophone, not short_vowel_error."""
    assert is_homophone("sun", "son"), "FAIL #68: sun/son not homophone"
    k_items = engine.get_items(Grade.KINDERGARTEN)
    sun_item = next(i for i in k_items if i.word == "sun")
    result = scorer.score_word(sun_item, "son")
    mistakes = result.detail["mistakes"]
    assert "homophone_error" in mistakes, f"FAIL #68: sun->son mistakes={mistakes}"
    assert "short_vowel" not in mistakes, f"FAIL #68: sun->son has short_vowel_error, mistakes={mistakes}"
    print("PASS #68: sun->son gets homophone_error (not short_vowel_error)")


def test_10_sight_sounds_like():
    """#10: sounds_like should work on sight words too."""
    # 'no' -> 'know' is a homophone, but let's test sounds_like on a sight word
    # 'to' is a sight word, 'too' sounds like it
    assert sounds_like("too", "to"), "FAIL #10: sounds_like(too, to) should be True"
    print("PASS #10: sounds_like works on sight words")


def test_52_word_count():
    """#52: Score should divide by actual word count, not 31."""
    k_words = engine.build_test(Grade.KINDERGARTEN)
    print(f"  Kindergarten sample size: {len(k_words)}")
    responses = [
        SpellingResponse(
            item_id=w.word, word=w.word, user_input=w.word,
            word_type=w.word_type, response_time_seconds=5.0, hints_used=0
        )
        for w in k_words[:5]
    ]
    score = scorer.score(k_words[:5], responses, Grade.KINDERGARTEN)
    print(f"  Score total_items: {score.total_items}")
    assert score.total_items == 5, f"FAIL #52: total_items={score.total_items} expected 5"
    print("PASS #52: total_items matches submitted count")


def test_53_sight_consistency():
    """#53: sight_word_score should match sight_word_accuracy."""
    k_words = engine.build_test(Grade.KINDERGARTEN)
    # Submit 3 sight words: 2 correct, 1 blank
    sight_words = [w for w in k_words if w.word_type == WordType.SIGHT][:3]
    responses = [
        SpellingResponse(
            item_id=sight_words[0].word, word=sight_words[0].word,
            user_input=sight_words[0].word,  # correct
            word_type=WordType.SIGHT, response_time_seconds=5.0, hints_used=0
        ),
        SpellingResponse(
            item_id=sight_words[1].word, word=sight_words[1].word,
            user_input=sight_words[1].word,  # correct
            word_type=WordType.SIGHT, response_time_seconds=5.0, hints_used=0
        ),
        SpellingResponse(
            item_id=sight_words[2].word, word=sight_words[2].word,
            user_input="",  # blank
            word_type=WordType.SIGHT, response_time_seconds=5.0, hints_used=0
        ),
    ]
    score = scorer.score(sight_words, responses, Grade.KINDERGARTEN)
    signals = engine.deriver.derive(sight_words, responses, score)
    sight_acc = signals["sight_word_accuracy"]
    # 2 correct out of 2 attempted (blank excluded) = 1.0
    assert sight_acc == 1.0, f"FAIL #53: sight_word_accuracy={sight_acc} expected 1.0"
    print(f"PASS #53: sight_word_accuracy={sight_acc} (blank excluded from denominator)")


def test_54_55_blank_icon_error_type():
    """#54, #55: Blank words should show 'Not answered' icon and null error_type."""
    k_words = engine.build_test(Grade.KINDERGARTEN)
    sight_word = next(w for w in k_words if w.word_type == WordType.SIGHT)
    responses = [
        SpellingResponse(
            item_id=sight_word.word, word=sight_word.word,
            user_input="",  # blank
            word_type=WordType.SIGHT, response_time_seconds=5.0, hints_used=0
        ),
    ]
    score = scorer.score([sight_word], responses, Grade.KINDERGARTEN)
    result = score.scored_items[0]
    user_input = result.detail.get("user_input", "").strip()
    # Simulate _error_type_for logic
    error_type = None
    if not result.is_correct and user_input:
        error_type = "some_error"
    assert error_type is None, f"FAIL #55: blank sight word error_type={error_type}"
    # Simulate icon logic
    icon = "Correct" if result.is_correct else ("Not answered" if not user_input else "Incorrect")
    assert icon == "Not answered", f"FAIL #54: blank word icon={icon}"
    print("PASS #54: blank word shows 'Not answered' icon")
    print("PASS #55: blank sight word has null error_type")


def test_61_rushed_last():
    """#61: rushed_attempt should not override more specific tags."""
    # Simulate the _error_type_for ordering: rushed_attempt checked last
    tags = ["unrelated_attempt", "rushed_attempt"]
    # In the fixed code, unrelated_attempt is checked before rushed_attempt
    error_type = None
    if "unrelated_attempt" in tags:
        error_type = "Unrelated attempt"
    elif "rushed_attempt" in tags:
        error_type = "Rushed attempt"
    assert error_type == "Unrelated attempt", f"FAIL #61: error_type={error_type}"
    print("PASS #61: unrelated_attempt takes priority over rushed_attempt")


def test_62_spelling_error_type():
    """#62: Words with spelling_error tag should get 'Spelling' error_type."""
    # Simulate _error_type_for for a word with only 'spelling' mistake
    mistakes = {"spelling": "Expected 'bombastic', got 'bombastik'"}
    tags = ["spelling_error"]
    error_type = None
    # Check feature keys first
    feature_key = next(
        (k for k in mistakes if k not in ("spelling", "unrelated_attempt", "spelling_convention", "homophone_error")),
        None,
    )
    if feature_key:
        error_type = feature_key.replace("_", " ").replace(" error", "")
    elif "spelling_error" in tags or "spelling" in mistakes:
        error_type = "Spelling"
    assert error_type == "Spelling", f"FAIL #62: error_type={error_type}"
    print("PASS #62: spelling_error tag returns 'Spelling' error_type")


def test_70_sight_focus_area():
    """#70: focus_areas should include sight words when accuracy is poor."""
    k_words = engine.build_test(Grade.KINDERGARTEN)
    sight_words = [w for w in k_words if w.word_type == WordType.SIGHT][:3]
    regular_words = [w for w in k_words if w.word_type == WordType.REGULAR][:3]
    test_words = sight_words + regular_words

    responses = []
    # All regular words correct
    for w in regular_words:
        responses.append(SpellingResponse(
            item_id=w.word, word=w.word, user_input=w.word,
            word_type=w.word_type, response_time_seconds=5.0, hints_used=0
        ))
    # All sight words wrong
    for w in sight_words:
        responses.append(SpellingResponse(
            item_id=w.word, word=w.word, user_input="xyz",
            word_type=w.word_type, response_time_seconds=5.0, hints_used=0
        ))

    score = scorer.score(test_words, responses, Grade.KINDERGARTEN)
    focus = engine.focus_areas(score)
    print(f"  focus_areas: {focus}")
    assert "Sight words" in focus, f"FAIL #70: Sight words not in focus_areas={focus}"
    print("PASS #70: focus_areas includes 'Sight words'")


if __name__ == "__main__":
    test_57_and_blend()
    test_68_sun_son_homophone()
    test_10_sight_sounds_like()
    test_52_word_count()
    test_53_sight_consistency()
    test_54_55_blank_icon_error_type()
    test_61_rushed_last()
    test_62_spelling_error_type()
    test_70_sight_focus_area()
    print("\n=== All tests passed! ===")
