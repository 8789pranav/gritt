"""Tests for the final report endpoint and ReportService.

Verifies:
  - Report generation with all 4 assessments present.
  - Report generation with partial assessments (some missing).
  - Tag validation — AI-cited tags that don't exist are removed.
  - Domain summary contains correct raw scores.
  - Report persistence to Firebase.
  - Error handling for missing child / invalid token.
  - Error handling when no assessments have been taken.
"""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import MockFirebaseClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
LOGIC_RESULT = {
    "grade": "Kindergarten",
    "percentage": 100.0,
    "correct_answers": 5,
    "total_items": 5,
    "level": "Above Grade Level",
    "dear_parent_tags": [
        {
            "tag": "pattern_detection_strong",
            "confidence": "high",
            "polarity": "strength",
            "description": "Child excels at recognising patterns.",
            "evidence": "Answered all pattern questions correctly.",
        },
        {
            "tag": "self_correction_present",
            "confidence": "medium",
            "polarity": "strength",
            "description": "Child self-corrects during problem solving.",
            "evidence": "Self-corrected on 2 items.",
        },
    ],
    "per_item_tags": [
        {"item_id": "q1", "answered": True, "is_correct": True, "tags": ["pattern_detection_strong"]},
        {"item_id": "q2", "answered": True, "is_correct": True, "tags": []},
        {"item_id": "q3", "answered": False, "is_correct": False, "tags": ["not_attempted"]},
    ],
    "signals": {"avg_response_time": 12.5, "self_corrections": 2},
    "scored_items": [],
    "timestamp": "2025-01-01T00:00:00Z",
}

SPELLING_RESULT = {
    "grade": "Kindergarten",
    "parent_summary": {
        "overall_accuracy": 80,
        "phonics_score": 75,
        "sight_word_score": 85,
        "confidence": "High",
        "strengths": ["Good sight word recognition"],
        "focus_areas": ["Vowel sounds in phonics words"],
        "key_error_patterns": [{"pattern": "vowel_error", "count": 2}],
        "recommendation": "Practice vowel sounds.",
        "note": "Instructional, not clinical.",
    },
    "dear_parent_tags": [
        {
            "tag": "sight_word_accuracy_strong",
            "confidence": "high",
            "polarity": "strength",
            "description": "Strong sight word recognition.",
            "evidence": "85% sight word accuracy.",
        },
        {
            "tag": "vowel_accuracy_developing",
            "confidence": "medium",
            "polarity": "growth_edge",
            "description": "Vowel accuracy needs development.",
            "evidence": "75% phonics score with vowel errors.",
        },
    ],
    "per_word_tags": [
        {"item_id": "cat", "answered": True, "is_correct": True, "tags": []},
        {"item_id": "cake", "answered": True, "is_correct": False, "tags": ["vowel_error"]},
        {"item_id": "fish", "answered": False, "is_correct": False, "tags": ["not_attempted"]},
    ],
    "error_analysis": {"vowel_error": 2},
    "timestamp": "2025-01-01T00:00:00Z",
}

SPEAKING_RESULT = {
    "grade": "Kindergarten",
    "percentage": 85.0,
    "average_score": 85.0,
    "answered_count": 3,
    "level": "Good Speaker",
    "dear_parent_tags": [
        {
            "tag": "fluency_strong",
            "confidence": "high",
            "polarity": "strength",
            "description": "Child speaks fluently.",
            "evidence": "Fluency score 90.",
        },
        {
            "tag": "pronunciation_needs_work",
            "confidence": "medium",
            "polarity": "growth_edge",
            "description": "Pronunciation needs practice.",
            "evidence": "Pronunciation score 70.",
        },
    ],
    "per_sentence_tags": [
        {"item_id": "s1", "answered": True, "is_correct": True, "tags": ["fluency_strong"]},
        {"item_id": "s2", "answered": False, "is_correct": False, "tags": ["not_attempted"]},
    ],
    "results": [],
    "timestamp": "2025-01-01T00:00:00Z",
}

