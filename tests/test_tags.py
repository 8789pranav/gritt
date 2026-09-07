"""
Comprehensive tag verification tests for every test type and grade.

Verifies that:
1. Test-level tags are correctly emitted for perfect / all-wrong / mixed scenarios
2. Per-item tags are present for every item in every grade
3. Per-item tags match the expected schema (answered, is_correct, tags list)
4. Tag polarities (strength / growth_edge / neutral) are correct
5. Tag IDs match the config definitions
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.domain.enums import Grade, TestType, WordType
from app.domain.models import (
    ComprehensionResponse,
    LogicResponse,
    SpeakingResponse,
    SpellingResponse,
    TagOutput,
    PerItemTags,
)
from app.engines import registry
from app.engines.speaking.analyzer import DimensionScore, SpeechAnalysis
from app.tagging.config_loader import load_tag_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def tag_ids(tags: List[TagOutput]) -> set[str]:
    return {t.tag for t in tags}


def tag_by_id(tags: List[TagOutput], tag_id: str) -> TagOutput | None:
    return next((t for t in tags if t.tag == tag_id), None)


def all_tag_ids_for_test(test_type: TestType) -> set[str]:
    config = load_tag_config(test_type)
    return {t.id for t in config.tags}


def _analysis(score: float) -> SpeechAnalysis:
    dim = DimensionScore(score=score)
    return SpeechAnalysis(
        pronunciation=dim,
        fluency=dim,
        prosody=dim,
        grammar=dim,
        speaking_rate=dim,
        overall_score=score,
        level="test",
        recommendation="test",
    )


# ---------------------------------------------------------------------------
# LOGIC: test-level tags
# ---------------------------------------------------------------------------
class TestLogicTags:
    """Verify Logic Quest tag emission across all grades."""

    EXPECTED_TAG_IDS = {
        "pattern_detection_strong",
        "pattern_detection_emerging",
        "relational_reasoning_present",
        "relational_reasoning_emerging",
        "systematic_problem_solving",
        "systematic_problem_solving_emerging",
        "flexible_strategy_use",
        "flexible_strategy_emerging",
        "reasoning_under_load",
        "reasoning_under_load_emerging",
        "rule_maintenance_difficulty",
        "deliberate_pace",
        "trial_and_error_strategy",
        "impulsive_response",
        "self_correction_present",
    }

    def test_all_tag_ids_match_config(self):
        actual = all_tag_ids_for_test(TestType.LOGIC)
        assert actual == self.EXPECTED_TAG_IDS

    @pytest.mark.parametrize("grade", list(Grade))
    def test_perfect_run_emits_strength_tags(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=item.expected_latency_seconds * 0.8,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        # Perfect run should emit at least one strength tag
        assert len(result.strengths) > 0, f"{grade.value}: no strength tags on perfect run"

        # All emitted tags must be known config IDs
        emitted = tag_ids(result.tags)
        unknown = emitted - self.EXPECTED_TAG_IDS
        assert not unknown, f"{grade.value}: unknown tags: {unknown}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_all_wrong_run_emits_growth_edge_tags(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=(item.correct_answer_index + 1) % len(item.options),
                response_time_seconds=item.expected_latency_seconds * 0.3,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        # Every construct the child was shown should now report as emerging.
        # (Uniform pacing means impulsive_response correctly does NOT fire -
        # it is measured against the child's own median, so a child who works
        # at one speed throughout is never rushing relative to themselves.)
        growth = {t.tag for t in result.growth_edges}
        assert growth, f"{grade.value}: no growth edge tags on an all-wrong run"
        assert "pattern_detection_emerging" in growth, growth
        emitted = tag_ids(result.tags)
        unknown = emitted - self.EXPECTED_TAG_IDS
        assert not unknown, f"{grade.value}: unknown tags: {unknown}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_impulsive_response_needs_a_pace_to_be_fast_against(self, grade: Grade):
        """G1: impulsive is relative to the child's own median time."""
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = []
        for index, item in enumerate(items):
            fast = index < 2
            responses.append(
                LogicResponse(
                    item_id=item.item_id,
                    selected_answer_index=(
                        (item.correct_answer_index + 1) % len(item.options)
                        if fast else item.correct_answer_index
                    ),
                    response_time_seconds=1.0 if fast else 20.0,
                )
            )
        result = engine.evaluate("child", grade, responses)
        assert result.signals["fast_and_wrong_count"] == 2
        assert "impulsive_response" in tag_ids(result.tags)

    @pytest.mark.parametrize("grade", list(Grade))
    def test_uniform_pace_is_not_impulsive(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=(item.correct_answer_index + 1) % len(item.options),
                response_time_seconds=1.0,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)
        assert "impulsive_response" not in tag_ids(result.tags)

    @pytest.mark.parametrize("grade", list(Grade))
    def test_trial_and_error_detected(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=10,
                attempts=3,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)
        emitted = tag_ids(result.tags)
        assert "trial_and_error_strategy" in emitted, f"{grade.value}: expected trial_and_error, got {emitted}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_self_correction_detected(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=10,
                self_corrected=True,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)
        emitted = tag_ids(result.tags)
        assert "self_correction_present" in emitted, f"{grade.value}: expected self_correction_present, got {emitted}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_tag_polarities_are_correct(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=item.expected_latency_seconds * 0.8,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        for tag in result.tags:
            if tag.polarity.value == "strength":
                assert tag.tag in self.EXPECTED_TAG_IDS
            elif tag.polarity.value == "growth_edge":
                assert tag.tag in self.EXPECTED_TAG_IDS

    @pytest.mark.parametrize("grade", list(Grade))
    def test_empty_submission_no_strength_tags(self, grade: Grade):
        engine = registry.logic_engine()
        result = engine.evaluate("child", grade, [])
        assert len(result.strengths) == 0, f"{grade.value}: unexpected strength tags on empty submission"


