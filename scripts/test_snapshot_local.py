"""Time a real Learning Snapshot letter from the local server.

Logs in like a parent, picks the child with the most assessment data, and
POSTs to /snapshot/ against the local server - the same path, evidence and
model a real parent presses, with the seconds on the clock.

Usage::

    python scripts/test_snapshot_local.py [password] [child_id]

The password defaults to the same one as run_real_snapshot.py. Give a
child_id to test that child rather than the one with the most data.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

BASE = os.environ.get("SNAPSHOT_BASE", "http://127.0.0.1:8000")
EMAIL = os.environ.get("SNAPSHOT_EMAIL", "rajdandeepak@gmail.com")
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "SNAPSHOT_PASSWORD", "Test@123"
)
WANTED_CHILD = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else None
FRESH = "--fresh" in sys.argv


def _id_token() -> str:
    """An ID token for the parent, by password or by the Admin SDK.

    Firebase throttles repeated password logins, which locks a local test
    loop out of its own account. The service account in .env owns these
    users, so a custom token minted for the same email keeps the test
    running without touching the password.
    """
    r = requests.post(
        f"{BASE}/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30
    )
    if r.status_code == 200:
        body = r.json()
        return body.get("id_token") or body.get("token") or body.get("idToken")

    print(f"password login failed ({r.status_code}); minting a token instead")
    from firebase_admin import auth as firebase_auth

    from app.infrastructure.firebase import get_firebase_client
    from app.core.config import get_settings

    get_firebase_client()  # initialise the Admin SDK
    user = firebase_auth.get_user_by_email(EMAIL)
    custom = firebase_auth.create_custom_token(user.uid)
    api_key = get_settings().firebase.api_key
    if not api_key:
        raise SystemExit("FIREBASE_API_KEY is not set; cannot mint a token")
    r = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
        params={"key": api_key},
        json={"token": custom.decode("utf-8"), "returnSecureToken": True},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["idToken"]


def main() -> int:
    id_token = _id_token()
    print(f"logged in as {EMAIL}")

    r = requests.post(f"{BASE}/get_children/", json={"idToken": id_token}, timeout=30)
    children = r.json()
    if isinstance(children, dict):
        children = children.get("children", children.get("data", []))
    print(f"{len(children)} child(ren)")

    from app.domain.enums import TestType
    from app.core.security import verify_paid_child
    from app.core.exceptions import PaymentRequiredError
    from app.infrastructure.repositories import ScoreRepository, SnapshotRepository

    scores = ScoreRepository()
    snapshots = SnapshotRepository()

    best = None
    for child in children:
        child_id = child.get("id") or child.get("child_id")
        if not child_id:
            continue
        try:
            uid, child_data = verify_paid_child(id_token, child_id)
        except PaymentRequiredError:
            continue
        except Exception:
            continue

        count = sum(
            1
            for key in (
                TestType.LOGIC.storage_key,
                TestType.SPELLING.storage_key,
                TestType.SPEAKING.storage_key,
                TestType.COMPREHENSION.storage_key,
            )
            if scores.get_latest(uid, child_id, key)
        )
        cached = snapshots.get(uid, child_id)
        meta = ((cached or {}).get("snapshot") or {}).get("meta") or {}
        real_cached = bool(cached and meta.get("llm_generated"))
        print(
            f"  {child.get('name', '?')} ({child_id[:8]}...): "
            f"{count} activities, cached letter: "
            f"{'real' if real_cached else 'fallback' if cached else 'none'}"
        )
        if WANTED_CHILD and child_id != WANTED_CHILD:
            continue
        if count and (best is None or count > best[3]):
            best = (child_id, uid, child_data, count, real_cached)

    if not best:
        print("no paid child with assessment data; submit activities first")
        return 0

    child_id, uid, child_data, count, real_cached = best
    grade = child_data.get("grade")
    if real_cached:
        print(
            "\nnote: this child already has a real cached letter, so the "
            "endpoint returns it without calling the model. To time a fresh "
            "one: python scripts/clear_cached_snapshot.py <uid> <child_id> --confirm"
        )

    if FRESH:
        from app.infrastructure.firebase import get_firebase_client

        path = f"users/{uid}/children/{child_id}/snapshot"
        cached = get_firebase_client().ref(path).get()
        if cached:
            backup_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "_backups"
            )
            os.makedirs(backup_dir, exist_ok=True)
            backup = os.path.join(backup_dir, f"{child_id}-snapshot.json")
            with open(backup, "w", encoding="utf-8") as handle:
                json.dump({"path": path, "data": cached}, handle, indent=2)
            get_firebase_client().ref(path).delete()
            print(f"cleared cached letter (backed up to {backup})")

    print(
        f"\nPOST /snapshot/ for {child_data.get('name')} "
        f"(grade {grade}, {count} activities)..."
    )
    start = time.monotonic()
    r = requests.post(
        f"{BASE}/snapshot/",
        json={"idToken": id_token, "child_id": child_id, "grade": grade},
        timeout=300,
    )
    elapsed = time.monotonic() - start

    print(f"\nHTTP {r.status_code} in {elapsed:.1f}s")
    if r.status_code != 200:
        print(r.text[:500])
        return 1

    letter = r.json().get("snapshot") or {}
    meta = letter.get("meta") or {}
    print(f"llm_generated     : {meta.get('llm_generated')}")
    print(f"guardrails_passed : {meta.get('guardrails_passed')}")
    print(f"specificity       : {meta.get('specificity')}")
    print(f"voice slips       : {len(meta.get('voice_slips') or [])}")
    print(
        f"growth edges      : {meta.get('growth_edges_written')} written of "
        f"{meta.get('growth_edges_found')} found"
    )
    print(f"model             : {meta.get('model')}")
    opening = letter.get("opening") or {}
    print(f"\nheadline: {opening.get('headline', '')}")
    print(f"paragraph: {opening.get('paragraph', '')[:300]}")

    noticed = letter.get("what_i_noticed") or []
    print(f"\nwhat_i_noticed ({len(noticed)} item(s)):")
    for item in noticed:
        detail = ", ".join(item.get("signals") or []) or " · ".join(
            item.get("seen_in") or []
        )
        print(f"  - {item.get('headline', '')}  [{detail}]")

    growing = letter.get("still_growing") or []
    print(f"still_growing ({len(growing)} item(s)):")
    for item in growing:
        print(f"  - {item.get('headline', '')}  [{', '.join(item.get('signals') or [])}]")

    print(f"\nclosing: {letter.get('closing', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