COMPREHENSION_RESULT = {
    "grade": "Kindergarten",
    "percentage": 75.0,
    "correct_answers": 6,
    "total_questions": 8,
    "level": "At Grade Level",
    "dear_parent_tags": [
        {
            "tag": "literal_comprehension_strong",
            "confidence": "high",
            "polarity": "strength",
            "description": "Strong literal comprehension.",
            "evidence": "All literal questions correct.",
        },
        {
            "tag": "inferential_comprehension_error",
            "confidence": "medium",
            "polarity": "growth_edge",
            "description": "Inferential reasoning needs support.",
            "evidence": "2 of 3 inferential questions wrong.",
        },
    ],
    "per_question_tags": [
        {"item_id": "q1", "answered": True, "is_correct": True, "tags": ["literal_comprehension_strong"]},
        {"item_id": "q7", "answered": False, "is_correct": False, "tags": ["not_attempted"]},
    ],
    "results": [],
    "timestamp": "2025-01-01T00:00:00Z",
}

AI_RESPONSE = {
    "developmental_snapshot": "Test Child shows strong pattern recognition and self-correction abilities in logic, with good sight word recognition in spelling. Speaking fluency is a strength, though pronunciation needs some practice.",
    "strengths": [
        {
            "area": "Logic Reasoning",
            "description": "Child excels at recognising patterns and self-corrects during problem solving.",
            "evidence_tags": ["pattern_detection_strong", "self_correction_present"],
            "evidence_assessments": ["logic"],
        },
        {
            "area": "Spelling - Sight Words",
            "description": "Strong sight word recognition at 85% accuracy.",
            "evidence_tags": ["sight_word_accuracy_strong"],
            "evidence_assessments": ["spelling"],
        },
        {
            "area": "Speaking - Fluency",
            "description": "Child speaks fluently with good flow.",
            "evidence_tags": ["fluency_strong"],
            "evidence_assessments": ["speaking"],
        },
    ],
    "growth_areas": [
        {
            "area": "Spelling - Vowels",
            "description": "Vowel accuracy needs development, particularly in phonics words.",
            "evidence_tags": ["vowel_accuracy_developing"],
            "evidence_assessments": ["spelling"],
        },
        {
            "area": "Speaking - Pronunciation",
            "description": "Pronunciation could benefit from daily read-aloud practice.",
            "evidence_tags": ["pronunciation_needs_work"],
            "evidence_assessments": ["speaking"],
        },
        {
            "area": "Comprehension - Inferential",
            "description": "Inferential reasoning needs support — going beyond literal text.",
            "evidence_tags": ["inferential_comprehension_error"],
            "evidence_assessments": ["comprehension"],
        },
    ],
    "cross_domain_patterns": [
        {
            "pattern": "Phonological Processing",
            "description": "Vowel errors in spelling combined with pronunciation needs in speaking suggest a phonological processing pattern.",
            "assessments": ["spelling", "speaking"],
            "evidence_tags": ["vowel_accuracy_developing", "pronunciation_needs_work"],
        },
    ],
    "recommendations": [
        {
            "priority": "high",
            "action": "Practice vowel sounds with minimal pairs (e.g., bat/bet, sit/set) daily for 10 minutes.",
            "evidence_tags": ["vowel_accuracy_developing"],
            "evidence_assessments": ["spelling"],
        },
        {
            "priority": "medium",
            "action": "Read aloud together daily, emphasising clear pronunciation of tricky sounds.",
            "evidence_tags": ["pronunciation_needs_work"],
            "evidence_assessments": ["speaking"],
        },
        {
            "priority": "medium",
            "action": "Ask 'why do you think that?' questions during story time to build inferential reasoning.",
            "evidence_tags": ["inferential_comprehension_error"],
            "evidence_assessments": ["comprehension"],
        },
    ],
    "parent_message": "Test Child is showing wonderful strengths in pattern recognition, self-correction, and reading fluency! With some focused practice on vowel sounds and inferential thinking, they will continue to grow beautifully. Keep up the great work at home!",
}