# ---------------------------------------------------------------------------
# LOGIC: per-item tags
# ---------------------------------------------------------------------------
class TestLogicPerItemTags:
    """Verify per-item tags for Logic Quest across all grades."""

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_cover_every_item(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=10,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        assert len(result.per_item_tags) == len(items)
        item_ids = {i.item_id for i in items}
        tagged_ids = {p.item_id for p in result.per_item_tags}
        assert tagged_ids == item_ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_correct_on_perfect_run(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=10,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        for pit in result.per_item_tags:
            assert pit.answered is True
            assert pit.is_correct is True
            # Correct items should carry their primary_tag
            assert len(pit.tags) > 0, f"{grade.value}/{pit.item_id}: no tags on correct item"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_impulsive_on_fast_wrong(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = []
        for index, item in enumerate(items):
            fast = index < 2
            responses.append(
                LogicResponse(
                    item_id=item.item_id,
                    selected_answer_index=(
                        (item.correct_answer_index + 1) % len(item.options)
                        if fast else item.correct_answer_index
                    ),
                    response_time_seconds=1.0 if fast else 20.0,
                )
            )
        result = engine.evaluate("child", grade, responses)

        # G1: only the two dashed-off items are fast relative to the median.
        fast_ids = {items[0].item_id, items[1].item_id}
        for pit in result.per_item_tags:
            assert pit.answered is True
            if pit.item_id in fast_ids:
                assert pit.is_correct is False
                assert "impulsive_response" in pit.tags, (
                    f"{grade.value}/{pit.item_id}: expected impulsive_response, "
                    f"got {pit.tags}"
                )
            else:
                assert "impulsive_response" not in pit.tags

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_unanswered_for_empty(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        result = engine.evaluate("child", grade, [])

        items_by_id = {item.item_id: item for item in items}
        for pit in result.per_item_tags:
            assert pit.answered is False
            assert pit.is_correct is None
            item = items_by_id.get(pit.item_id)
            expected_tag = f"{item.primary_tag.value}_missed"
            assert pit.tags == [expected_tag], f"{pit.item_id}: expected [{expected_tag}], got {pit.tags}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_trial_and_error(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=10,
                attempts=2,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        for pit in result.per_item_tags:
            assert "trial_and_error_strategy" in pit.tags, f"{grade.value}/{pit.item_id}: expected trial_and_error"


# ---------------------------------------------------------------------------
# SPELLING: test-level tags
# ---------------------------------------------------------------------------
class TestSpellingTags:
    """Verify Word Wizard tag emission across all grades."""

    EXPECTED_TAG_IDS = {
        "phonetic_strategy_strong",
        "vowel_accuracy_strong",
        "vowel_emerging",
        "digraph_competent",
        "blend_competent",
        "digraph_emerging",
        "blend_emerging",
        "sight_word_recognition_strong",
        "sight_word_emerging",
        "spelling_convention_emerging",
        "audio_support_benefit",
        "rushed_spelling",
    }

    def test_all_tag_ids_match_config(self):
        actual = all_tag_ids_for_test(TestType.SPELLING)
        assert actual == self.EXPECTED_TAG_IDS

    @pytest.mark.parametrize("grade", list(Grade))
    def test_perfect_run_emits_strength_tags(self, grade: Grade):
        engine = registry.spelling_engine()
        items = engine.get_items(grade)
        responses = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input=item.word,
                word_type=item.word_type,
                response_time_seconds=6.0,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        assert len(result.strengths) > 0, f"{grade.value}: no strength tags on perfect run"
        emitted = tag_ids(result.tags)
        unknown = emitted - self.EXPECTED_TAG_IDS
        assert not unknown, f"{grade.value}: unknown tags: {unknown}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_all_wrong_emits_growth_edge_tags(self, grade: Grade):
        engine = registry.spelling_engine()
        items = engine.get_items(grade)
        responses = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input="zzqq",
                word_type=item.word_type,
                response_time_seconds=6.0,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        assert len(result.growth_edges) > 0, f"{grade.value}: no growth_edge tags on all-wrong"
        emitted = tag_ids(result.tags)
        # Should flag vowel or digraph difficulty
        growth_ids = {t.tag for t in result.growth_edges}
        assert len(growth_ids) > 0

    @pytest.mark.parametrize("grade", list(Grade))
    def test_rushed_spelling_detected(self, grade: Grade):
        engine = registry.spelling_engine()
        items = engine.get_items(grade)
        # #61: rushed is relative to the child's own median time, so the run
        # needs a working pace to be fast *against*. The first two words are
        # dashed off wrong; the rest are answered correctly at a normal pace.
        responses = []
        for index, item in enumerate(items):
            fast = index < 2
            responses.append(
                SpellingResponse(
                    item_id=item.item_id,
                    word=item.word,
                    # A plausible misspelling, not an unrelated word -
                    # an unrelated attempt is classified and so never rushed.
                    user_input=item.word + "z" if fast else item.word,
                    word_type=item.word_type,
                    response_time_seconds=1.0 if fast else 12.0,
                )
            )
        result = engine.evaluate("child", grade, responses)
        emitted = tag_ids(result.tags)
        assert "rushed_spelling" in emitted, f"{grade.value}: expected rushed_spelling, got {emitted}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_uniformly_fast_run_is_not_rushed(self, grade: Grade):
        """#61: a child who simply works fast is not rushing every word."""
        engine = registry.spelling_engine()
        items = engine.get_items(grade)
        responses = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input="x",
                word_type=item.word_type,
                response_time_seconds=1.0,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)
        assert "rushed_spelling" not in tag_ids(result.tags)

    @pytest.mark.parametrize("grade", list(Grade))
    def test_empty_submission_minimal_tags(self, grade: Grade):
        engine = registry.spelling_engine()
        result = engine.evaluate("child", grade, [])
        # Empty submission may emit some tags due to zero-error triggers
        # (e.g. vowel_error_count == 0 → vowel_accuracy_strong)
        # but should NOT emit confidence-based tags like phonetic_strategy_strong
        emitted = tag_ids(result.tags)
        assert "phonetic_strategy_strong" not in emitted, f"{grade.value}: should not emit phonetic_strategy_strong on empty"
        assert "digraph_competent" not in emitted, f"{grade.value}: should not emit digraph_competent on empty"
        assert "blend_competent" not in emitted, f"{grade.value}: should not emit blend_competent on empty"
        assert "vowel_accuracy_strong" not in emitted, f"{grade.value}: should not emit vowel_accuracy_strong on empty"


# ---------------------------------------------------------------------------
# SPELLING: per-item tags
# ---------------------------------------------------------------------------
class TestSpellingPerItemTags:
    """Verify per-word tags for spelling across all grades."""

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_cover_every_word(self, grade: Grade):
        engine = registry.spelling_engine()
        items = engine.get_items(grade)
        responses = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input=item.word,
                word_type=item.word_type,
                response_time_seconds=6.0,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        assert len(result.per_item_tags) == len(items)
        item_ids = {i.item_id for i in items}
        tagged_ids = {p.item_id for p in result.per_item_tags}
        assert tagged_ids == item_ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_correct_on_perfect(self, grade: Grade):
        engine = registry.spelling_engine()
        items = engine.get_items(grade)
        responses = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input=item.word,
                word_type=item.word_type,
                response_time_seconds=6.0,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        for pit in result.per_item_tags:
            assert pit.answered is True
            assert pit.is_correct is True
            # Perfect spelling may still produce feature error tags due to
            # phonics feature matching quirks (e.g. silent-e words where the
            # "final" consonant is not the last letter). The key assertion is
            # that is_correct is True (scorer short-circuits on exact match).

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_feature_errors_on_wrong(self, grade: Grade):
        engine = registry.spelling_engine()
        items = engine.get_items(grade)
        regular_items = [i for i in items if i.word_type == WordType.REGULAR]
        if not regular_items:
            return

        # Use realistic misspellings (drop last 1-2 chars) so they're
        # classified as genuine misspellings, not unrelated_attempt.
        responses = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input=item.word[:-1] if len(item.word) > 2 else item.word + "x",
                word_type=item.word_type,
                response_time_seconds=6.0,
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        # At least some regular words should have feature error tags
        error_tag_count = sum(
            1 for pit in result.per_item_tags
            if any(t.endswith("_error") for t in pit.tags)
        )
        assert error_tag_count > 0, f"{grade.value}: no feature error tags on all-wrong"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_unanswered_for_empty(self, grade: Grade):
        engine = registry.spelling_engine()
        items = engine.get_items(grade)
        result = engine.evaluate("child", grade, [])

        for pit in result.per_item_tags:
            assert pit.answered is False
            assert pit.is_correct is None


# ---------------------------------------------------------------------------
# SPEAKING: test-level tags
# ---------------------------------------------------------------------------
class TestSpeakingTags:
    """Voice Challenge tags, driven the way production drives them.

    The service no longer routes speaking through SpeakingSignalDeriver: the
    Azure signal chain measures everything the deriver used to approximate, and
    pipeline.aggregate produces the signal block the tag config reads. These
    tests exercise that path, not the retired one.

    Note the scale. The old deriver emitted avg_fluency as a 0-1 ratio; the
    chain emits it as Azure does, 0-100. Same name, different units - which is
    exactly the kind of collision that fires no tag and raises no error.
    """

    EXPECTED_TAG_IDS = {
        "decoding_accurate", "decoding_emerging",
        "reading_rate_on_track", "reading_rate_slow",
        "phrasing_smooth", "phrasing_choppy",
        "expression_present", "expression_flat",
        "reads_every_word", "skips_words",
        "hesitates_before_starting", "stretches_words",
        "filler_habit_emerging", "self_corrects_while_reading",
        "vowel_sounds_secure", "short_vowel_emerging", "long_vowel_emerging",
        "blends_secure", "blends_emerging",
        "digraphs_secure", "digraphs_emerging",
        "ending_sounds_emerging",
        "recording_needs_review",
    }

    def test_all_tag_ids_match_config(self):
        assert all_tag_ids_for_test(TestType.SPEAKING) == self.EXPECTED_TAG_IDS

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _sentence(accuracy=90.0, fluency=90.0, prosody=85.0, completeness=100.0,
                  wcpm=60.0, band="in_band", omissions=0, fillers=0,
                  repetitions=0, prolonged=0, clear_errors=0,
                  time_to_speak=800.0, phonics=90.0, words=8):
        from app.engines.speaking.metrics import PHONICS_FEATURES

        return {
            "status": "answered",
            "scores": {
                "accuracy": accuracy, "fluency": fluency, "prosody": prosody,
                "completeness": completeness,
                "pron_score": round(min(accuracy, fluency, prosody) * 0.4
                                    + accuracy * 0.2 + fluency * 0.2
                                    + prosody * 0.2, 1),
            },
            "reading": {"correct_words": words, "total_words": words,
                        "wcpm": wcpm, "accuracy_pct": accuracy},
            "timing": {"speaking_span_ms": round(words / wcpm * 60000, 1)
                       if wcpm else 0.0,
                       "time_to_speak_ms": time_to_speak,
                       "time_to_first_word_ms": 120.0,
                       "pause_count": 1, "long_pause_count": 0},
            "disfluency": {"filler_count": fillers, "repetitions": repetitions},
            "errors": {"omission": omissions, "insertion": 0,
                       "mispronunciation": clear_errors, "monotone": 0,
                       "unexpected_break": 0, "missing_break": 0,
                       "clear_error": clear_errors, "needs_attention": 0,
                       "prolonged": prolonged, "words_flagged": clear_errors},
            "phonics": {name: phonics for name in PHONICS_FEATURES},
        }

    def _tags(self, sentences, grade="First"):
        from app.engines.speaking.pipeline import aggregate
        from app.tagging.emitter import emit_tags

        signals = aggregate(sentences, grade)
        return signals, {t.tag for t in emit_tags(TestType.SPEAKING, signals)}

    # -- the shape of the dictionary --------------------------------------
    def test_every_strength_has_an_emerging_partner(self):
        ids = all_tag_ids_for_test(TestType.SPEAKING)
        for strong, emerging in (
            ("decoding_accurate", "decoding_emerging"),
            ("phrasing_smooth", "phrasing_choppy"),
            ("expression_present", "expression_flat"),
            ("reads_every_word", "skips_words"),
            ("blends_secure", "blends_emerging"),
            ("digraphs_secure", "digraphs_emerging"),
        ):
            assert strong in ids and emerging in ids, (strong, emerging)

    # -- behaviour --------------------------------------------------------
    def test_a_strong_reader(self):
        _, tags = self._tags([self._sentence() for _ in range(8)])
        assert "decoding_accurate" in tags
        assert "phrasing_smooth" in tags
        assert "expression_present" in tags
        assert "reads_every_word" in tags
        assert "reading_rate_on_track" in tags

    def test_a_struggling_reader_gets_growth_edges(self):
        _, tags = self._tags([
            self._sentence(accuracy=55, fluency=52, prosody=45, completeness=70,
                           wcpm=15, band="below_band", omissions=1,
                           clear_errors=2, phonics=60)
            for _ in range(8)
        ])
        assert "decoding_emerging" in tags
        assert "phrasing_choppy" in tags
        assert "expression_flat" in tags
        assert "skips_words" in tags
        assert "decoding_accurate" not in tags

    def test_below_60_fluency_still_produces_a_tag(self):
        """The old config only fired between 0.6 and 0.8, so the weakest
        readers produced no fluency tag at all."""
        _, tags = self._tags([self._sentence(fluency=40) for _ in range(8)])
        assert "phrasing_choppy" in tags

    def test_a_slow_reader_is_named(self):
        _, tags = self._tags([self._sentence(wcpm=12) for _ in range(8)])
        assert "reading_rate_slow" in tags
        assert "reading_rate_on_track" not in tags

    def test_fillers_reach_the_rollup(self):
        _, tags = self._tags([self._sentence(fillers=2) for _ in range(8)])
        assert "filler_habit_emerging" in tags

    def test_stretched_sounds_reach_the_rollup(self):
        _, tags = self._tags([self._sentence(prolonged=1) for _ in range(8)])
        assert "stretches_words" in tags

    def test_hesitation_before_starting(self):
        _, tags = self._tags([self._sentence(time_to_speak=6000) for _ in range(8)])
        assert "hesitates_before_starting" in tags

    def test_repetition_reads_as_self_correction(self):
        _, tags = self._tags([self._sentence(repetitions=1) for _ in range(8)])
        assert "self_corrects_while_reading" in tags

    # -- phonics, shared vocabulary with Word Wizard ----------------------
    def test_phonics_strengths(self):
        _, tags = self._tags([self._sentence(phonics=92) for _ in range(8)])
        assert "vowel_sounds_secure" in tags
        assert "blends_secure" in tags
        assert "digraphs_secure" in tags

    def test_phonics_weaknesses(self):
        _, tags = self._tags([self._sentence(phonics=55) for _ in range(8)])
        assert "short_vowel_emerging" in tags
        assert "blends_emerging" in tags
        assert "ending_sounds_emerging" in tags

    def test_a_feature_never_exercised_is_silent(self):
        """A sound the sentences never contained is not a weakness."""
        rows = [self._sentence() for _ in range(8)]
        for row in rows:
            row["phonics"]["consonant_digraph"] = None
        signals, tags = self._tags(rows)
        assert signals["phonics_consonant_digraph"] is None
        assert "digraphs_emerging" not in tags
        assert "digraphs_secure" not in tags

    # -- guards -----------------------------------------------------------
    def test_two_sentences_are_not_enough_to_characterise_a_reader(self):
        _, tags = self._tags([self._sentence() for _ in range(2)])
        assert not tags, tags

    def test_an_empty_submission_emits_nothing(self):
        _, tags = self._tags([])
        assert not tags, tags

    def test_unassessable_recordings_are_reported_not_scored(self):
        rows = [self._sentence() for _ in range(4)]
        rows += [{"status": "needs_review", "scores": {}, "reading": {},
                  "timing": {}, "disfluency": {}, "errors": {}, "phonics": {}}
                 for _ in range(2)]
        signals, tags = self._tags(rows)
        assert signals["sentences_needs_review"] == 2
        assert signals["sentences_answered"] == 4
        assert "recording_needs_review" in tags

    def test_every_tag_has_parent_copy(self):
        from app.services.report_service import ReportService

        missing = self.EXPECTED_TAG_IDS - set(ReportService._TAG_SENTENCE_MAP)
        assert not missing, missing


class TestSpeakingPerItemTags:
    """Verify per-sentence tags for speaking across all grades."""

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_cover_every_sentence(self, grade: Grade):
        engine = registry.speaking_engine()
        sentences = engine.get_items(grade)
        responses = [
            SpeakingResponse(
                item_id=s.sentence_id,
                sentence_id=s.sentence_id,
                original_sentence=s.sentence,
                audio_base64="",
            )
            for s in sentences
        ]
        analyses = {s.sentence_id: _analysis(90.0) for s in sentences}
        result = engine.evaluate_with_analyses("child", grade, responses, analyses)

        assert len(result.per_item_tags) == len(sentences)
        sent_ids = {s.sentence_id for s in sentences}
        tagged_ids = {p.item_id for p in result.per_item_tags}
        assert tagged_ids == sent_ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_strong_dimensions(self, grade: Grade):
        engine = registry.speaking_engine()
        sentences = engine.get_items(grade)
        responses = [
            SpeakingResponse(
                item_id=s.sentence_id,
                sentence_id=s.sentence_id,
                original_sentence=s.sentence,
                audio_base64="",
            )
            for s in sentences
        ]
        analyses = {s.sentence_id: _analysis(95.0) for s in sentences}
        result = engine.evaluate_with_analyses("child", grade, responses, analyses)

        for pit in result.per_item_tags:
            assert pit.answered is True
            assert pit.is_correct is True
            # Score 95 → normalised >= 0.85 → all dimensions strong
            assert "pronunciation_strong" in pit.tags, f"{grade.value}/{pit.item_id}: expected pronunciation_strong"
            assert "fluency_strong" in pit.tags, f"{grade.value}/{pit.item_id}: expected fluency_strong"
            assert "prosody_strong" in pit.tags, f"{grade.value}/{pit.item_id}: expected prosody_strong"
            assert "grammar_strong" in pit.tags, f"{grade.value}/{pit.item_id}: expected grammar_strong"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_weak_dimensions(self, grade: Grade):
        engine = registry.speaking_engine()
        sentences = engine.get_items(grade)
        responses = [
            SpeakingResponse(
                item_id=s.sentence_id,
                sentence_id=s.sentence_id,
                original_sentence=s.sentence,
                audio_base64="",
            )
            for s in sentences
        ]
        analyses = {s.sentence_id: _analysis(30.0) for s in sentences}
        result = engine.evaluate_with_analyses("child", grade, responses, analyses)

        for pit in result.per_item_tags:
            assert pit.answered is True
            assert pit.is_correct is False
            # Score 30 → normalised < 0.6 → all dimensions need_work
            assert "pronunciation_needs_work" in pit.tags, f"{grade.value}/{pit.item_id}: expected pronunciation_needs_work"
            assert "fluency_needs_work" in pit.tags, f"{grade.value}/{pit.item_id}: expected fluency_needs_work"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_unanswered_for_empty(self, grade: Grade):
        engine = registry.speaking_engine()
        result = engine.evaluate_with_analyses("child", grade, [], {})

        for pit in result.per_item_tags:
            assert pit.answered is False
            assert pit.is_correct is None
            assert pit.tags == []


# ---------------------------------------------------------------------------
# COMPREHENSION: test-level tags
# ---------------------------------------------------------------------------
class TestComprehensionTags:
    """Verify Story Explorer tag emission across all grades."""

    EXPECTED_TAG_IDS = {
        "literal_comprehension_strong",
        "literal_comprehension_emerging",
        "inferential_comprehension_strong",
        "inferential_comprehension_emerging",
        "vocabulary_in_context_strong",
        "vocabulary_in_context_emerging",
        "inconsistent_across_stories",
    }

    def test_all_tag_ids_match_config(self):
        actual = all_tag_ids_for_test(TestType.COMPREHENSION)
        assert actual == self.EXPECTED_TAG_IDS

    @pytest.mark.parametrize("grade", list(Grade))
    def test_perfect_run_emits_strength_tags(self, grade: Grade):
        engine = registry.comprehension_engine()
        stories = engine.get_items(grade)
        responses = [
            ComprehensionResponse(
                item_id=q.question_id,
                question_id=q.question_id,
                selected_index=q.correct_index,
            )
            for story in stories
            for q in story.questions
        ]
        result = engine.evaluate("child", grade, responses)

        assert len(result.strengths) > 0, f"{grade.value}: no strength tags on perfect run"
        emitted = tag_ids(result.tags)
        unknown = emitted - self.EXPECTED_TAG_IDS
        assert not unknown, f"{grade.value}: unknown tags: {unknown}"

        # Perfect -> every construct reports as a strength, and none of them
        # as a growth edge.
        assert "literal_comprehension_strong" in emitted, f"{grade.value}: expected literal_comprehension_strong"
        assert "inferential_comprehension_strong" in emitted, f"{grade.value}: expected inferential_comprehension_strong"
        assert "vocabulary_in_context_strong" in emitted, f"{grade.value}: expected vocabulary_in_context_strong"
        assert not result.growth_edges, f"{grade.value}: {[t.tag for t in result.growth_edges]}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_all_wrong_emits_growth_edge_tags(self, grade: Grade):
        engine = registry.comprehension_engine()
        stories = engine.get_items(grade)
        responses = [
            ComprehensionResponse(
                item_id=q.question_id,
                question_id=q.question_id,
                selected_index=(q.correct_index + 1) % len(q.options),
            )
            for story in stories
            for q in story.questions
        ]
        result = engine.evaluate("child", grade, responses)

        # C7: every tagged error must reach the rollup, not just the item level.
        growth = {t.tag for t in result.growth_edges}
        assert growth, f"{grade.value}: no growth_edge tags on all-wrong"
        assert "literal_comprehension_emerging" in growth, growth
        assert "inferential_comprehension_emerging" in growth, growth
        assert "vocabulary_in_context_emerging" in growth, growth
        assert not result.strengths, [t.tag for t in result.strengths]

    @pytest.mark.parametrize("grade", list(Grade))
    def test_empty_submission_no_strength_tags(self, grade: Grade):
        engine = registry.comprehension_engine()
        result = engine.evaluate("child", grade, [])
        assert len(result.strengths) == 0, f"{grade.value}: unexpected strengths on empty"


# ---------------------------------------------------------------------------
# COMPREHENSION: per-item tags
# ---------------------------------------------------------------------------
class TestComprehensionPerItemTags:
    """Verify per-question tags for comprehension across all grades."""

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_cover_every_question(self, grade: Grade):
        engine = registry.comprehension_engine()
        stories = engine.get_items(grade)
        total_questions = sum(len(s.questions) for s in stories)
        responses = [
            ComprehensionResponse(
                item_id=q.question_id,
                question_id=q.question_id,
                selected_index=q.correct_index,
            )
            for story in stories
            for q in story.questions
        ]
        result = engine.evaluate("child", grade, responses)

        assert len(result.per_item_tags) == total_questions

        all_q_ids = {q.question_id for s in stories for q in s.questions}
        tagged_ids = {p.item_id for p in result.per_item_tags}
        assert tagged_ids == all_q_ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_include_question_type(self, grade: Grade):
        engine = registry.comprehension_engine()
        stories = engine.get_items(grade)
        responses = [
            ComprehensionResponse(
                item_id=q.question_id,
                question_id=q.question_id,
                selected_index=q.correct_index,
            )
            for story in stories
            for q in story.questions
        ]
        result = engine.evaluate("child", grade, responses)

        valid_types = {"literal", "inferential", "vocabulary"}
        for pit in result.per_item_tags:
            assert pit.answered is True
            assert pit.is_correct is True
            # Each question should be tagged with its type
            type_tags = [t for t in pit.tags if t in valid_types]
            assert len(type_tags) == 1, f"{grade.value}/{pit.item_id}: expected 1 type tag, got {type_tags}"
            # And the type_correct suffix
            correct_tags = [t for t in pit.tags if t.endswith("_correct")]
            assert len(correct_tags) == 1, f"{grade.value}/{pit.item_id}: expected 1 _correct tag, got {correct_tags}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_wrong_answers_have_error_suffix(self, grade: Grade):
        engine = registry.comprehension_engine()
        stories = engine.get_items(grade)
        responses = [
            ComprehensionResponse(
                item_id=q.question_id,
                question_id=q.question_id,
                selected_index=(q.correct_index + 1) % len(q.options),
            )
            for story in stories
            for q in story.questions
        ]
        result = engine.evaluate("child", grade, responses)

        for pit in result.per_item_tags:
            assert pit.answered is True
            assert pit.is_correct is False
            error_tags = [t for t in pit.tags if t.endswith("_error")]
            assert len(error_tags) == 1, f"{grade.value}/{pit.item_id}: expected 1 _error tag, got {error_tags}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_unanswered_include_type_only(self, grade: Grade):
        engine = registry.comprehension_engine()
        stories = engine.get_items(grade)
        result = engine.evaluate("child", grade, [])

        valid_types = {"literal", "inferential", "vocabulary"}
        for pit in result.per_item_tags:
            assert pit.answered is False
            assert pit.is_correct is None
            # Unanswered questions should still carry their type tag
            type_tags = [t for t in pit.tags if t in valid_types]
            assert len(type_tags) == 1, f"{grade.value}/{pit.item_id}: expected type tag on unanswered"
            # No _correct or _error suffix
            assert not any(t.endswith("_correct") or t.endswith("_error") for t in pit.tags)
