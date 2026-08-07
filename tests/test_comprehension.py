"""Tests for reading comprehension (Story Explorer) endpoints."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_get_comprehension_stories(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/comprehension/get_stories/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_stories"] > 0
    assert data["total_questions"] > 0
    story = data["stories"][0]
    assert "story_id" in story
    assert "title" in story
    assert "story_text" in story
    assert "story_audio_base64" in story
    assert "questions" in story
    assert len(story["questions"]) > 0
    assert "correct_index" not in story["questions"][0]


@pytest.mark.asyncio
async def test_get_comprehension_stories_all_grades(client, mock_firebase_auth, seed_user, mock_tts):
    for grade in ["Kindergarten", "First", "Second", "Third"]:
        resp = await client.post("/comprehension/get_stories/", json={
            "idToken": "test-token",
            "child_id": "child-1",
            "grade": grade,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_stories"] > 0
        assert data["total_questions"] > 0


@pytest.mark.asyncio
async def test_get_comprehension_stories_invalid_grade(client, mock_firebase_auth, seed_user):
    resp = await client.post("/comprehension/get_stories/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Fifth",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_comprehension_submit_perfect(client, mock_firebase_auth, seed_user, mock_tts):
    stories_resp = await client.post("/comprehension/get_stories/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    stories = stories_resp.json()["stories"]

    from app.engines.registry import comprehension_engine
    from app.domain.enums import Grade
    engine = comprehension_engine()
    all_stories = engine.get_items(Grade.KINDERGARTEN)
    q_map = {}
    for s in all_stories:
        for q in s.questions:
            q_map[q.question_id] = q

    story_answers = []
    for story in stories:
        answers = []
        for q in story["questions"]:
            correct_idx = q_map[q["id"]].correct_index
            answers.append({"question_id": q["id"], "selected_index": correct_idx})
        story_answers.append({"story_id": story["story_id"], "answers": answers})

    resp = await client.post("/comprehension/submit/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "story_answers": story_answers,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentage"] == 100.0
    assert data["correct_answers"] == data["total_questions"]
    assert len(data["dear_parent_tags"]) > 0
    assert "per_question_tags" in data
    assert "results" in data


@pytest.mark.asyncio
async def test_comprehension_submit_all_wrong(client, mock_firebase_auth, seed_user, mock_tts):
    stories_resp = await client.post("/comprehension/get_stories/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    stories = stories_resp.json()["stories"]

    story_answers = []
    for story in stories:
        answers = [
            {"question_id": q["id"], "selected_index": 3}
            for q in story["questions"]
        ]
        story_answers.append({"story_id": story["story_id"], "answers": answers})

    resp = await client.post("/comprehension/submit/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "story_answers": story_answers,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentage"] < 50.0
    assert data["correct_answers"] < data["total_questions"]


@pytest.mark.asyncio
async def test_comprehension_complete_result(client, mock_firebase_auth, seed_user, mock_tts):
    stories_resp = await client.post("/comprehension/get_stories/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    stories = stories_resp.json()["stories"]

    from app.engines.registry import comprehension_engine
    from app.domain.enums import Grade
    engine = comprehension_engine()
    all_stories = engine.get_items(Grade.KINDERGARTEN)
    q_map = {}
    for s in all_stories:
        for q in s.questions:
            q_map[q.question_id] = q

    story_answers = []
    for story in stories:
        answers = [
            {"question_id": q["id"], "selected_index": q_map[q["id"]].correct_index}
            for q in story["questions"]
        ]
        story_answers.append({"story_id": story["story_id"], "answers": answers})

    await client.post("/comprehension/submit/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "story_answers": story_answers,
    })

    resp = await client.post("/comprehension/complete_result/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["percentage"] == 100.0
    assert "dear_parent_tags" in data
    assert "story_breakdown" in data


@pytest.mark.asyncio
async def test_comprehension_complete_result_not_found(client, mock_firebase_auth, seed_user):
    resp = await client.post("/comprehension/complete_result/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 404