AI_RESPONSE_WITH_FAKE_TAGS = {
    "developmental_snapshot": "Test Child is doing well.",
    "strengths": [
        {
            "area": "Logic",
            "description": "Great pattern recognition.",
            "evidence_tags": ["pattern_detection_strong", "fake_tag_that_doesnt_exist"],
            "evidence_assessments": ["logic"],
        },
    ],
    "growth_areas": [
        {
            "area": "Spelling",
            "description": "Vowel work needed.",
            "evidence_tags": ["vowel_accuracy_developing", "another_fake_tag"],
            "evidence_assessments": ["spelling"],
        },
    ],
    "cross_domain_patterns": [],
    "recommendations": [
        {
            "priority": "high",
            "action": "Practice vowels.",
            "evidence_tags": ["vowel_accuracy_developing", "completely_made_up_tag"],
            "evidence_assessments": ["spelling"],
        },
    ],
    "parent_message": "Keep it up!",
}


def _seed_all_assessments(client: MockFirebaseClient):
    """Seed all 4 assessment results into mock Firebase."""
    # Logic
    ref = client.ref("users/test-uid/children/child-1/logic_tests")
    key = ref.push().key
    ref.child(key).set(LOGIC_RESULT)

    # Spelling
    ref = client.ref("users/test-uid/children/child-1/scores")
    key = ref.push().key
    ref.child(key).set(SPELLING_RESULT)

    # Speaking
    ref = client.ref("users/test-uid/children/child-1/speaking_tests")
    key = ref.push().key
    ref.child(key).set(SPEAKING_RESULT)

    # Comprehension
    ref = client.ref("users/test-uid/children/child-1/comprehension_tests")
    key = ref.push().key
    ref.child(key).set(COMPREHENSION_RESULT)


def _seed_partial_assessments(client: MockFirebaseClient):
    """Seed only logic and spelling (no speaking or comprehension)."""
    ref = client.ref("users/test-uid/children/child-1/logic_tests")
    key = ref.push().key
    ref.child(key).set(LOGIC_RESULT)

    ref = client.ref("users/test-uid/children/child-1/scores")
    key = ref.push().key
    ref.child(key).set(SPELLING_RESULT)


