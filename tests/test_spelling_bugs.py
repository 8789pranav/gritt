"""Regression tests for the Word Wizard spelling bug list.

One test per bug from the Dear Parent Project review, named for the bug number
so a future failure points straight back at the decision it encodes.
"""

from __future__ import annotations

import pytest

from app.domain.enums import Grade, WordType
from app.domain.models import SpellingResponse
from app.engines import registry
from app.engines.spelling.phonics import is_homophone, sounds_like


def _run(grade: Grade, attempts: dict, time: float = 10.0):
    """Score ``attempts`` ({word: spelling}) and return (result, tags-by-word)."""
    engine = registry.spelling_engine()
    by_word = {item.word: item for item in engine.get_items(grade)}
    items = [by_word[word] for word in attempts]
    responses = [
        SpellingResponse(
            item_id=by_word[word].item_id,
            word=word,
            user_input=attempt,
            word_type=by_word[word].word_type,
            response_time_seconds=time,
        )
        for word, attempt in attempts.items()
    ]
    result = engine.evaluate("child", grade, responses, items=items)
    label_by_id = {item.item_id: item.word for item in items}
    tags = {label_by_id[p.item_id]: set(p.tags) for p in result.per_item_tags}
    return result, tags


# ---------------------------------------------------------------------------
# #73 - a dropped letter is an error at the position it belonged to
# ---------------------------------------------------------------------------
class TestBug73DroppedLetters:
    def test_dropped_silent_e_is_a_long_vowel_error(self):
        """home -> hom shortens the vowel: an error, not correct and not nothing."""
        _, tags = _run(Grade.FIRST, {"home": "hom"})
        assert "long_vowel_error" in tags["home"]
        assert "long_vowel_correct" not in tags["home"]

    def test_dropped_short_vowel_is_an_error(self):
        """bombastic -> bombstic drops the 'a'; the surviving 'o' earns nothing."""
        _, tags = _run(Grade.SECOND, {"bombastic": "bombstic"})
        assert "short_vowel_error" in tags["bombastic"]
        assert "short_vowel_correct" not in tags["bombastic"]

    def test_changed_vowel_in_a_multi_vowel_word_is_an_error(self):
        """amputate -> ampytate loses the 'u'."""
        _, tags = _run(Grade.THIRD, {"amputate": "ampytate"})
        assert "short_vowel_error" in tags["amputate"]

    def test_vowel_accuracy_strong_no_longer_fires_falsely(self):
        result, _ = _run(Grade.FIRST, {"home": "hom", "she": "she", "hi": "hi"})
        assert result.signals["vowel_error_count"] >= 1
        assert "vowel_accuracy_strong" not in {t.tag for t in result.tags}

    def test_comma_list_is_a_conjunction_not_alternatives(self):
        """Every listed vowel must appear, in order."""
        from app.engines.spelling.phonics import FeatureExpectation, PhonicsFeature

        expectation = FeatureExpectation(
            feature=PhonicsFeature.SHORT_VOWEL, raw_value="o, a, i"
        )
        assert expectation.matches("bombastic")
        assert not expectation.matches("bombstic")
        assert not expectation.matches("bombistac")  # right letters, wrong order


# ---------------------------------------------------------------------------
# #74 - a vowel-length change is not a sound match
# ---------------------------------------------------------------------------
class TestBug74VowelLength:
    @pytest.mark.parametrize(
        "target,attempt",
        [("turnstile", "turnstil"), ("home", "hom"), ("entertain", "entertan")],
    )
    def test_shortened_vowel_is_not_a_convention_error(self, target, attempt):
        assert not sounds_like(target, attempt)

    @pytest.mark.parametrize(
        "target,attempt",
        [
            ("phone", "fone"),
            ("graph", "graff"),
            ("candle", "candel"),
            ("puzzle", "puzle"),
            ("standstill", "standstil"),
            ("said", "sed"),
            ("what", "wat"),
        ],
    )
    def test_genuine_convention_errors_still_match(self, target, attempt):
        assert sounds_like(target, attempt)

    def test_turnstile_routes_to_long_vowel_error(self):
        _, tags = _run(Grade.THIRD, {"turnstile": "turnstil"})
        assert "long_vowel_error" in tags["turnstile"]
        assert "spelling_convention_error" not in tags["turnstile"]

    def test_ending_consonant_survives_a_dropped_silent_e(self):
        """turnstil still ends on the 'l' sound, so only the vowel is wrong."""
        _, tags = _run(Grade.THIRD, {"turnstile": "turnstil"})
        assert "ending_consonant_correct" in tags["turnstile"]


