"""
Comprehensive score & results verification for every test type × every grade.

Verifies through the full API pipeline (router → service → engine → repository):
  1. Perfect submission → 100% score, correct count, strength tags emitted
  2. All-wrong submission → 0% (or near-0) score, growth-edge tags emitted
  3. Partial submission → score between 0 and 100, correct count
  4. complete_result → all expected fields present and consistent
  5. Per-item tags → every item has tags, correct is_correct flag
  6. Score persistence → saved and retrievable via complete_result
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.domain.enums import Grade, TestType, WordType
from app.domain.models import (
    ComprehensionResponse,
    LogicResponse,
    SpeakingResponse,
    SpellingResponse,
)
from app.engines import registry
from app.engines.speaking.analyzer import DimensionScore, SpeechAnalysis


def _analysis(score: float) -> SpeechAnalysis:
    dim = DimensionScore(score=score)
    return SpeechAnalysis(
        pronunciation=dim, fluency=dim, prosody=dim, grammar=dim,
        speaking_rate=dim, overall_score=score, level="test", recommendation="test",
    )


GRADES = list(Grade)
GRADE_STR = ["Kindergarten", "First", "Second", "Third"]


# ===========================================================================
# LOGIC QUEST
# ===========================================================================
class TestLogicScores:
    """Verify Logic Quest scores and results for every grade."""

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_perfect_score(self, client, mock_firebase_auth, seed_user, grade):
        """Perfect submission → 100%, all correct, strength tags."""
        engine = registry.logic_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)

        test_resp = await client.post("/logic/get_test/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        assert test_resp.status_code == 200
        api_items = test_resp.json()["items"]
        assert len(api_items) == len(items)

        item_map = {i.item_id: i for i in items}
        responses = [
            {
                "item_id": item["item_id"],
                "selected_answer_index": item_map[item["item_id"]].correct_answer_index,
                "response_time_seconds": 10,
            }
            for item in api_items
        ]

        resp = await client.post("/logic/submit_test/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "responses": responses,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["percentage"] == 100.0, f"{grade}: expected 100%, got {data['percentage']}"
        assert data["correct_answers"] == len(items), f"{grade}: correct_answers mismatch"
        assert data["total_items"] == len(items)
        assert len(data["dear_parent_tags"]) > 0, f"{grade}: no tags emitted"
        assert all(t["polarity"] in ("strength", "growth_edge", "neutral") for t in data["dear_parent_tags"])
        assert "per_item_tags" in data
        assert len(data["per_item_tags"]) == len(items)
        assert all(p["answered"] for p in data["per_item_tags"])
        assert all(p["is_correct"] for p in data["per_item_tags"])

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_zero_score(self, client, mock_firebase_auth, seed_user, grade):
        """All-wrong submission → 0%, no correct, growth-edge tags."""
        engine = registry.logic_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)

        responses = [
            {
                "item_id": item.item_id,
                "selected_answer_index": (item.correct_answer_index + 1) % len(item.options),
                "response_time_seconds": 10,
            }
            for item in items
        ]

        resp = await client.post("/logic/submit_test/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "responses": responses,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["percentage"] == 0.0, f"{grade}: expected 0%, got {data['percentage']}"
        assert data["correct_answers"] == 0
        assert data["total_items"] == len(items)
        assert len(data["per_item_tags"]) == len(items)
        assert all(p["answered"] for p in data["per_item_tags"])
        assert not any(p["is_correct"] for p in data["per_item_tags"])

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_partial_score(self, client, mock_firebase_auth, seed_user, grade):
        """Half correct → 50%, correct count matches."""
        engine = registry.logic_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)
        half = len(items) // 2

        responses = []
        for idx, item in enumerate(items):
            if idx < half:
                responses.append({
                    "item_id": item.item_id,
                    "selected_answer_index": item.correct_answer_index,
                    "response_time_seconds": 10,
                })
            else:
                responses.append({
                    "item_id": item.item_id,
                    "selected_answer_index": (item.correct_answer_index + 1) % len(item.options),
                    "response_time_seconds": 10,
                })

        resp = await client.post("/logic/submit_test/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "responses": responses,
        })
        assert resp.status_code == 200
        data = resp.json()

        expected_pct = round(half / len(items) * 100, 1)
        assert data["percentage"] == expected_pct, f"{grade}: expected {expected_pct}%, got {data['percentage']}"
        assert data["correct_answers"] == half

        correct_items = [p for p in data["per_item_tags"] if p["is_correct"]]
        wrong_items = [p for p in data["per_item_tags"] if not p["is_correct"]]
        assert len(correct_items) == half
        assert len(wrong_items) == len(items) - half

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_complete_result_fields(self, client, mock_firebase_auth, seed_user, grade):
        """complete_result returns all expected fields with correct values."""
        engine = registry.logic_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)

        responses = [
            {
                "item_id": item.item_id,
                "selected_answer_index": item.correct_answer_index,
                "response_time_seconds": 10,
            }
            for item in items
        ]
        await client.post("/logic/submit_test/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "responses": responses,
        })

        resp = await client.post("/logic/complete_result/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["percentage"] == 100.0
        assert data["correct_answers"] == len(items)
        assert data["total_items"] == len(items)
        assert "dear_parent_tags" in data and len(data["dear_parent_tags"]) > 0
        assert "per_item_tags" in data and len(data["per_item_tags"]) == len(items)
        assert "signals" in data
        assert "level" in data
        assert "scored_items" in data

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_single_response_correct(self, client, mock_firebase_auth, seed_user, grade):
        """Single item response returns correct feedback."""
        engine = registry.logic_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)
        item = items[0]

        resp = await client.post("/logic/submit_response/", json={
            "idToken": "test-token", "child_id": "child-1",
            "item_id": item.item_id,
            "selected_answer_index": item.correct_answer_index,
            "response_time_seconds": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_correct"] is True
        assert data["correct_answer_index"] == item.correct_answer_index
        assert "feedback" in data
        assert "correct_answer" in data


# ===========================================================================
# SPELLING (Word Wizard)
# ===========================================================================
class TestSpellingScores:
    """Verify Spelling scores and results for every grade."""

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_perfect_score(self, client, mock_firebase_auth, seed_user, grade):
        """All words spelled correctly → 100%."""
        engine = registry.spelling_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)

        resp = await client.post("/submit_words/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
            "words": [
                {"word": w.word, "user_input": w.word, "type": w.word_type.value, "time": 5.0}
                for w in items
            ],
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["evaluation"]["percentage"] == 100.0, f"{grade}: expected 100%, got {data['evaluation']['percentage']}"
        assert data["evaluation"]["level"] is not None
        assert len(data["dear_parent_tags"]) > 0, f"{grade}: no tags"
        assert "per_word_tags" in data
        assert len(data["per_word_tags"]) == len(items)
        assert all(p["answered"] for p in data["per_word_tags"])
        assert all(p["is_correct"] for p in data["per_word_tags"])
        assert "results" in data
        assert len(data["results"]) == len(items)
        assert all(r["is_correct"] for r in data["results"])
        assert "assessment_summary" in data
        assert "error_analysis" in data
        assert "strengths" in data
        assert "focus_areas" in data
        assert "confidence" in data

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_zero_score(self, client, mock_firebase_auth, seed_user, grade):
        """All words misspelled → near-0%."""
        engine = registry.spelling_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)

        resp = await client.post("/submit_words/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
            "words": [
                {"word": w.word, "user_input": "zzqq", "type": w.word_type.value, "time": 5.0}
                for w in items
            ],
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["evaluation"]["percentage"] < 20.0, f"{grade}: expected <20%, got {data['evaluation']['percentage']}"
        assert data["evaluation"]["level"] is not None
        assert len(data["per_word_tags"]) == len(items)
        assert all(p["answered"] for p in data["per_word_tags"])
        assert not all(p["is_correct"] for p in data["per_word_tags"])

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_partial_score(self, client, mock_firebase_auth, seed_user, grade):
        """Half correct → score reflects partial accuracy."""
        engine = registry.spelling_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)
        half = len(items) // 2

        words = []
        for idx, w in enumerate(items):
            words.append({
                "word": w.word,
                "user_input": w.word if idx < half else "zzqq",
                "type": w.word_type.value,
                "time": 5.0,
            })

        resp = await client.post("/submit_words/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
            "words": words,
        })
        assert resp.status_code == 200
        data = resp.json()

        pct = data["evaluation"]["percentage"]
        assert 0 < pct < 100, f"{grade}: expected partial score, got {pct}"
        correct_items = [p for p in data["per_word_tags"] if p["is_correct"]]
        assert len(correct_items) == half, f"{grade}: expected {half} correct, got {len(correct_items)}"

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_complete_result_fields(self, client, mock_firebase_auth, seed_user, grade):
        """complete_result returns all expected fields."""
        engine = registry.spelling_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)

        await client.post("/submit_words/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
            "words": [
                {"word": w.word, "user_input": w.word, "type": w.word_type.value, "time": 5.0}
                for w in items
            ],
        })

        resp = await client.post("/complete_result/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "parent_summary" in data
        assert "teacher_admin_detail" in data
        assert "dear_parent_tags" in data
        assert len(data["dear_parent_tags"]) > 0
        assert "per_word_tags" in data
        assert data["parent_summary"]["overall_accuracy"] == 100
        assert data["teacher_admin_detail"]["correct"] == len(items)


# ===========================================================================
# SPEAKING (Voice Challenge)
# ===========================================================================
class TestSpeakingScores:
    """Verify Voice Challenge scores for every grade.

    These drive SpeakingPipeline.analyse_sentence, which is where the service
    meets the Azure signal chain. The old tests patched
    HybridSpeechProvider.analyze_with_audio, which nothing calls any more - so
    they were asserting against a mock the code had stopped consulting.
    """

    @staticmethod
    def _pipeline_returning(**scores):
        """A pipeline stand-in that scores every sentence the same way."""
        from app.engines.speaking.metrics import (
            DisfluencyMetrics, PHONICS_FEATURES, ReadingMetrics, TimingMetrics,
        )

        async def fake(self, submission, grade):
            if not (submission.audio_base64 or "").strip():
                from app.engines.speaking.metrics import empty_sentence_metrics

                payload = empty_sentence_metrics(
                    submission.reference_text, "no_audio", "No recording.")
                payload["sentence_id"] = submission.sentence_id
                return payload
            words = len(submission.reference_text.split())
            return {
                "sentence_id": submission.sentence_id,
                "status": "answered",
                "reference": submission.reference_text,
                "recognized": submission.reference_text,
                "verbatim": submission.reference_text.lower(),
                "channel_agreement": 1.0,
                "scores": dict(scores),
                "reading": ReadingMetrics(
                    words, words, scores["accuracy"], 60.0, 5.0, "in_band"
                ).as_dict(),
                "timing": {**TimingMetrics(100.0, 1, 0, 200.0, 200.0, 200.0,
                                           5000.0).as_dict(),
                           "time_to_speak_ms": 700.0},
                "disfluency": DisfluencyMetrics([], 0, 0.0, 0, []).as_dict(),
                "phonics": {n: scores["accuracy"] for n in PHONICS_FEATURES},
                "errors": {"omission": 0, "insertion": 0, "mispronunciation": 0,
                           "unexpected_break": 0, "missing_break": 0,
                           "monotone": 0, "clear_error": 0,
                           "needs_attention": 0, "prolonged": 0,
                           "words_flagged": 0},
                "findings": [],
                "words": [],
                "attempt": 1,
            }

        return patch(
            "app.engines.speaking.pipeline.SpeakingPipeline.analyse_sentence",
            new=fake,
        )

    @staticmethod
    async def _submit(client, grade):
        engine = registry.speaking_engine()
        sentences = engine.get_items(Grade.parse(grade))
        submissions = [
            {"sentence_id": s.sentence_id, "original_sentence": s.sentence,
             "audio_base64": "cmVjb3JkaW5n", "audio_format": "wav",
             "time_to_speak_ms": 700, "attempt": 1}
            for s in sentences
        ]
        resp = await client.post("/speaking/submit/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "submissions": submissions,
        })
        return sentences, resp

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_perfect_score(self, client, mock_firebase_auth, seed_user, grade):
        """A strong reading scores high and reports strengths."""
        with self._pipeline_returning(accuracy=97.0, fluency=95.0,
                                      completeness=100.0, prosody=93.0,
                                      pron_score=95.2):
            sentences, resp = await self._submit(client, grade)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["answered_count"] == len(sentences)
        assert data["percentage"] >= 90.0, (
            f"{grade}: expected >=90%, got {data['percentage']}")
        assert data["level"] == "Excellent Speaker"
        strengths = [t for t in data["dear_parent_tags"]
                     if t["polarity"] == "strength"]
        assert strengths, f"{grade}: no strength tags on a strong reading"

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_weak_score(self, client, mock_firebase_auth, seed_user, grade):
        """A struggling reading scores low and reports growth edges."""
        with self._pipeline_returning(accuracy=48.0, fluency=45.0,
                                      completeness=60.0, prosody=42.0,
                                      pron_score=46.8):
            sentences, resp = await self._submit(client, grade)

        assert resp.status_code == 200
        data = resp.json()
        assert data["percentage"] < 60.0, (
            f"{grade}: expected <60%, got {data['percentage']}")
        growth = [t for t in data["dear_parent_tags"]
                  if t["polarity"] == "growth_edge"]
        assert growth, f"{grade}: no growth edge on a weak reading"

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_nothing_recorded_scores_zero(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        engine = registry.speaking_engine()
        sentences = engine.get_items(Grade.parse(grade))
        submissions = [
            {"sentence_id": s.sentence_id, "original_sentence": s.sentence,
             "audio_base64": "", "audio_format": "wav"}
            for s in sentences
        ]
        resp = await client.post("/speaking/submit/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "submissions": submissions,
        })
        data = resp.json()
        assert data["user_score"] == 0.0
        assert data["answered_count"] == 0
        assert data["percentage"] == 0.0
        assert not data["dear_parent_tags"]
        assert all(r["status"] == "Not Attempted" for r in data["results"])

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_complete_result_fields(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        with self._pipeline_returning(accuracy=88.0, fluency=85.0,
                                      completeness=95.0, prosody=80.0,
                                      pron_score=84.4):
            sentences, resp = await self._submit(client, grade)
        assert resp.status_code == 200

        result = await client.post("/speaking/complete_result/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        assert result.status_code == 200
        data = result.json()
        for key in ("parent_summary", "dear_parent_tags",
                    "per_sentence_tags", "teacher_admin_detail"):
            assert key in data, key


class TestComprehensionScores:
    """Verify Comprehension scores and results for every grade."""

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_perfect_score(self, client, mock_firebase_auth, seed_user, mock_tts, grade):
        """All correct answers → 100%."""
        engine = registry.comprehension_engine()
        grade_enum = Grade.parse(grade)
        stories = engine.get_items(grade_enum)
        total_q = sum(len(s.questions) for s in stories)

        stories_resp = await client.post("/comprehension/get_stories/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        assert stories_resp.status_code == 200
        api_stories = stories_resp.json()["stories"]

        q_map = {}
        for s in stories:
            for q in s.questions:
                q_map[q.question_id] = q

        story_answers = []
        for story in api_stories:
            answers = [
                {"question_id": q["id"], "selected_index": q_map[q["id"]].correct_index}
                for q in story["questions"]
            ]
            story_answers.append({"story_id": story["story_id"], "answers": answers})

        resp = await client.post("/comprehension/submit/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "story_answers": story_answers,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["percentage"] == 100.0, f"{grade}: expected 100%, got {data['percentage']}"
        assert data["correct_answers"] == total_q
        assert data["total_questions"] == total_q
        assert len(data["dear_parent_tags"]) > 0, f"{grade}: no tags"
        assert "per_question_tags" in data
        assert len(data["per_question_tags"]) == total_q
        assert all(p["answered"] for p in data["per_question_tags"])
        assert all(p["is_correct"] for p in data["per_question_tags"])
        assert "results" in data

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_zero_score(self, client, mock_firebase_auth, seed_user, mock_tts, grade):
        """All wrong answers → 0%."""
        engine = registry.comprehension_engine()
        grade_enum = Grade.parse(grade)
        stories = engine.get_items(grade_enum)
        total_q = sum(len(s.questions) for s in stories)

        story_answers = []
        for story in stories:
            answers = [
                {"question_id": q.question_id, "selected_index": (q.correct_index + 1) % len(q.options)}
                for q in story.questions
            ]
            story_answers.append({"story_id": story.story_id, "answers": answers})

        resp = await client.post("/comprehension/submit/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "story_answers": story_answers,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["percentage"] == 0.0, f"{grade}: expected 0%, got {data['percentage']}"
        assert data["correct_answers"] == 0
        assert data["total_questions"] == total_q
        assert all(p["answered"] for p in data["per_question_tags"])
        assert not any(p["is_correct"] for p in data["per_question_tags"])

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_partial_score(self, client, mock_firebase_auth, seed_user, mock_tts, grade):
        """Half correct → 50%."""
        engine = registry.comprehension_engine()
        grade_enum = Grade.parse(grade)
        stories = engine.get_items(grade_enum)

        all_questions = [(s, q) for s in stories for q in s.questions]
        half = len(all_questions) // 2

        story_answer_map: Dict[str, List[Dict]] = {}
        for idx, (story, q) in enumerate(all_questions):
            if story.story_id not in story_answer_map:
                story_answer_map[story.story_id] = []
            if idx < half:
                story_answer_map[story.story_id].append({
                    "question_id": q.question_id,
                    "selected_index": q.correct_index,
                })
            else:
                story_answer_map[story.story_id].append({
                    "question_id": q.question_id,
                    "selected_index": (q.correct_index + 1) % len(q.options),
                })

        story_answers = [
            {"story_id": sid, "answers": ans}
            for sid, ans in story_answer_map.items()
        ]

        resp = await client.post("/comprehension/submit/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "story_answers": story_answers,
        })
        assert resp.status_code == 200
        data = resp.json()

        expected_pct = round(half / len(all_questions) * 100, 1)
        assert data["percentage"] == expected_pct, f"{grade}: expected {expected_pct}%, got {data['percentage']}"
        assert data["correct_answers"] == half

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_complete_result_fields(self, client, mock_firebase_auth, seed_user, mock_tts, grade):
        """complete_result returns all expected fields."""
        engine = registry.comprehension_engine()
        grade_enum = Grade.parse(grade)
        stories = engine.get_items(grade_enum)

        q_map = {}
        for s in stories:
            for q in s.questions:
                q_map[q.question_id] = q

        story_answers = []
        for story in stories:
            answers = [
                {"question_id": q.question_id, "selected_index": q.correct_index}
                for q in story.questions
            ]
            story_answers.append({"story_id": story.story_id, "answers": answers})

        await client.post("/comprehension/submit/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "story_answers": story_answers,
        })

        resp = await client.post("/comprehension/complete_result/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["summary"]["percentage"] == 100.0
        assert data["summary"]["correct_answers"] == data["summary"]["total_questions"]
        assert "parent_summary" in data
        assert "story_breakdown" in data
        assert "dear_parent_tags" in data and len(data["dear_parent_tags"]) > 0
        assert "per_question_tags" in data

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_answers_withheld_from_client(self, client, mock_firebase_auth, seed_user, mock_tts, grade):
        """get_stories must NOT leak correct_index to the client."""
        resp = await client.post("/comprehension/get_stories/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        assert resp.status_code == 200
        for story in resp.json()["stories"]:
            for q in story["questions"]:
                assert "correct_index" not in q, f"{grade}: correct_index leaked in {q['id']}"


# ===========================================================================
# CROSS-TEST: Score persistence and retrieval
# ===========================================================================
class TestScorePersistence:
    """Verify scores are saved and retrievable across all test types."""

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_logic_score_persisted(self, client, mock_firebase_auth, seed_user, grade):
        """Submit then complete_result returns the same score."""
        engine = registry.logic_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)

        responses = [
            {
                "item_id": item.item_id,
                "selected_answer_index": item.correct_answer_index,
                "response_time_seconds": 10,
            }
            for item in items
        ]
        submit_resp = await client.post("/logic/submit_test/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "responses": responses,
        })
        submit_pct = submit_resp.json()["percentage"]

        complete_resp = await client.post("/logic/complete_result/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        complete_pct = complete_resp.json()["percentage"]

        assert submit_pct == complete_pct, f"{grade}: submit={submit_pct}, complete={complete_pct}"

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_spelling_score_persisted(self, client, mock_firebase_auth, seed_user, grade):
        engine = registry.spelling_engine()
        grade_enum = Grade.parse(grade)
        items = engine.get_items(grade_enum)

        await client.post("/submit_words/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
            "words": [
                {"word": w.word, "user_input": w.word, "type": w.word_type.value, "time": 5.0}
                for w in items
            ],
        })

        resp = await client.post("/complete_result/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["parent_summary"]["overall_accuracy"] == 100.0

    @pytest.mark.parametrize("grade", GRADE_STR)
    async def test_comprehension_score_persisted(self, client, mock_firebase_auth, seed_user, mock_tts, grade):
        engine = registry.comprehension_engine()
        grade_enum = Grade.parse(grade)
        stories = engine.get_items(grade_enum)

        q_map = {}
        for s in stories:
            for q in s.questions:
                q_map[q.question_id] = q

        story_answers = []
        for story in stories:
            answers = [
                {"question_id": q.question_id, "selected_index": q.correct_index}
                for q in story.questions
            ]
            story_answers.append({"story_id": story.story_id, "answers": answers})

        submit_resp = await client.post("/comprehension/submit/", json={
            "idToken": "test-token", "child_id": "child-1",
            "grade": grade, "story_answers": story_answers,
        })
        submit_pct = submit_resp.json()["percentage"]

        complete_resp = await client.post("/comprehension/complete_result/", json={
            "idToken": "test-token", "child_id": "child-1", "grade": grade,
        })
        complete_pct = complete_resp.json()["summary"]["percentage"]

        assert submit_pct == complete_pct, f"{grade}: submit={submit_pct}, complete={complete_pct}"
