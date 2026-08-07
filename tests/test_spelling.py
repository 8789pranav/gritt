"""Tests for spelling assessment endpoints."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_get_grade_words(client, mock_firebase_auth):
    resp = await client.post("/grade/", json={"grade": "Kindergarten"})
    assert resp.status_code == 200
    data = resp.json()
    assert "words" in data
    assert len(data["words"]) > 0
    word = data["words"][0]
    assert "word" in word
    assert "type" in word
    assert "sentence" in word


@pytest.mark.asyncio
async def test_get_grade_words_all_grades(client, mock_firebase_auth):
    for grade in ["Kindergarten", "First", "Second", "Third"]:
        resp = await client.post("/grade/", json={"grade": grade})
        assert resp.status_code == 200
        assert len(resp.json()["words"]) > 0


@pytest.mark.asyncio
async def test_get_grade_words_invalid(client, mock_firebase_auth):
    resp = await client.post("/grade/", json={"grade": "Fifth"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_submit_words_perfect(client, mock_firebase_auth, seed_user):
    from app.engines.registry import spelling_engine
    from app.domain.enums import Grade
    engine = spelling_engine()
    all_words = engine.get_items(Grade.KINDERGARTEN)

    payload = {
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "words": [
            {"word": w.word, "user_input": w.word, "type": w.word_type.value, "time": 5.0, "hints_used": 0}
            for w in all_words
        ],
    }
    resp = await client.post("/submit_words/", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluation"]["percentage"] == 100.0
    assert len(data["dear_parent_tags"]) > 0
    assert "results" in data
    assert "assessment_summary" in data


@pytest.mark.asyncio
async def test_submit_words_all_wrong(client, mock_firebase_auth, seed_user):
    from app.engines.registry import spelling_engine
    from app.domain.enums import Grade
    engine = spelling_engine()
    all_words = engine.get_items(Grade.KINDERGARTEN)

    payload = {
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "words": [
            {"word": w.word, "user_input": "zzqq", "type": w.word_type.value, "time": 5.0, "hints_used": 0}
            for w in all_words
        ],
    }
    resp = await client.post("/submit_words/", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["evaluation"]["percentage"] < 20.0
    assert len(data["focus_areas"]) > 0 or len(data["error_analysis"]) > 0


@pytest.mark.asyncio
async def test_submit_words_invalid_child(client, mock_firebase_auth, seed_user):
    resp = await client.post("/submit_words/", json={
        "idToken": "test-token",
        "child_id": "nonexistent",
        "grade": "Kindergarten",
        "words": [{"word": "cat", "user_input": "cat", "type": "regular"}],
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_result(client, mock_firebase_auth, seed_user):
    from app.engines.registry import spelling_engine
    from app.domain.enums import Grade
    engine = spelling_engine()
    all_words = engine.get_items(Grade.KINDERGARTEN)

    await client.post("/submit_words/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "words": [
            {"word": w.word, "user_input": w.word, "type": w.word_type.value, "time": 5.0}
            for w in all_words
        ],
    })

    resp = await client.post("/complete_result/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "parent_summary" in data
    assert "teacher_admin_detail" in data
    assert "dear_parent_tags" in data


@pytest.mark.asyncio
async def test_complete_result_not_found(client, mock_firebase_auth, seed_user):
    resp = await client.post("/complete_result/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_text_audio(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/generate_text_audio/", json={
        "idToken": "test-token",
        "text": "hello world",
    })
    assert resp.status_code == 200
    assert "base64_audio" in resp.json()


@pytest.mark.asyncio
async def test_generate_all_grade_audio(client, mock_firebase_auth, mock_tts):
    resp = await client.post("/generate_all_grade_audio/", json={"grade": "Kindergarten"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["grade"] == "Kindergarten"
    assert len(data["audio_files"]) > 0
    assert data["audio_files"][0]["word_audio"] is not None