# ---------------------------------------------------------------------------
# #75 - convention errors must produce a weakness signal
# ---------------------------------------------------------------------------
class TestBug75ConventionEmerging:
    ATTEMPTS = {
        "graph": "graff",
        "phone": "fone",
        "standstill": "standstil",
        "said": "sed",
        "what": "wat",
        "coast": "coast",
    }

    def test_convention_errors_are_counted(self):
        result, _ = _run(Grade.SECOND, self.ATTEMPTS)
        assert result.signals["convention_error_count"] >= 3

    def test_tag_fires_and_is_a_growth_edge(self):
        result, _ = _run(Grade.SECOND, self.ATTEMPTS)
        assert "spelling_convention_emerging" in {t.tag for t in result.tags}
        assert "spelling_convention_emerging" in {
            t.tag for t in result.growth_edges
        }

    def test_routed_into_focus_areas(self):
        engine = registry.spelling_engine()
        result, _ = _run(Grade.SECOND, self.ATTEMPTS)
        assert "Spelling conventions" in engine.focus_areas(result.score)

    def test_a_strengths_only_report_is_no_longer_possible(self):
        """The #75 scenario: every error is a convention error."""
        result, _ = _run(Grade.SECOND, self.ATTEMPTS)
        assert len(result.growth_edges) > 0

    def test_below_threshold_does_not_fire(self):
        result, _ = _run(Grade.SECOND, {"graph": "graff", "coast": "coast"})
        assert "spelling_convention_emerging" not in {t.tag for t in result.tags}


# ---------------------------------------------------------------------------
# #63 - added letters that change no sound
# ---------------------------------------------------------------------------
def test_bug63_added_letter_is_a_convention_error():
    assert sounds_like("clunk", "clunck")
    _, tags = _run(Grade.SECOND, {"clunk": "clunck"})
    assert "spelling_convention_error" in tags["clunk"]
    assert "ending_consonant_error" not in tags["clunk"]


# ---------------------------------------------------------------------------
# #61 - rushed never competes with a classification tag
# ---------------------------------------------------------------------------
class TestBug61Rushed:
    def test_classification_tags_suppress_rushed(self):
        _, tags = _run(
            Grade.SECOND,
            {"graph": "graff", "quaint": "letter", "clunk": "clank"},
            time=1.0,
        )
        assert "rushed_attempt" not in tags["graph"]
        assert "rushed_attempt" not in tags["quaint"]

    def test_rushed_is_relative_to_the_childs_median(self):
        engine = registry.spelling_engine()
        by_word = {item.word: item for item in engine.get_items(Grade.SECOND)}
        pace = {"from": 12.0, "coast": 13.0, "hunted": 11.0, "climax": 14.0}
        fast = {"clunk": "clank", "strand": "stand"}
        responses = [
            SpellingResponse(
                item_id=by_word[w].item_id,
                word=w,
                user_input=w,
                word_type=by_word[w].word_type,
                response_time_seconds=t,
            )
            for w, t in pace.items()
        ] + [
            SpellingResponse(
                item_id=by_word[w].item_id,
                word=w,
                user_input=a,
                word_type=by_word[w].word_type,
                response_time_seconds=1.0,
            )
            for w, a in fast.items()
        ]
        items = [by_word[w] for w in list(pace) + list(fast)]
        result = engine.evaluate("child", Grade.SECOND, responses, items=items)
        assert result.signals["fast_slips"] == 2
        assert "rushed_spelling" in {t.tag for t in result.tags}

    def test_convention_errors_do_not_inflate_fast_slips(self):
        result, _ = _run(Grade.SECOND, {"graph": "graff", "phone": "fone"}, time=1.0)
        assert result.signals["fast_slips"] == 0


