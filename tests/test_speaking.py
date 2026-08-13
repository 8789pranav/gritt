"""Tests for speaking (Voice Challenge) assessment endpoints."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_get_speaking_sentence(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/speaking/get_sentence/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "sentence_id" in data
    assert "sentence" in data
    assert data["audio_base64"] is not None
    assert data["word_count"] > 0


@pytest.mark.asyncio
async def test_get_speaking_sentence_all_grades(client, mock_firebase_auth, seed_user, mock_tts):
    for grade in ["Kindergarten", "First", "Second", "Third"]:
        resp = await client.post("/speaking/get_sentence/", json={
            "idToken": "test-token",
            "child_id": "child-1",
            "grade": grade,
        })
        assert resp.status_code == 200
        assert resp.json()["sentence"] != ""


@pytest.mark.asyncio
async def test_get_all_speaking_sentences(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/speaking/get_all_sentences/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sentences"] > 0
    assert len(data["sentences"]) == data["total_sentences"]
    assert data["sentences"][0]["audio_base64"] is not None


@pytest.mark.asyncio
async def test_speaking_analyze(client, mock_firebase_auth, seed_user, mock_speech):
    resp = await client.post("/speaking/analyze/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "original_sentence": "The cat sat on the mat.",
        "audio_base64": "fake_audio_data",
        "audio_format": "mp3",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["transcribed_text"] == "The cat sat on the mat."
    assert "pronunciation" in data
    assert "fluency" in data
    assert "overall" in data
    assert data["overall"]["score"] == 82


@pytest.mark.asyncio
async def test_speaking_analyze_transcription_failure(client, mock_firebase_auth, seed_user):
    with patch("app.infrastructure.hybrid_speech.HybridSpeechProvider.analyze_with_audio", new_callable=AsyncMock,
               return_value={"success": False, "error": "Audio too short"}):
        resp = await client.post("/speaking/analyze/", json={
            "idToken": "test-token",
            "child_id": "child-1",
            "grade": "Kindergarten",
            "original_sentence": "The cat sat on the mat.",
            "audio_base64": "bad_audio",
        })
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_speaking_submit_single(client, mock_firebase_auth, seed_user, mock_speech):
    sent_resp = await client.post("/speaking/get_sentence/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    sentence_id = sent_resp.json()["sentence_id"]
    sentence = sent_resp.json()["sentence"]

    resp = await client.post("/speaking/submit/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "sentence_id": sentence_id,
        "original_sentence": sentence,
        "audio_base64": "fake_audio",
        "audio_format": "mp3",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["answered_count"] >= 1
    assert "dear_parent_tags" in data
    assert "results" in data
    assert len(data["results"]) > 0


@pytest.mark.asyncio
async def test_speaking_submit_batch(client, mock_firebase_auth, seed_user, mock_speech):
    all_resp = await client.post("/speaking/get_all_sentences/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    sentences = all_resp.json()["sentences"]

    submissions = [
        {
            "sentence_id": s["sentence_id"],
            "original_sentence": s["sentence"],
            "audio_base64": "fake_audio",
            "audio_format": "mp3",
        }
        for s in sentences[:2]
    ]

    resp = await client.post("/speaking/submit/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "submissions": submissions,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["answered_count"] == 2
    assert data["total_marks"] == len(sentences) * 100


@pytest.mark.asyncio
async def test_speaking_complete_result(client, mock_firebase_auth, seed_user, mock_speech):
    sent_resp = await client.post("/speaking/get_sentence/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    sid = sent_resp.json()["sentence_id"]
    sentence = sent_resp.json()["sentence"]

    await client.post("/speaking/submit/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "sentence_id": sid,
        "original_sentence": sentence,
        "audio_base64": "fake_audio",
    })

    resp = await client.post("/speaking/complete_result/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "parent_summary" in data
    assert "all_results" in data
    assert "dear_parent_tags" in data


@pytest.mark.asyncio
async def test_speaking_complete_result_not_found(client, mock_firebase_auth, seed_user):
    resp = await client.post("/speaking/complete_result/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 404
