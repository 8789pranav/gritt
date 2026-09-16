"""Scan all children for one with test data, then generate a real snapshot."""
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
    print(f"Login failed: {r.status_code}")
    sys.exit(1)
id_token = r.json().get("id_token") or r.json().get("token") or r.json().get("idToken")
print("Logged in.")

# ---------------------------------------------------------------------
# 2. List children
# ---------------------------------------------------------------------
r = requests.post(f"{BASE}/get_children/", json={"idToken": id_token}, timeout=30)
children = r.json() if r.status_code == 200 else []
if isinstance(children, dict):
    children = children.get("children", children.get("data", []))
print(f"Found {len(children)} children.")

# ---------------------------------------------------------------------
# 3. Find a child with data (skip unpaid ones)
# ---------------------------------------------------------------------
from app.services.snapshot_service import SnapshotService
from app.core.security import verify_paid_child
from app.core.exceptions import PaymentRequiredError
from app.domain.enums import TestType

svc = SnapshotService()

best_child = None
best_count = 0

for child in children:
    child_id = child.get("id") or child.get("child_id")
    name = child.get("name", "?")
    try:
        uid, child_data = verify_paid_child(id_token, child_id)
    except PaymentRequiredError:
        continue
    except Exception as e:
        continue

    count = 0
    has = []
    for test_name, key in [
        ("logic", TestType.LOGIC.storage_key),
        ("spelling", TestType.SPELLING.storage_key),
        ("speaking", TestType.SPEAKING.storage_key),
        ("comprehension", TestType.COMPREHENSION.storage_key),
    ]:
        latest = svc._scores.get_latest(uid, child_id, key)
        if latest:
            count += 1
            has.append(test_name)

    if count > 0:
        print(f"  {name} ({child_id[:8]}...): {count} tests -> {has}")
        if count > best_count:
            best_count = count
            best_child = (child_id, name, uid)

if not best_child:
    print("\nNo child has any test data. Submitting tests first is required.")
    sys.exit(0)

child_id, name, uid = best_child
print(f"\n=== Best child: {name} ({child_id}) with {best_count} tests ===")

# ---------------------------------------------------------------------
# 4. Generate the snapshot for real
# ---------------------------------------------------------------------
from app.services.snapshot_service import SnapshotService
from app.services.snapshot_writer import SnapshotWriter
from unittest.mock import patch

svc = SnapshotService()

# We already verified the child; patch verify so build_evidence works.
with patch("app.services.snapshot_service.verify_paid_child",
           return_value=(uid, {"name": name})):
    evidence = svc.build_evidence(id_token, child_id, None)

print(f"\nEvidence: {len(evidence['observations'])} strengths, "
      f"{len(evidence['growth_edges'])} growth edges, "
      f"{len(evidence['full_picture_areas'])} areas")

writer = SnapshotWriter()
letter = writer.write(evidence)

response = {
    "success": True,
    "child_id": child_id,
    "child_name": evidence["child_name"],
    "grade": evidence.get("grade"),
    "tests_completed": evidence["tests_completed"],
    "snapshot": letter,
}

print(json.dumps(response, indent=2, ensure_ascii=False))
