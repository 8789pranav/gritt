"""Repository pattern over Firebase Realtime Database.

Each repository owns a specific subtree (``users/``, ``spelling_audio/``, …)
and exposes a small, intention-revealing API.  Services depend on these
abstractions rather than raw ``db.reference()`` calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.infrastructure.firebase import FirebaseClient, get_firebase_client

_INVALID_CHARS = [".", "#", "$", "[", "]", "/"]


def sanitize_key(key: str) -> str:
    """Replace characters that Firebase Realtime DB keys cannot contain."""
    sanitized = key
    for char in _INVALID_CHARS:
        sanitized = sanitized.replace(char, "_")
    return sanitized


def sanitize_data(data: Any) -> Any:
    """Recursively make *data* safe for Firebase writes."""
    if isinstance(data, dict):
        return {sanitize_key(k): sanitize_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_data(item) for item in data]
    if isinstance(data, (set, tuple)):
        return [sanitize_data(item) for item in list(data)]
    if isinstance(data, datetime):
        return data.isoformat()
    if isinstance(data, (int, float, str, bool)) or data is None:
        return data
    return str(data)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserRepository:
    """Read/write parent accounts under ``users/{uid}``."""

    def __init__(self, client: Optional[FirebaseClient] = None) -> None:
        self._client = client or get_firebase_client()

    def create(self, uid: str, data: Dict[str, Any]) -> None:
        self._client.ref(f"users/{uid}").set(data)

    def get(self, uid: str) -> Optional[Dict[str, Any]]:
        return self._client.ref(f"users/{uid}").get()

    def update(self, uid: str, fields: Dict[str, Any]) -> None:
        self._client.ref(f"users/{uid}").update(fields)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        return self._client.ref("users").get() or {}

    def is_admin(self, uid: str) -> bool:
        data = self.get(uid)
        return bool(data and data.get("isAdmin", False))


class ChildRepository:
    """Read/write child profiles under ``users/{uid}/children/{child_id}``."""

    def __init__(self, client: Optional[FirebaseClient] = None) -> None:
        self._client = client or get_firebase_client()

    def add(self, uid: str, child_id: str, data: Dict[str, Any]) -> None:
        self._client.ref(f"users/{uid}/children/{child_id}").set(data)

    def get(self, uid: str, child_id: str) -> Optional[Dict[str, Any]]:
        return self._client.ref(f"users/{uid}/children/{child_id}").get()

    def list(self, uid: str) -> Dict[str, Dict[str, Any]]:
        return self._client.ref(f"users/{uid}/children").get() or {}

    def delete(self, uid: str, child_id: str) -> None:
        self._client.ref(f"users/{uid}/children/{child_id}").delete()

    def delete_subtree(self, uid: str, child_id: str, subtree: str) -> None:
        self._client.ref(
            f"users/{uid}/children/{child_id}/{subtree}"
        ).delete()


class ScoreRepository:
    """Persist and retrieve assessment results per child."""

    def __init__(self, client: Optional[FirebaseClient] = None) -> None:
        self._client = client or get_firebase_client()

    def _path(self, uid: str, child_id: str, test_collection: str) -> str:
        return f"users/{uid}/children/{child_id}/{test_collection}"

    def save(
        self,
        uid: str,
        child_id: str,
        test_collection: str,
        data: Dict[str, Any],
    ) -> str:
        ref = self._client.ref(self._path(uid, child_id, test_collection))
        new_key = ref.push().key
        ref.child(new_key).set(sanitize_data(data))
        return new_key

    def get_all(
        self,
        uid: str,
        child_id: str,
        test_collection: str,
    ) -> Dict[str, Dict[str, Any]]:
        return self._client.ref(
            self._path(uid, child_id, test_collection)
        ).get() or {}

    def get_latest(
        self,
        uid: str,
        child_id: str,
        test_collection: str,
        grade: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        all_tests = self.get_all(uid, child_id, test_collection)
        if not all_tests:
            return None
        filtered = []
        for test_id, test_data in all_tests.items():
            if grade and test_data.get("grade") != grade:
                continue
            filtered.append((test_data.get("timestamp", ""), test_data))
        if not filtered:
            return None
        filtered.sort(key=lambda x: x[0], reverse=True)
        return filtered[0][1]


class AudioCacheRepository:
    """Store and retrieve pre-generated TTS audio in Firebase."""

    def __init__(self, client: Optional[FirebaseClient] = None) -> None:
        self._client = client or get_firebase_client()

    def get_node(self, path: str) -> Optional[Dict[str, Any]]:
        return self._client.ref(path).get()

    def set_node(self, path: str, data: Dict[str, Any]) -> None:
        self._client.ref(path).set(data)

    def get_all_in(self, path: str) -> Dict[str, Any]:
        return self._client.ref(path).get() or {}


class PaymentRepository:
    """Payment records under ``payments/{payment_id}`` plus a Stripe
    Checkout session index under ``payment_sessions/{session_id}``."""

    def __init__(self, client: Optional[FirebaseClient] = None) -> None:
        self._client = client or get_firebase_client()

    def create(self, payment_id: str, data: Dict[str, Any]) -> None:
        self._client.ref(f"payments/{payment_id}").set(sanitize_data(data))
        session_id = data.get("stripe_session_id")
        if session_id:
            self._client.ref(
                f"payment_sessions/{sanitize_key(session_id)}"
            ).set(payment_id)

    def get(self, payment_id: str) -> Optional[Dict[str, Any]]:
        return self._client.ref(f"payments/{payment_id}").get()

    def get_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        payment_id = self._client.ref(
            f"payment_sessions/{sanitize_key(session_id)}"
        ).get()
        if not payment_id:
            return None
        data = self.get(payment_id)
        if data is not None:
            data.setdefault("payment_id", payment_id)
        return data

    def update(self, payment_id: str, fields: Dict[str, Any]) -> None:
        self._client.ref(f"payments/{payment_id}").update(sanitize_data(fields))


class FeedbackRepository:
    """Parent feedback stored under ``parent_feedback/``."""

    def __init__(self, client: Optional[FirebaseClient] = None) -> None:
        self._client = client or get_firebase_client()

    def save(self, feedback_id: str, payload: Dict[str, Any]) -> None:
        self._client.ref(f"parent_feedback/{feedback_id}").set(payload)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        return self._client.ref("parent_feedback").get() or {}
