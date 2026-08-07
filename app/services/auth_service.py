"""Authentication & account management service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
)
from app.core.security import verify_token
from app.infrastructure.repositories import (
    ChildRepository,
    UserRepository,
    sanitize_data,
)

VALID_GRADES = ["Kindergarten", "First", "Second", "Third"]


class AuthService:
    """Handles registration, login, profile, and child management."""

    def __init__(self) -> None:
        from app.infrastructure.firebase import get_firebase_client

        self._client = get_firebase_client()
        self._users = UserRepository(self._client)
        self._children = ChildRepository(self._client)

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- registration & login ----------------------------------------------
    def register(self, email: str, name: str, password: Optional[str]) -> Dict[str, Any]:
        from firebase_admin import auth as firebase_auth

        try:
            user = firebase_auth.create_user(
                email=email,
                password=password,
                display_name=name,
            )
        except firebase_auth.EmailAlreadyExistsError:
            raise ValidationError("Email already registered")
        except Exception as exc:
            raise ValidationError(f"Registration failed: {exc}")

        self._users.create(user.uid, {"name": name, "email": email})
        return {"message": "User created successfully", "user_id": user.uid}

    def login(self, email: str, password: str) -> Dict[str, Any]:
        settings = get_settings()
        if not settings.firebase.api_key:
            raise AuthenticationError("Firebase API key not configured")

        try:
            response = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
                f"?key={settings.firebase.api_key}",
                json={
                    "email": email,
                    "password": password,
                    "returnSecureToken": True,
                },
            )
            data = response.json()
            if response.status_code == 200 and "idToken" in data:
                return {
                    "id_token": data["idToken"],
                    "refresh_token": data["refreshToken"],
                    "expires_in": data["expiresIn"],
                    "user_id": data["localId"],
                }
            raise AuthenticationError(
                data.get("error", {}).get("message", "Unknown error")
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(f"Login failed: {exc}")

    def save_user_data(self, id_token: str, name: str, email: str) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        payload = {
            "name": name,
            "email": email,
            "created_at": self._utc_now(),
        }
        self._users.create(uid, payload)
        return {"message": "User data saved successfully", "user_id": uid}

    def get_user_details(self, id_token: str, email: str, name: str, age: int) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        user_data = self._users.get(uid)
        if not user_data:
            raise NotFoundError("User data not found")
        if (
            user_data.get("email") == email
            and user_data.get("name") == name
            and user_data.get("age") == age
        ):
            return {
                "name": user_data.get("name", ""),
                "email": user_data.get("email", ""),
                "age": user_data.get("age", ""),
            }
        raise ValidationError("Provided user details do not match stored data")

    # -- child management ---------------------------------------------------
    def add_child(self, id_token: str, name: str, age: int, grade: str) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        if not name or age < 0 or grade not in VALID_GRADES:
            raise ValidationError("Invalid child data: name, age, or grade")

        child_id = str(uuid.uuid4())
        child_data = {
            "name": name,
            "age": age,
            "grade": grade,
            "created_at": self._utc_now(),
        }
        self._children.add(uid, child_id, child_data)
        return {"child_id": child_id, "message": "Child added successfully"}

    def get_children(self, id_token: str) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        children_data = self._children.list(uid)
        children = [
            {
                "child_id": child_id,
                "name": data.get("name", ""),
                "age": data.get("age", 0),
                "grade": data.get("grade", ""),
            }
            for child_id, data in children_data.items()
        ]
        return {"children": children}

    def get_all_child_details(self, id_token: str) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        children_data = self._children.list(uid)
        from app.infrastructure.repositories import ScoreRepository

        score_repo = ScoreRepository(self._client)
        children = []
        for child_id, data in children_data.items():
            scores_data = score_repo.get_all(uid, child_id, "scores")
            scores = [
                {
                    "score_id": score_id,
                    "grade": s.get("grade", ""),
                    "evaluation": s.get("evaluation", {}),
                    "assessment_summary": s.get("assessment_summary", {}),
                    "error_analysis": s.get("error_analysis", {}),
                    "instructional_recommendation": s.get(
                        "instructional_recommendation", ""
                    ),
                    "timestamp": s.get("timestamp", ""),
                }
                for score_id, s in scores_data.items()
            ]
            children.append(
                {
                    "child_id": child_id,
                    "name": data.get("name", ""),
                    "age": data.get("age", 0),
                    "grade": data.get("grade", ""),
                    "scores": scores,
                }
            )
        return {"children": children}

    def delete_child(self, id_token: str, child_id: str) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        child_data = self._children.get(uid, child_id)
        if not child_data:
            raise NotFoundError("Child not found")
        self._children.delete_subtree(uid, child_id, "scores")
        self._children.delete(uid, child_id)
        return {
            "message": "Child and all associated data deleted successfully.",
            "deleted_child_id": child_id,
        }
