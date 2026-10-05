"""Check the cached snapshot for a child and optionally regenerate it."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from firebase_admin import auth as firebase_auth
from app.infrastructure.firebase import get_firebase_client
from app.core.config import get_settings

BASE = "http://127.0.0.1:8000"
EMAIL = "pranavkaushlic@gmail.com"


def _user_and_token():
    get_firebase_client()
    user = firebase_auth.get_user_by_email(EMAIL)
    r = requests.post(f"{BASE}/login", json={"email": EMAIL, "password": "dummy"}, timeout=15)
    if r.status_code == 200:
        body = r.json()
        return user, body.get("id_token") or body.get("token") or body.get("idToken")

    custom = firebase_auth.create_custom_token(user.uid)
    api_key = get_settings().firebase.api_key
    r = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
        params={"key": api_key},
        json={"token": custom.decode("utf-8"), "returnSecureToken": True},
        timeout=30,
    )
    r.raise_for_status()
    return user, r.json()["idToken"]


def main() -> int:
    child_name = sys.argv[1] if len(sys.argv) > 1 else "new hrms"
    user, token = _user_and_token()

    r = requests.post(f"{BASE}/get_children/", json={"idToken": token}, timeout=30)
    children = r.json()
    if isinstance(children, dict):
        children = children.get("children", children.get("data", []))

    target = None
    for c in children:
        if c.get("name", "").strip().lower() == child_name.lower():
            target = c
            break
    if not target:
        print(f"child '{child_name}' not found")
        return 1

    child_id = target.get("id") or target.get("child_id")
    grade = target.get("grade")
    print(f"child_id: {child_id}  name: {target.get('name')}  grade: {grade}")

    # check current cached snapshot
    r = requests.post(f"{BASE}/snapshot/", json={"idToken": token, "child_id": child_id, "grade": grade}, timeout=60)
    if r.status_code != 200:
        print(f"snapshot failed: {r.status_code} {r.text[:300]}")
        return 1
    body = r.json()
    letter = body.get("snapshot") or {}
    meta = letter.get("meta") or {}
    noticed = letter.get("what_i_noticed") or []
    growing = letter.get("still_growing") or []
    print("\n[CACHED / RETURNED LETTER]")
    print(f"llm_generated     : {meta.get('llm_generated')}")
    print(f"model             : {meta.get('model')}")
    print(f"prompt_version    : {meta.get('prompt_version')}")
    print(f"specificity       : {meta.get('specificity')}")
    print(f"guardrails_passed : {meta.get('guardrails_passed')}")
    print(f"voice slips       : {len(meta.get('voice_slips') or [])}")
    print(f"noticed count     : {len(noticed)}")
    print(f"growing count     : {len(growing)}")
    for item in noticed:
        print("  noticed:", item.get("headline"), "|", item.get("area_display_name"))

    if len(noticed) < 4 or not meta.get("llm_generated"):
        print("\n[REGENERATING FRESH...]")
        # clear cache
        client = get_firebase_client()
        path = f"users/{user.uid}/children/{child_id}/snapshot"
        client.ref(path).delete()
        print("cleared cached snapshot")

        start = time.monotonic()
        r = requests.post(f"{BASE}/snapshot/", json={"idToken": token, "child_id": child_id, "grade": grade}, timeout=300)
        elapsed = time.monotonic() - start
        print(f"regenerated in {elapsed:.1f}s status={r.status_code}")
        if r.status_code != 200:
            print(r.text[:500])
            return 1
        body = r.json()
        letter = body.get("snapshot") or {}
        meta = letter.get("meta") or {}
        noticed = letter.get("what_i_noticed") or []
        growing = letter.get("still_growing") or []
        print(f"llm_generated  : {meta.get('llm_generated')}")
        print(f"model          : {meta.get('model')}")
        print(f"prompt_version : {meta.get('prompt_version')}")
        print(f"specificity    : {meta.get('specificity')}")
        print(f"noticed count  : {len(noticed)}")
        print(f"growing count  : {len(growing)}")
        for item in noticed:
            print("  noticed:", item.get("headline"), "|", item.get("area_display_name"))
        for item in growing:
            print("  growing:", item.get("headline"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
