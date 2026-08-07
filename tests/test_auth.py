"""Tests for auth & account management endpoints."""

from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.asyncio
async def test_register(client, mock_firebase_auth):
    with patch("firebase_admin.auth.create_user") as mock_create:
        mock_create.return_value = MagicMock(uid="new-uid")
        resp = await client.post("/register/", json={
            "idToken": "test-token",
            "email": "new@test.com",
            "name": "New User",
            "password": "pass123",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "User created successfully"
    assert data["user_id"] == "new-uid"


@pytest.mark.asyncio
async def test_register_duplicate_email(client, mock_firebase_auth):
    with patch("firebase_admin.auth.create_user", side_effect=Exception("EMAIL_EXISTS")):
        resp = await client.post("/register/", json={
            "idToken": "test-token",
            "email": "dup@test.com",
            "name": "Dup",
            "password": "pass",
        })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client, mock_firebase_auth):
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"idToken": "tok", "refreshToken": "ref", "expiresIn": "3600", "localId": "uid1"},
        )
        resp = await client.post("/login", json={
            "email": "test@test.com",
            "password": "pass",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["id_token"] == "tok"
    assert data["user_id"] == "uid1"


@pytest.mark.asyncio
async def test_login_failure(client, mock_firebase_auth):
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=400,
            json=lambda: {"error": {"message": "INVALID_PASSWORD"}},
        )
        resp = await client.post("/login", json={
            "email": "test@test.com",
            "password": "wrong",
        })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_save_user_data(client, mock_firebase_auth):
    resp = await client.post("/save-user-data/", json={
        "idToken": "test-token",
        "email": "test@test.com",
        "name": "Test Parent",
    })
    assert resp.status_code == 200
    assert "saved successfully" in resp.json()["message"]


@pytest.mark.asyncio
async def test_add_child(client, mock_firebase_auth, seed_user):
    resp = await client.post("/add_child/", json={
        "idToken": "test-token",
        "name": "New Child",
        "age": 7,
        "grade": "First",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Child added successfully"
    assert "child_id" in data


@pytest.mark.asyncio
async def test_add_child_invalid_grade(client, mock_firebase_auth, seed_user):
    resp = await client.post("/add_child/", json={
        "idToken": "test-token",
        "name": "Bad Child",
        "age": 7,
        "grade": "Fifth",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_children(client, mock_firebase_auth, seed_user):
    resp = await client.post("/get_children/", json={"idToken": "test-token"})
    assert resp.status_code == 200
    children = resp.json()["children"]
    assert len(children) >= 1
    assert children[0]["name"] == "Test Child"


@pytest.mark.asyncio
async def test_get_all_child_details(client, mock_firebase_auth, seed_user):
    resp = await client.post("/get_all_child_details/", json={"idToken": "test-token"})
    assert resp.status_code == 200
    children = resp.json()["children"]
    assert len(children) >= 1
    assert "scores" in children[0]


@pytest.mark.asyncio
async def test_delete_child(client, mock_firebase_auth, seed_user):
    resp = await client.request("DELETE", "/delete_child/", json={
        "idToken": "test-token",
        "child_id": "child-1",
    })
    assert resp.status_code == 200
    assert "deleted successfully" in resp.json()["message"]


@pytest.mark.asyncio
async def test_delete_child_not_found(client, mock_firebase_auth, seed_user):
    resp = await client.request("DELETE", "/delete_child/", json={
        "idToken": "test-token",
        "child_id": "nonexistent",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_token(client, mock_firebase_auth):
    resp = await client.post("/get_children/", json={"idToken": "invalid"})
    assert resp.status_code == 401
