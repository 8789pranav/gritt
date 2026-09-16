"""Regression tests for the Story Explorer bug list.

One test per bug from the Dear Parent Project review, named for the bug number
so a future failure points straight back at the decision it encodes.
"""

from __future__ import annotations

import json

import pytest

from app.domain.enums import Grade
from app.domain.models import ComprehensionResponse
from app.engines import registry

CONFIG = 'data/tags/comprehension_tags.json'


def _questions(grade: Grade):
    return [q for s in registry.comprehension_engine().get_items(grade)
            for q in s.questions]


def _run(grade: Grade, wrong_types=(), wrong_ids=(), all_wrong=False, times=None):
    """Answer every question, missing the given types / ids."""
    engine = registry.comprehension_engine()
    responses = []
    for q in _questions(grade):
        miss = (
            all_wrong
            or q.question_type.value in wrong_types
            or q.question_id in wrong_ids
        )
        responses.append(
            ComprehensionResponse(
                item_id=q.question_id,
                question_id=q.question_id,
                selected_index=(
                    (q.correct_index + 1) % len(q.options) if miss else q.correct_index
                ),
                response_time_seconds=(times or {}).get(q.question_id, 0.0),
            )
        )
    result = engine.evaluate("child", grade, responses)
    return result, {t.tag for t in result.tags}


def _polarity(result, tag_id):
    return next(t.polarity.value for t in result.tags if t.tag == tag_id)


# ---------------------------------------------------------------------------
# C7 - every tagged error must reach the rollup
# ---------------------------------------------------------------------------
class TestC7ErrorsReachTheRollup:
    @pytest.mark.parametrize("grade", list(Grade))
    def test_all_wrong_produces_growth_edges(self, grade: Grade):
        """The Kindergarten run: 9 tagged errors, dear_parent_tags EMPTY."""
        result, ids = _run(grade, all_wrong=True)
        item_errors = [
            t for p in result.per_item_tags for t in p.tags if t.endswith("_error")
        ]
        assert item_errors, f"{grade.value}: nothing tagged at item level"
        assert result.growth_edges, (
            f"{grade.value}: {len(item_errors)} item errors reached an empty rollup"
        )

    @pytest.mark.parametrize("grade", list(Grade))
    def test_each_construct_has_an_emerging_partner(self, grade: Grade):
        result, ids = _run(grade, all_wrong=True)
        assert "literal_comprehension_emerging" in ids, ids
        assert "inferential_comprehension_emerging" in ids, ids
        assert "vocabulary_in_context_emerging" in ids, ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_only_the_missed_construct_reports_emerging(self, grade: Grade):
        result, ids = _run(grade, wrong_types=("literal",))
        assert "literal_comprehension_emerging" in ids, ids
        assert "inferential_comprehension_strong" in ids, ids
        assert "inferential_comprehension_emerging" not in ids, ids

    def test_the_kindergarten_run_from_the_report(self):
        """9 of 11 wrong: 6 literal, 2 inferential, 1 vocabulary."""
        result, ids = _run(Grade.KINDERGARTEN, all_wrong=True)
        assert len(result.growth_edges) >= 3, [t.tag for t in result.growth_edges]
        assert not result.strengths, [t.tag for t in result.strengths]

    @pytest.mark.parametrize("grade", list(Grade))
    def test_sparse_copy_no_longer_fires_on_a_full_submission(self, grade: Grade):
        """C4's fallback existed for missing data, not for missing tags."""
        result, _ = _run(grade, all_wrong=True)
        assert result.tags, f"{grade.value}: no tags at all on a full submission"


# ---------------------------------------------------------------------------
# C10 - an _emerging tag is not a strength
# ---------------------------------------------------------------------------
class TestC10Polarity:
    def test_inferential_emerging_is_a_growth_edge(self):
        config = json.load(open(CONFIG, encoding="utf-8"))
        definition = next(
            t for t in config["tags"]
            if t["id"] == "inferential_comprehension_emerging"
        )
        assert definition["polarity"] == "growth_edge"

    @pytest.mark.parametrize("grade", list(Grade))
    def test_a_low_scorer_gets_no_praise_only_report(self, grade: Grade):
        """Grade 2: 2 of 10, and the only tag read as a strength."""
        result, _ = _run(grade, all_wrong=True)
        assert not result.strengths, [t.tag for t in result.strengths]

    @pytest.mark.parametrize("tag_id", [
        "literal_comprehension_emerging",
        "inferential_comprehension_emerging",
        "vocabulary_in_context_emerging",
    ])
    def test_no_emerging_tag_is_marked_a_strength(self, tag_id):
        config = json.load(open(CONFIG, encoding="utf-8"))
        definition = next(t for t in config["tags"] if t["id"] == tag_id)
        assert definition["polarity"] == "growth_edge"


