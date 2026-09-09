"""Run the snapshot pipeline against REAL data from Firebase.

1. Logs in via the deployed API to get a real id_token.
2. Lists the children on the account so we can pick one with data.
3. Runs the local snapshot service against the real Firebase.
"""
import sys
sys.path.insert(0, "Z:/grittt")

import json
import requests

BASE = "https://nvupmmyd66.us-east-1.awsapprunner.com"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else "Test@123"

# ---------------------------------------------------------------------
# 1. Login
# ---------------------------------------------------------------------
print("Logging in...")
r = requests.post(f"{BASE}/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Login failed: {r.status_code} {r.text[:300]}")
    sys.exit(1)

data = r.json()
id_token = data.get("id_token") or data.get("token") or data.get("idToken")
print(f"Logged in. Token: {id_token[:20]}...")

# ---------------------------------------------------------------------
# 2. List children
# ---------------------------------------------------------------------
print("\nFetching children...")
r = requests.post(f"{BASE}/get_children/", json={"idToken": id_token}, timeout=30)
children = r.json() if r.status_code == 200 else []
if isinstance(children, dict):
    children = children.get("children", children.get("data", []))

print(f"\nFound {len(children)} child(ren):")
for i, child in enumerate(children):
    print(f"  [{i}] id={child.get('id', child.get('child_id', '?'))} "
          f"name={child.get('name', '?')} "
          f"grade={child.get('grade', '?')}")

# ---------------------------------------------------------------------
# 3. Check which tests have data for the first child
# ---------------------------------------------------------------------
if children:
    first = children[0]
    child_id = first.get("id") or first.get("child_id")
    print(f"\nChecking stored tests for {first.get('name', 'child')} ({child_id})...")

    from app.services.snapshot_service import SnapshotService
    svc = SnapshotService()

    # Peek at what is stored before generating.
    from app.core.security import verify_paid_child
    uid, child_data = verify_paid_child(id_token, child_id)
    print(f"  uid: {uid}")
    print(f"  child: {child_data.get('name', '?')}, grade: {child_data.get('grade', '?')}")

    from app.domain.enums import TestType
    for name, key in [
        ("logic", TestType.LOGIC.storage_key),
        ("spelling", TestType.SPELLING.storage_key),
        ("speaking", TestType.SPEAKING.storage_key),
        ("comprehension", TestType.COMPREHENSION.storage_key),
    ]:
        latest = svc._scores.get_latest(uid, child_id, key)
        if latest:
            tags = latest.get("dear_parent_tags", [])
            tag_ids = [t.get("id", t.get("tag", "")) for t in tags]
            print(f"  {name}: HAS DATA ({len(tags)} tags: {tag_ids[:5]}...)")
        else:
            print(f"  {name}: no data")
