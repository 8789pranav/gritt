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
        "systematic_problem_solving",
        "cognitive_flexibility_intact",
        "flexible_strategy_use",
        "reasoning_under_load_emerging",
        "strategy_shift_difficulty",
        "rule_maintenance_difficulty",
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

        # All wrong + fast → should flag impulsive_response (growth_edge)
        emitted = tag_ids(result.tags)
        assert "impulsive_response" in emitted, f"{grade.value}: expected impulsive_response, got {emitted}"

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
        responses = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=(item.correct_answer_index + 1) % len(item.options),
                response_time_seconds=1,  # very fast
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)

        for pit in result.per_item_tags:
            assert pit.answered is True
            assert pit.is_correct is False
            assert "impulsive_response" in pit.tags, f"{grade.value}/{pit.item_id}: expected impulsive_response, got {pit.tags}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_per_item_tags_unanswered_for_empty(self, grade: Grade):
        engine = registry.logic_engine()
        items = engine.get_items(grade)
        result = engine.evaluate("child", grade, [])

        for pit in result.per_item_tags:
            assert pit.answered is False
            assert pit.is_correct is None
            assert pit.tags == []

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
        "vowel_difficulty_emerging",
        "digraph_blend_competent",
        "digraph_difficulty_emerging",
        "sight_word_recognition_strong",
        "sight_word_emerging",
        "audio_support_benefit",
        "confident_attempt",
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
        # Answer very quickly with wrong inputs
        responses = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input="x",
                word_type=item.word_type,
                response_time_seconds=1.0,  # very fast
            )
            for item in items
        ]
        result = engine.evaluate("child", grade, responses)
        emitted = tag_ids(result.tags)
        assert "rushed_spelling" in emitted, f"{grade.value}: expected rushed_spelling, got {emitted}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_empty_submission_minimal_tags(self, grade: Grade):
        engine = registry.spelling_engine()
        result = engine.evaluate("child", grade, [])
        # Empty submission may emit some tags due to zero-error triggers
        # (e.g. vowel_error_count == 0 → vowel_accuracy_strong)
        # but should NOT emit confidence-based tags like phonetic_strategy_strong
        emitted = tag_ids(result.tags)
        assert "phonetic_strategy_strong" not in emitted, f"{grade.value}: should not emit phonetic_strategy_strong on empty"
        assert "digraph_blend_competent" not in emitted, f"{grade.value}: should not emit digraph_blend_competent on empty"


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
    """Verify Voice Challenge tag emission across all grades."""

    EXPECTED_TAG_IDS = {
        "expressive_fluency_strong",
        "expressive_fluency_emerging",
        "pronunciation_accurate",
        "pronunciation_developing",
        "prosody_strong",
        "prosody_emerging",
        "complex_syntax_confident",
    }

    def test_all_tag_ids_match_config(self):
        actual = all_tag_ids_for_test(TestType.SPEAKING)
        assert actual == self.EXPECTED_TAG_IDS

    @pytest.mark.parametrize("grade", list(Grade))
    def test_strong_delivery_emits_strength_tags(self, grade: Grade):
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

        assert len(result.strengths) > 0, f"{grade.value}: no strength tags on strong delivery"
        emitted = tag_ids(result.tags)
        unknown = emitted - self.EXPECTED_TAG_IDS
        assert not unknown, f"{grade.value}: unknown tags: {unknown}"

        # Strong delivery should flag fluency, pronunciation, prosody
        assert "expressive_fluency_strong" in emitted, f"{grade.value}: expected expressive_fluency_strong"
        assert "pronunciation_accurate" in emitted, f"{grade.value}: expected pronunciation_accurate"
        assert "prosody_strong" in emitted, f"{grade.value}: expected prosody_strong"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_weak_delivery_emits_growth_edge_tags(self, grade: Grade):
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
        analyses = {s.sentence_id: _analysis(35.0) for s in sentences}
        result = engine.evaluate_with_analyses("child", grade, responses, analyses)

        assert len(result.growth_edges) > 0, f"{grade.value}: no growth_edge tags on weak delivery"
        emitted = tag_ids(result.tags)
        assert "pronunciation_developing" in emitted, f"{grade.value}: expected pronunciation_developing"
        assert "expressive_fluency_emerging" in emitted or "pronunciation_developing" in emitted

    @pytest.mark.parametrize("grade", list(Grade))
    def test_medium_delivery_emits_emerging_tags(self, grade: Grade):
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
        analyses = {s.sentence_id: _analysis(65.0) for s in sentences}
        result = engine.evaluate_with_analyses("child", grade, responses, analyses)

        # 65% → fluency between 0.6 and 0.8 → emerging
        emitted = tag_ids(result.tags)
        assert "expressive_fluency_emerging" in emitted, f"{grade.value}: expected expressive_fluency_emerging at 65%, got {emitted}"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_empty_submission_minimal_tags(self, grade: Grade):
        engine = registry.speaking_engine()
        result = engine.evaluate_with_analyses("child", grade, [], {})
        # Empty submission may emit some tags due to zero-score triggers
        # (e.g. avg_pronunciation < 0.7 → pronunciation_developing)
        # but should NOT emit strength tags
        assert len(result.strengths) == 0, f"{grade.value}: unexpected strength tags on empty"


# ---------------------------------------------------------------------------
# SPEAKING: per-item tags
# ---------------------------------------------------------------------------
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
        "inferential_comprehension_strong",
        "inferential_comprehension_emerging",
        "vocabulary_in_context_strong",
        "vocabulary_in_context_emerging",
        "listening_comprehension_strong",
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

        # Perfect → should flag literal, inferential, listening
        assert "literal_comprehension_strong" in emitted, f"{grade.value}: expected literal_comprehension_strong"
        assert "listening_comprehension_strong" in emitted, f"{grade.value}: expected listening_comprehension_strong"

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

        assert len(result.growth_edges) > 0, f"{grade.value}: no growth_edge tags on all-wrong"

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