# ---------------------------------------------------------------------------
# #57 and vowel-start words
# ---------------------------------------------------------------------------
class TestBug57AndBlend:
    def test_and_earns_its_blend_tag(self):
        _, tags = _run(Grade.FIRST, {"and": "and"})
        assert "consonant_blend_correct" in tags["and"]

    def test_and_is_a_vowel_start_word(self):
        _, tags = _run(Grade.FIRST, {"and": "and"})
        assert not any(t.startswith("beginning_consonant") for t in tags["and"])

    @pytest.mark.parametrize("word", ["outline", "amputate", "entertain"])
    def test_other_vowel_start_words_skip_the_beginning_tag(self, word):
        _, tags = _run(Grade.THIRD, {word: word})
        assert not any(t.startswith("beginning_consonant") for t in tags[word])


# ---------------------------------------------------------------------------
# #54, #70, Q3
# ---------------------------------------------------------------------------
def test_bug54_blank_word_is_unanswered_with_no_tags():
    engine = registry.spelling_engine()
    by_word = {item.word: item for item in engine.get_items(Grade.FIRST)}
    items = [by_word["yet"], by_word["chat"]]
    responses = [
        SpellingResponse(
            item_id=by_word["yet"].item_id,
            word="yet",
            user_input="yet",
            word_type=WordType.REGULAR,
            response_time_seconds=5.0,
        ),
        SpellingResponse(
            item_id=by_word["chat"].item_id,
            word="chat",
            user_input="",
            word_type=WordType.REGULAR,
            response_time_seconds=0.0,
        ),
    ]
    result = engine.evaluate("child", Grade.FIRST, responses, items=items)
    blank = next(
        p for p in result.per_item_tags if p.item_id == by_word["chat"].item_id
    )
    assert blank.answered is False
    assert not blank.tags


def test_bug70_sight_words_reach_focus_areas():
    engine = registry.spelling_engine()
    result, _ = _run(Grade.SECOND, {"does": "dose", "said": "sed", "coast": "coast"})
    assert "Sight words" in engine.focus_areas(result.score)


def test_q3_sound_alikes_stay_in_the_sight_word_pool():
    """The denominator is every sight word shown; a sound-alike is not removed."""
    result, _ = _run(
        Grade.SECOND,
        {"does": "does", "said": "sed", "they": "thay", "what": "wat"},
    )
    assert result.signals["sight_words_count"] == 4
    assert result.signals["sight_word_accuracy"] == pytest.approx(0.25)


def test_homophones_are_word_choice_not_phonics():
    assert is_homophone("which", "witch")
    assert not sounds_like("does", "dose")
    _, tags = _run(Grade.THIRD, {"which": "witch"})
    assert tags["which"] == {"homophone_error"}


# ---------------------------------------------------------------------------
# Resolved decision - phonics_score means phonics
# ---------------------------------------------------------------------------
def _phonics_ok(result_dict: dict) -> bool:
    mistakes = result_dict["detail"].get("mistakes", {})
    return (
        result_dict["is_correct"]
        or "spelling_convention" in mistakes
        or "homophone_error" in mistakes
    )


def test_convention_errors_do_not_lower_phonics_score():
    """graff, fone, standstil are phonetically perfect: phonics stays 100."""
    result, _ = _run(
        Grade.SECOND,
        {"graph": "graff", "phone": "fone", "standstill": "standstil"},
    )
    results = [s.model_dump() for s in result.score.scored_items]
    phonics = [r for r in results if r["detail"]["type"] == WordType.REGULAR.value]
    assert phonics
    assert all(_phonics_ok(r) for r in phonics)


def test_genuine_phonics_errors_still_count():
    result, _ = _run(Grade.THIRD, {"hamburger": "hambuger"})
    item = result.score.scored_items[0]
    assert "spelling_convention" not in item.detail.get("mistakes", {})
    assert not item.is_correct
    assert not _phonics_ok(item.model_dump())
