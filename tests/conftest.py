"""Shared test fixtures: mock Firebase, OpenAI, and external services."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Firebase mock
# ---------------------------------------------------------------------------
class MockFirebaseClient:
    """In-memory Firebase client that stores data in a nested dict."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    def ref(self, path: str) -> "MockRef":
        return MockRef(self._data, path)


class MockRef:
    def __init__(self, data: Dict[str, Any], path: str) -> None:
        self._data = data
        self._path = path

    def _navigate(self) -> Dict[str, Any]:
        parts = self._path.split("/")
        node = self._data
        for p in parts:
            if p == "":
                continue
            if p not in node:
                node[p] = {}
            node = node[p]
        return node

    def get(self) -> Any:
        node = self._navigate()
        if not node:
            return None
        return node

    def set(self, value: Any) -> None:
        parts = self._path.split("/")
        node = self._data
        for p in parts[:-1]:
            if p == "":
                continue
            if p not in node:
                node[p] = {}
            node = node[p]
        if parts[-1]:
            node[parts[-1]] = value

    def update(self, fields: Dict[str, Any]) -> None:
        node = self._navigate()
        node.update(fields)

    def delete(self) -> None:
        parts = self._path.split("/")
        node = self._data
        for p in parts[:-1]:
            if p == "":
                continue
            if p not in node:
                return
            node = node[p]
        if parts[-1] and parts[-1] in node:
            del node[parts[-1]]

    def child(self, key: str) -> "MockRef":
        return MockRef(self._data, f"{self._path}/{key}")

    def push(self) -> "MockRef":
        import uuid as _uuid

        key = _uuid.uuid4().hex
        parts = self._path.split("/")
        node = self._data
        for p in parts:
            if p == "":
                continue
            if p not in node:
                node[p] = {}
            node = node[p]
        node[key] = {}
        return MockRef(self._data, f"{self._path}/{key}")

    @property
    def key(self) -> str:
        return self._path.rsplit("/", 1)[-1]


@pytest.fixture
def mock_firebase_client() -> MockFirebaseClient:
    return MockFirebaseClient()


@pytest.fixture(autouse=True)
def patch_firebase(mock_firebase_client: MockFirebaseClient):
    """Patch all Firebase access to use the in-memory mock."""
    with patch("app.infrastructure.firebase.get_firebase_client", return_value=mock_firebase_client), \
         patch("app.infrastructure.repositories.get_firebase_client", return_value=mock_firebase_client), \
         patch("app.core.security.get_firebase_client", return_value=mock_firebase_client):
        yield


# ---------------------------------------------------------------------------
# Firebase Auth mock
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_firebase_auth():
    """Patch firebase_admin.auth to return predictable decoded tokens."""
    def fake_verify_token(token: str) -> dict:
        if not token or token == "invalid":
            raise Exception("Invalid token")
        if token == "admin-token":
            return {"uid": "admin-uid", "email": "admin@test.com"}
        return {"uid": "test-uid", "email": "test@test.com"}

    with patch("firebase_admin.auth.verify_id_token", side_effect=fake_verify_token):
        yield fake_verify_token


@pytest.fixture
def seed_user(mock_firebase_client: MockFirebaseClient, mock_firebase_auth):
    """Seed a test user and child into the mock Firebase."""
    mock_firebase_client.ref("users/test-uid").set({
        "name": "Test Parent",
        "email": "test@test.com",
        "isAdmin": False,
    })
    mock_firebase_client.ref("users/admin-uid").set({
        "name": "Admin",
        "email": "admin@test.com",
        "isAdmin": True,
    })
    mock_firebase_client.ref("users/test-uid/children/child-1").set({
        "name": "Test Child",
        "age": 6,
        "grade": "Kindergarten",
        "payment_status": "paid",
    })
    mock_firebase_client.ref("users/test-uid/children/child-unpaid").set({
        "name": "Unpaid Child",
        "age": 7,
        "grade": "First",
        "payment_status": "unpaid",
    })
    return {"uid": "test-uid", "child_id": "child-1", "token": "test-token"}


# ---------------------------------------------------------------------------
# TTS mock
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_tts():
    """Patch TTSProvider.synthesize to return fake base64 audio."""
    async def fake_synthesize(text: str, *, speed: float = 1.0) -> Optional[str]:
        if not text:
            return None
        return f"fake_audio_b64_{text[:20]}"

    with patch("app.infrastructure.tts.TTSProvider.synthesize", side_effect=fake_synthesize):
        yield


# ---------------------------------------------------------------------------
# Speech provider mock
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_speech():
    """Patch HybridSpeechProvider.analyze_with_audio."""
    analysis_result = {
        "success": True,
        "analysis": {
            "pronunciation": {"score": 85, "feedback": "Good pronunciation."},
            "speaking_rate": {"score": 80, "wpm": 120, "status": "Perfect", "feedback": "Good pace."},
            "fluency": {"score": 75, "long_pauses_count": 0, "feedback": "Smooth delivery."},
            "prosody": {"score": 70, "monotony_score": 0.6, "feedback": "Good expression."},
            "grammar": {"score": 90, "issues": [], "feedback": "No grammar issues."},
            "overall": {"score": 82, "status": "At", "level": "Good Speaker", "recommendation": "Keep practicing!", "parent_tip": "Read aloud daily.", "strengths": ["Pronunciation"], "areas_to_improve": ["Fluency"]},
        },
        "transcribed_text": "The cat sat on the mat.",
        "word_timestamps": [{"word": "The", "start": 0.0, "end": 0.3}],
        "duration": 3.5,
    }

    with patch("app.infrastructure.hybrid_speech.HybridSpeechProvider.analyze_with_audio", new_callable=AsyncMock, return_value=analysis_result):
        yield


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------
@pytest.fixture
async def client(mock_firebase_client, mock_firebase_auth):
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