# ---------------------------------------------------------------------------
# Vocabulary - both tags were unreachable
# ---------------------------------------------------------------------------
class TestVocabularyReachable:
    @pytest.mark.parametrize("grade", list(Grade))
    def test_every_grade_has_exactly_one_vocabulary_question(self, grade: Grade):
        types = [q.question_type.value for q in _questions(grade)]
        assert types.count("vocabulary") == 1, types

    @pytest.mark.parametrize("grade", list(Grade))
    def test_strong_fires_when_the_word_is_known(self, grade: Grade):
        result, ids = _run(grade)
        assert "vocabulary_in_context_strong" in ids, ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_emerging_fires_when_it_is_not(self, grade: Grade):
        result, ids = _run(grade, wrong_types=("vocabulary",))
        assert "vocabulary_in_context_emerging" in ids, ids
        assert "vocabulary_in_context_strong" not in ids

    def test_one_question_is_declared_low_confidence(self):
        """A single item decides the tag either way; say so in the payload."""
        config = json.load(open(CONFIG, encoding="utf-8"))
        for tag_id in ("vocabulary_in_context_strong", "vocabulary_in_context_emerging"):
            definition = next(t for t in config["tags"] if t["id"] == tag_id)
            assert definition["confidence"] == "low", tag_id


# ---------------------------------------------------------------------------
# listening_comprehension_strong - REMOVE
# ---------------------------------------------------------------------------
def test_listening_comprehension_strong_is_gone():
    """It cited overall_accuracy, which measures nothing about listening."""
    config = json.load(open(CONFIG, encoding="utf-8"))
    assert "listening_comprehension_strong" not in {t["id"] for t in config["tags"]}


@pytest.mark.parametrize("grade", list(Grade))
def test_perfect_run_does_not_emit_it(grade: Grade):
    result, ids = _run(grade)
    assert "listening_comprehension_strong" not in ids


def test_overall_accuracy_no_longer_drives_any_tag():
    config = json.load(open(CONFIG, encoding="utf-8"))
    for tag in config["tags"]:
        assert "overall_accuracy" not in tag["trigger"], tag["id"]


# ---------------------------------------------------------------------------
# C5 - response times
# ---------------------------------------------------------------------------
class TestC5ResponseTimes:
    def test_the_request_schema_accepts_a_time(self):
        """The field was absent, so anything the client sent was dropped."""
        from app.schemas import ComprehensionQuestionAnswer

        answer = ComprehensionQuestionAnswer(
            question_id="q1", selected_index=0, response_time_seconds=4.5
        )
        assert answer.response_time_seconds == 4.5

    def test_the_time_defaults_to_zero_when_absent(self):
        from app.schemas import ComprehensionQuestionAnswer

        answer = ComprehensionQuestionAnswer(question_id="q1", selected_index=0)
        assert answer.response_time_seconds == 0.0

    @pytest.mark.parametrize("grade", list(Grade))
    def test_scored_items_carry_the_time(self, grade: Grade):
        times = {q.question_id: 7.5 for q in _questions(grade)}
        result, _ = _run(grade, times=times)
        for item in result.score.scored_items:
            assert item.detail.get("response_time_seconds") == 7.5, item.detail

    @pytest.mark.parametrize("grade", list(Grade))
    def test_story_breakdown_carries_the_time(self, grade: Grade):
        engine = registry.comprehension_engine()
        times = {q.question_id: 6.25 for q in _questions(grade)}
        result, _ = _run(grade, times=times)
        breakdown = engine.story_breakdown(result.score)
        assert breakdown
        for story in breakdown:
            for question in story["questions"]:
                assert question["response_time_seconds"] == 6.25, question


# ---------------------------------------------------------------------------
# C8 - a question count is a whole number
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("grade", list(Grade))
def test_c8_total_questions_is_a_whole_number(grade: Grade):
    result, _ = _run(grade)
    assert isinstance(result.signals["total_questions"], int)
    assert isinstance(int(result.score.max_points), int)


# ---------------------------------------------------------------------------
# C11 - a collapse between stories in one sitting
# ---------------------------------------------------------------------------
class TestC11StoryCollapse:
    def _split(self, grade):
        engine = registry.comprehension_engine()
        stories = engine.get_items(grade)
        return stories[0], stories[1]

    @pytest.mark.parametrize("grade", list(Grade))
    def test_flags_one_story_near_zero_and_another_well(self, grade: Grade):
        """Grade 1: story 1 = 5 of 6, story 2 = 0 of 5, same sitting."""
        _, second = self._split(grade)
        result, ids = _run(grade, wrong_ids={q.question_id for q in second.questions})
        assert result.signals["stories_attempted"] == 2
        assert "inconsistent_across_stories" in ids, (
            ids, result.signals["story_score_gap"], result.signals["story_low_score"]
        )

    @pytest.mark.parametrize("grade", list(Grade))
    def test_silent_on_an_even_performance(self, grade: Grade):
        result, ids = _run(grade)
        assert "inconsistent_across_stories" not in ids

    @pytest.mark.parametrize("grade", list(Grade))
    def test_silent_when_both_stories_went_badly(self, grade: Grade):
        """A uniformly low score is not an inconsistency."""
        result, ids = _run(grade, all_wrong=True)
        assert "inconsistent_across_stories" not in ids

    def test_it_is_an_observation_not_a_verdict(self):
        config = json.load(open(CONFIG, encoding="utf-8"))
        definition = next(
            t for t in config["tags"] if t["id"] == "inconsistent_across_stories"
        )
        assert definition["polarity"] == "neutral"


# ---------------------------------------------------------------------------
# Parent copy stays in step with the config
# ---------------------------------------------------------------------------
def test_every_comprehension_tag_has_parent_copy():
    from app.services.report_service import ReportService

    config = json.load(open(CONFIG, encoding="utf-8"))
    ids = {t["id"] for t in config["tags"]}
    missing = ids - set(ReportService._TAG_SENTENCE_MAP)
    assert not missing, missing
