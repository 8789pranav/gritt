"""FastAPI auth dependency: verify Firebase ID tokens."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import InvalidTokenError
from app.infrastructure.firebase import get_firebase_client

_security = HTTPBearer(auto_error=False)


async def get_firebase_user(
    token: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> dict:
    """Verify the Bearer token and return the decoded Firebase claims."""
    if not token:
        raise InvalidTokenError("No token provided")

    client = get_firebase_client()
    from firebase_admin import auth as firebase_auth

    try:
        return firebase_auth.verify_id_token(token.credentials)
    except Exception as exc:
        raise InvalidTokenError(str(exc)) from exc


def verify_token(id_token: str) -> dict:
    """Verify a raw ID-token string and return decoded claims."""
    client = get_firebase_client()
    from firebase_admin import auth as firebase_auth

    try:
        return firebase_auth.verify_id_token(id_token)
    except Exception as exc:
        raise InvalidTokenError(str(exc)) from exc


def verify_child(id_token: str, child_id: str) -> tuple[str, dict]:
    """Verify token + child ownership. Returns ``(uid, child_data)``."""
    decoded = verify_token(id_token)
    uid = decoded["uid"]
    child_repo = _child_repo()
    child_data = child_repo.get(uid, child_id)
    if not child_data:
        from app.core.exceptions import ChildNotFoundError

        raise ChildNotFoundError(child_id)
    return uid, child_data


def verify_paid_child(id_token: str, child_id: str) -> tuple[str, dict]:
    """Verify token + child ownership + payment.

    Returns ``(uid, child_data)``. Raises :class:`PaymentRequiredError`
    (HTTP 402) when the child has not been unlocked with a payment.
    """
    uid, child_data = verify_child(id_token, child_id)
    if child_data.get("payment_status") != "paid":
        from app.core.exceptions import PaymentRequiredError

        raise PaymentRequiredError(child_id)
    return uid, child_data


def verify_admin(id_token: str) -> str:
    """Verify token + admin flag. Returns ``uid``."""
    decoded = verify_token(id_token)
    uid = decoded["uid"]
    user_repo = _user_repo()
    if not user_repo.is_admin(uid):
        from app.core.exceptions import AdminRequiredError

        raise AdminRequiredError()
    return uid


# Lazy accessors to avoid requiring Firebase at import time
def _user_repo():
    from app.infrastructure.repositories import UserRepository

    return UserRepository()


def _child_repo():
    from app.infrastructure.repositories import ChildRepository

    return ChildRepository()
