"""Firebase Admin SDK initialisation and singleton client."""

from __future__ import annotations

import logging
from typing import Any, Optional

import firebase_admin
from firebase_admin import credentials, db

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_app: Optional[firebase_admin.App] = None
_db_ref: Optional[db.Reference] = None


class FirebaseClient:
    """Thin wrapper around the Firebase Admin SDK."""

    def __init__(self, app: firebase_admin.App, db_ref: db.Reference) -> None:
        self._app = app
        self._db = db_ref

    @property
    def app(self) -> firebase_admin.App:
        return self._app

    @property
    def db(self) -> db.Reference:
        return self._db

    def ref(self, path: str = "") -> db.Reference:
        return self._db.child(path)


def get_firebase_client() -> FirebaseClient:
    """Return the process-wide Firebase client singleton."""
    global _app, _db_ref
    if _app is not None and _db_ref is not None:
        return FirebaseClient(_app, _db_ref)

    settings = get_settings()
    if not settings.firebase.is_configured:
        raise RuntimeError(
            "Firebase is not configured; set FIREBASE_CRED_BASE64 and FIREBASE_DB_URL"
        )

    cred_dict = settings.firebase.decode_credentials()
    cred = credentials.Certificate(cred_dict)

    _app = firebase_admin.initialize_app(cred, {
        "databaseURL": settings.firebase.database_url,
    })
    _db_ref = db.reference()
    logger.info("Firebase Admin SDK initialised")
    return FirebaseClient(_app, _db_ref)


def reset_firebase() -> None:
    """Drop the singleton (intended for tests)."""
    global _app, _db_ref
    if _app is not None:
        try:
            firebase_admin.delete_app(_app)
        except Exception:
            pass
    _app = None
    _db_ref = None
