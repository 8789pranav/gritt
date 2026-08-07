"""Tests for Logic Quest assessment endpoints."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_logic_get_test(client, mock_firebase_auth, seed_user):
    resp = await client.post("/logic/get_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total_items"] == 8
    assert len(data["items"]) == 8
    item = data["items"][0]
    assert "item_id" in item
    assert "question_text" in item
    assert "options" in item
    assert len(item["options"]) >= 2


@pytest.mark.asyncio
async def test_logic_get_test_all_grades(client, mock_firebase_auth, seed_user):
    for grade in ["Kindergarten", "First", "Second", "Third"]:
        resp = await client.post("/logic/get_test/", json={
            "idToken": "test-token",
            "child_id": "child-1",
            "grade": grade,
        })
        assert resp.status_code == 200
        assert resp.json()["total_items"] == 8


@pytest.mark.asyncio
async def test_logic_get_test_invalid_grade(client, mock_firebase_auth, seed_user):
    resp = await client.post("/logic/get_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Fifth",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_logic_submit_test_perfect(client, mock_firebase_auth, seed_user):
    test_resp = await client.post("/logic/get_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    items = test_resp.json()["items"]

    from app.engines.registry import logic_engine
    from app.domain.enums import Grade
    engine = logic_engine()
    all_items = engine.get_items(Grade.KINDERGARTEN)
    item_map = {i.item_id: i for i in all_items}

    responses = []
    for item in items:
        correct_idx = item_map[item["item_id"]].correct_answer_index
        responses.append({
            "item_id": item["item_id"],
            "selected_answer_index": correct_idx,
            "response_time_seconds": 10,
            "attempts": 1,
            "self_corrected": False,
        })

    resp = await client.post("/logic/submit_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "responses": responses,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentage"] == 100.0
    assert data["correct_answers"] == 8
    assert len(data["dear_parent_tags"]) > 0


@pytest.mark.asyncio
async def test_logic_submit_test_all_wrong(client, mock_firebase_auth, seed_user):
    from app.engines.registry import logic_engine
    from app.domain.enums import Grade
    engine = logic_engine()
    all_items = engine.get_items(Grade.KINDERGARTEN)

    responses = [
        {
            "item_id": item.item_id,
            "selected_answer_index": (item.correct_answer_index + 1) % len(item.options),
            "response_time_seconds": 10,
        }
        for item in all_items
    ]

    resp = await client.post("/logic/submit_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "responses": responses,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentage"] == 0.0
    assert data["correct_answers"] == 0


@pytest.mark.asyncio
async def test_logic_submit_response_single(client, mock_firebase_auth, seed_user):
    test_resp = await client.post("/logic/get_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    items = test_resp.json()["items"]
    first_item = items[0]

    from app.engines.registry import logic_engine
    from app.domain.enums import Grade
    engine = logic_engine()
    all_items = engine.get_items(Grade.KINDERGARTEN)
    item_map = {i.item_id: i for i in all_items}
    correct_idx = item_map[first_item["item_id"]].correct_answer_index

    resp = await client.post("/logic/submit_response/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "item_id": first_item["item_id"],
        "selected_answer_index": correct_idx,
        "response_time_seconds": 5,
        "attempts": 1,
        "self_corrected": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_correct"] is True
    assert "feedback" in data
    assert "correct_answer" in data


@pytest.mark.asyncio
async def test_logic_submit_response_wrong(client, mock_firebase_auth, seed_user):
    test_resp = await client.post("/logic/get_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    first_item = test_resp.json()["items"][0]

    from app.engines.registry import logic_engine
    from app.domain.enums import Grade
    engine = logic_engine()
    all_items = engine.get_items(Grade.KINDERGARTEN)
    item_map = {i.item_id: i for i in all_items}
    correct_idx = item_map[first_item["item_id"]].correct_answer_index
    wrong_idx = (correct_idx + 1) % len(first_item["options"])

    resp = await client.post("/logic/submit_response/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "item_id": first_item["item_id"],
        "selected_answer_index": wrong_idx,
        "response_time_seconds": 5,
    })
    assert resp.status_code == 200
    assert resp.json()["is_correct"] is False


@pytest.mark.asyncio
async def test_logic_complete_result(client, mock_firebase_auth, seed_user):
    test_resp = await client.post("/logic/get_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    items = test_resp.json()["items"]

    from app.engines.registry import logic_engine
    from app.domain.enums import Grade
    engine = logic_engine()
    all_items = engine.get_items(Grade.KINDERGARTEN)
    item_map = {i.item_id: i for i in all_items}

    responses = [
        {
            "item_id": item["item_id"],
            "selected_answer_index": item_map[item["item_id"]].correct_answer_index,
            "response_time_seconds": 10,
        }
        for item in items
    ]

    await client.post("/logic/submit_test/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "responses": responses,
    })

    resp = await client.post("/logic/complete_result/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["percentage"] == 100.0
    assert "dear_parent_tags" in data


@pytest.mark.asyncio
async def test_logic_complete_result_not_found(client, mock_firebase_auth, seed_user):
    resp = await client.post("/logic/complete_result/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_logic_get_test_with_audio(client, mock_firebase_auth, seed_user, mock_tts):
    resp = await client.post("/logic/get_test_with_audio/", json={
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total_items"] == 8
    item = data["items"][0]
    assert item["question_audio_base64"] is not None
    assert len(item["options"]) >= 2
    assert item["options"][0]["audio_base64"] is not None