def _mock_ai_response(response_dict: Dict[str, Any]):
    """Create a mock for AIProvider.synthesize_report."""
    mock_ai = MagicMock()
    mock_ai.synthesize_report.return_value = response_dict
    return mock_ai


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestFinalReport:
    """Tests for POST /final_report/ endpoint."""

    @pytest.mark.asyncio
    async def test_report_with_all_assessments(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Report includes all 4 assessments when all are present."""
        _seed_all_assessments(mock_firebase_client)

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        assert resp.status_code == 200
        data = resp.json()

        assert data["success"] is True
        assert data["child_id"] == "child-1"
        assert data["grade"] == "Kindergarten"
        assert data["child_name"] == "Test Child"

        # All 4 assessments included
        assert set(data["assessments_included"]) == {"logic", "spelling", "speaking", "comprehension"}
        assert data["assessments_missing"] == []

        # Domain summary has raw scores
        ds = data["domain_summary"]
        assert ds["logic"]["percentage"] == 100.0
        assert ds["spelling"]["overall_accuracy"] == 80
        assert ds["speaking"]["percentage"] == 85.0
        assert ds["comprehension"]["percentage"] == 75.0

        # AI report present
        ai = data["ai_report"]
        assert "developmental_snapshot" in ai
        assert len(ai["strengths"]) == 3
        assert len(ai["growth_areas"]) == 3
        assert len(ai["cross_domain_patterns"]) == 1
        assert len(ai["recommendations"]) == 3
        assert "parent_message" in ai

        # All tags present
        tags = data["all_tags"]
        assert len(tags["strengths"]) >= 4
        assert len(tags["growth_edges"]) >= 3

    @pytest.mark.asyncio
    async def test_report_with_partial_assessments(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Report works when only some assessments are present."""
        _seed_partial_assessments(mock_firebase_client)

        partial_ai = {
            "developmental_snapshot": "Partial report based on logic and spelling.",
            "strengths": [
                {
                    "area": "Logic",
                    "description": "Strong pattern recognition.",
                    "evidence_tags": ["pattern_detection_strong"],
                    "evidence_assessments": ["logic"],
                },
            ],
            "growth_areas": [
                {
                    "area": "Spelling",
                    "description": "Vowel accuracy developing.",
                    "evidence_tags": ["vowel_accuracy_developing"],
                    "evidence_assessments": ["spelling"],
                },
            ],
            "cross_domain_patterns": [],
            "recommendations": [],
            "parent_message": "Partial report — complete remaining assessments for full picture.",
        }

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(partial_ai)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        assert resp.status_code == 200
        data = resp.json()

        assert "logic" in data["assessments_included"]
        assert "spelling" in data["assessments_included"]
        assert "speaking" in data["assessments_missing"]
        assert "comprehension" in data["assessments_missing"]

        # Domain summary only has logic and spelling
        ds = data["domain_summary"]
        assert "logic" in ds
        assert "spelling" in ds
        assert "speaking" not in ds
        assert "comprehension" not in ds

    @pytest.mark.asyncio
    async def test_tag_validation_removes_fake_tags(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """AI-cited tags that don't exist in the data are removed."""
        _seed_all_assessments(mock_firebase_client)

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE_WITH_FAKE_TAGS)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        assert resp.status_code == 200
        data = resp.json()
        ai = data["ai_report"]

        # Real tags kept
        strength_tags = ai["strengths"][0]["evidence_tags"]
        assert "pattern_detection_strong" in strength_tags

        # Fake tags removed
        assert "fake_tag_that_doesnt_exist" not in strength_tags
        assert "another_fake_tag" not in ai["growth_areas"][0]["evidence_tags"]
        assert "completely_made_up_tag" not in ai["recommendations"][0]["evidence_tags"]

    @pytest.mark.asyncio
    async def test_report_persisted_to_firebase(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Report is saved under final_reports in Firebase."""
        _seed_all_assessments(mock_firebase_client)

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        assert resp.status_code == 200

        # Check Firebase has the report
        reports = mock_firebase_client.ref(
            "users/test-uid/children/child-1/final_reports"
        ).get()
        assert reports is not None
        assert len(reports) == 1
        saved = list(reports.values())[0]
        assert saved["grade"] == "Kindergarten"
        assert "report" in saved

    @pytest.mark.asyncio
    async def test_report_invalid_child(
        self, client, mock_firebase_auth, seed_user,
    ):
        """Report fails for non-existent child."""
        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "nonexistent", "grade": "Kindergarten",
            })

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_report_invalid_token(
        self, client, mock_firebase_auth, seed_user,
    ):
        """Report fails for invalid token."""
        resp = await client.post("/final_report/", json={
            "idToken": "invalid", "child_id": "child-1", "grade": "Kindergarten",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_report_no_assessments(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Report still generates when no assessments have been taken."""
        empty_ai = {
            "developmental_snapshot": "No assessment data available yet.",
            "strengths": [],
            "growth_areas": [],
            "cross_domain_patterns": [],
            "recommendations": [],
            "parent_message": "Please complete assessments to generate a report.",
        }

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(empty_ai)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        assert resp.status_code == 200
        data = resp.json()

        assert data["assessments_included"] == []
        assert set(data["assessments_missing"]) == {"logic", "spelling", "speaking", "comprehension"}
        assert data["domain_summary"] == {}
        assert data["all_tags"]["strengths"] == []
        assert data["all_tags"]["growth_edges"] == []

    @pytest.mark.asyncio
    async def test_report_cross_domain_pattern_uses_real_tags(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Cross-domain patterns must cite real tags from both assessments."""
        _seed_all_assessments(mock_firebase_client)

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        data = resp.json()
        patterns = data["ai_report"]["cross_domain_patterns"]
        assert len(patterns) == 1

        pattern = patterns[0]
        assert pattern["pattern"] == "Phonological Processing"
        assert set(pattern["assessments"]) == {"spelling", "speaking"}
        assert "vowel_accuracy_developing" in pattern["evidence_tags"]
        assert "pronunciation_needs_work" in pattern["evidence_tags"]

    @pytest.mark.asyncio
    async def test_report_strength_tags_have_correct_polarity(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """All strength tags have polarity='strength'."""
        _seed_all_assessments(mock_firebase_client)

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        data = resp.json()
        for tag in data["all_tags"]["strengths"]:
            assert tag["polarity"] == "strength"
        for tag in data["all_tags"]["growth_edges"]:
            assert tag["polarity"] == "growth_edge"

    @pytest.mark.asyncio
    async def test_report_domain_summary_has_tag_counts(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Domain summary includes tag_count per assessment."""
        _seed_all_assessments(mock_firebase_client)

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        data = resp.json()
        ds = data["domain_summary"]
        assert ds["logic"]["tag_count"] == 2
        assert ds["spelling"]["tag_count"] == 2
        assert ds["speaking"]["tag_count"] == 2
        assert ds["comprehension"]["tag_count"] == 2


class TestReportService:
    """Direct unit tests for ReportService."""

    def test_generate_report_calls_ai_with_context(
        self, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """ReportService passes structured context to AIProvider."""
        _seed_all_assessments(mock_firebase_client)

        mock_ai = _mock_ai_response(AI_RESPONSE)
        with patch("app.services.report_service.get_ai_provider", return_value=mock_ai):
            from app.services.report_service import ReportService
            svc = ReportService()
            report = svc.generate_final_report("test-token", "child-1", "Kindergarten")

        # Verify AI was called
        mock_ai.synthesize_report.assert_called_once()

        # Check the context passed to AI
        call_args = mock_ai.synthesize_report.call_args[0][0]
        assert "child" in call_args
        assert call_args["child"]["name"] == "Test Child"
        assert "assessments" in call_args
        assert "logic" in call_args["assessments"]
        assert "spelling" in call_args["assessments"]
        assert "speaking" in call_args["assessments"]
        assert "comprehension" in call_args["assessments"]
        assert len(call_args["all_strength_tags"]) >= 4
        assert len(call_args["all_growth_edge_tags"]) >= 3

    def test_generate_report_validates_evidence_tags(
        self, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """ReportService removes fake evidence_tags from AI output."""
        _seed_all_assessments(mock_firebase_client)

        mock_ai = _mock_ai_response(AI_RESPONSE_WITH_FAKE_TAGS)
        with patch("app.services.report_service.get_ai_provider", return_value=mock_ai):
            from app.services.report_service import ReportService
            svc = ReportService()
            report = svc.generate_final_report("test-token", "child-1", "Kindergarten")

        ai = report["ai_report"]
        # Fake tags removed from strengths
        assert "fake_tag_that_doesnt_exist" not in ai["strengths"][0]["evidence_tags"]
        # Fake tags removed from growth_areas
        assert "another_fake_tag" not in ai["growth_areas"][0]["evidence_tags"]
        # Fake tags removed from recommendations
        assert "completely_made_up_tag" not in ai["recommendations"][0]["evidence_tags"]
        # Real tags preserved
        assert "pattern_detection_strong" in ai["strengths"][0]["evidence_tags"]
        assert "vowel_accuracy_developing" in ai["growth_areas"][0]["evidence_tags"]


class TestUnansweredItems:
    """Tests for unanswered items and their tags in the final report."""

    @pytest.mark.asyncio
    async def test_unanswered_tags_collected(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Tags from unanswered items appear in all_tags.unanswered."""
        _seed_all_assessments(mock_firebase_client)

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        data = resp.json()
        unanswered_tags = data["all_tags"]["unanswered"]
        assert len(unanswered_tags) == 4  # one per assessment

        # Each unanswered tag has correct structure
        for tag in unanswered_tags:
            assert tag["polarity"] == "unanswered"
            assert tag["tag"] == "not_attempted"
            assert "item_id" in tag
            assert "source_assessment" in tag

        # Check one from each assessment
        sources = {t["source_assessment"] for t in unanswered_tags}
        assert "Logic Quest" in sources
        assert "Spelling Assessment" in sources
        assert "Speaking Challenge" in sources
        assert "Comprehension Assessment" in sources

    @pytest.mark.asyncio
    async def test_unanswered_count_in_context(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Each assessment context includes unanswered_count."""
        _seed_all_assessments(mock_firebase_client)

        mock_ai = _mock_ai_response(AI_RESPONSE)
        with patch("app.services.report_service.get_ai_provider", return_value=mock_ai):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        # Verify the context passed to AI has unanswered info
        call_args = mock_ai.synthesize_report.call_args[0][0]
        for assessment_name in ("logic", "spelling", "speaking", "comprehension"):
            ctx = call_args["assessments"][assessment_name]
            assert ctx["unanswered_count"] == 1
            assert len(ctx["unanswered_items"]) == 1
            assert ctx["unanswered_items"][0]["answered"] is False

    @pytest.mark.asyncio
    async def test_unanswered_tags_in_validation(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """Unanswered tags are included in known_tags for validation."""
        _seed_all_assessments(mock_firebase_client)

        ai_with_unanswered = {
            "developmental_snapshot": "Child skipped some items.",
            "strengths": [],
            "growth_areas": [
                {
                    "area": "Logic",
                    "description": "Child did not attempt 1 logic item.",
                    "evidence_tags": ["not_attempted"],
                    "evidence_assessments": ["logic"],
                },
            ],
            "cross_domain_patterns": [],
            "recommendations": [],
            "parent_message": "Encourage child to try all items.",
        }

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(ai_with_unanswered)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        data = resp.json()
        # not_attempted tag should be preserved (it exists in data)
        growth = data["ai_report"]["growth_areas"][0]
        assert "not_attempted" in growth["evidence_tags"]

    @pytest.mark.asyncio
    async def test_no_unanswered_items_when_all_answered(
        self, client, mock_firebase_auth, seed_user, mock_firebase_client,
    ):
        """No unanswered tags when all items are answered."""
        # Seed with all items answered
        logic_all_answered = {**LOGIC_RESULT, "per_item_tags": [
            {"item_id": "q1", "answered": True, "is_correct": True, "tags": ["pattern_detection_strong"]},
            {"item_id": "q2", "answered": True, "is_correct": True, "tags": []},
        ]}
        ref = mock_firebase_client.ref("users/test-uid/children/child-1/logic_tests")
        key = ref.push().key
        ref.child(key).set(logic_all_answered)

        with patch("app.services.report_service.get_ai_provider",
                   return_value=_mock_ai_response(AI_RESPONSE)):
            resp = await client.post("/final_report/", json={
                "idToken": "test-token", "child_id": "child-1", "grade": "Kindergarten",
            })

        data = resp.json()
        # No unanswered tags from logic (other assessments not seeded)
        logic_unanswered = [
            t for t in data["all_tags"]["unanswered"]
            if t["source_assessment"] == "Logic Quest"
        ]
        assert len(logic_unanswered) == 0
