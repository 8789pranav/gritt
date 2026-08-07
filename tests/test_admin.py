"""Tests for admin endpoints: stats, feedback, audio pre-generation, user management."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_make_admin(client, mock_firebase_auth, seed_user):
    mock_firebase_client = client._transport  # just to ensure fixture is active
    resp = await client.post("/admin/make-admin/", json={
        "idToken": "admin-token",
        "targetEmail": "test@test.com",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] is True
    assert "admin" in data["message"].lower()


@pytest.mark.asyncio
async def test_make_admin_non_admin(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/make-admin/", json={
        "idToken": "test-token",
        "targetEmail": "test@test.com",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_make_admin_user_not_found(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/make-admin/", json={
        "idToken": "admin-token",
        "targetEmail": "nobody@test.com",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_stats(client, mock_firebase_auth, seed_user):
    with patch("firebase_admin.auth.list_users") as mock_list:
        mock_page = MagicMock()
        mock_page.users = []
        mock_page.has_next_page = False
        mock_list.return_value = mock_page
        resp = await client.post("/admin/stats/", json={"idToken": "admin-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["isAdmin"] is True
    assert data["totalUsers"] >= 1


@pytest.mark.asyncio
async def test_admin_stats_non_admin(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/stats/", json={"idToken": "test-token"})
    assert resp.status_code == 200
    assert resp.json()["isAdmin"] is False


@pytest.mark.asyncio
async def test_submit_feedback(client, mock_firebase_auth, seed_user):
    resp = await client.post("/feedback/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "q1_grade": "Kindergarten",
        "q2_prior_assessments": "No",
        "q3_spelling_confidence": "High",
        "q4_assessment_length": "Just right",
        "q5_difficulty_level": "Medium",
        "q6_engagement_level": "High",
        "q7_technical_issues": "No",
        "q8_results_clarity": "Very clear",
        "q9_recommendations_helpful": "Yes",
        "q10_information_amount": "Just right",
        "q11_overall_satisfaction": "Very satisfied",
        "q12_comments": "Great app!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "feedback_id" in data
    assert data["saved_under"] == "parent_feedback"


@pytest.mark.asyncio
async def test_submit_feedback_invalid_child(client, mock_firebase_auth, seed_user):
    resp = await client.post("/feedback/", json={
        "idToken": "test-token",
        "child_id": "nonexistent",
        "q1_grade": "K",
        "q2_prior_assessments": "No",
        "q3_spelling_confidence": "High",
        "q4_assessment_length": "OK",
        "q5_difficulty_level": "Medium",
        "q6_engagement_level": "High",
        "q7_technical_issues": "No",
        "q8_results_clarity": "Clear",
        "q9_recommendations_helpful": "Yes",
        "q10_information_amount": "OK",
        "q11_overall_satisfaction": "Good",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_get_feedback(client, mock_firebase_auth, seed_user):
    await client.post("/feedback/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "q1_grade": "K",
        "q2_prior_assessments": "No",
        "q3_spelling_confidence": "High",
        "q4_assessment_length": "OK",
        "q5_difficulty_level": "Medium",
        "q6_engagement_level": "High",
        "q7_technical_issues": "No",
        "q8_results_clarity": "Clear",
        "q9_recommendations_helpful": "Yes",
        "q10_information_amount": "OK",
        "q11_overall_satisfaction": "Good",
    })

    resp = await client.post("/admin/feedback/", json={"idToken": "admin-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert len(data["feedbacks"]) >= 1


@pytest.mark.asyncio
async def test_admin_get_feedback_non_admin(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/feedback/", json={"idToken": "test-token"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pregenerate_spelling_audio(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/admin/pregenerate_spelling_audio/", json={"idToken": "admin-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "results" in data
    assert "generated" in data["results"]


@pytest.mark.asyncio
async def test_pregenerate_speaking_audio(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/admin/pregenerate_speaking_audio/", json={"idToken": "admin-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "results" in data


@pytest.mark.asyncio
async def test_pregenerate_story_audio(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/admin/pregenerate_story_audio/", json={"idToken": "admin-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "results" in data


@pytest.mark.asyncio
async def test_regenerate_story_audio(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/admin/regenerate_story_audio/?grade=Kindergarten", json={"idToken": "admin-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_pregenerate_logic_audio(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/admin/pregenerate_logic_audio/", json={"idToken": "admin-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "results" in data


@pytest.mark.asyncio
async def test_pregenerate_audio_non_admin(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/admin/pregenerate_spelling_audio/", json={"idToken": "test-token"})
    assert resp.status_code == 403
