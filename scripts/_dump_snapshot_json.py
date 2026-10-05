"""Print the complete cached snapshot JSON for a child.

Usage:
  python scripts/_dump_snapshot_json.py --uid <uid> "child name"
  python scripts/_dump_snapshot_json.py --uid <uid> --child-id <child_id>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firebase_admin import auth as firebase_auth
from app.infrastructure.firebase import get_firebase_client


def parse_args(argv):
    name = "new hrms"
    uid = None
    child_id = None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--uid" and i + 1 < len(argv):
            uid = argv[i + 1]
            i += 2
        elif a == "--child-id" and i + 1 < len(argv):
            child_id = argv[i + 1]
            i += 2
        elif not a.startswith("--"):
            name = a
            i += 1
        else:
            i += 1
    return name, uid, child_id


NAME, UID_ARG, CHILD_ID_ARG = parse_args(sys.argv)

client = get_firebase_client()

if UID_ARG:
    uid = UID_ARG
    user = firebase_auth.get_user(uid)
elif EMAIL := os.getenv("SNAPSHOT_EMAIL"):
    uid = firebase_auth.get_user_by_email(EMAIL).uid
else:
    print("need --uid or SNAPSHOT_EMAIL env")
    sys.exit(1)

if not CHILD_ID_ARG:
    children = client.ref(f"users/{uid}/children").get() or {}
    for cid, child in children.items():
        if (child or {}).get("name", "").strip().lower() == NAME.lower():
            CHILD_ID_ARG = cid
            break

if not CHILD_ID_ARG:
    print(f"child '{NAME}' not found")
    sys.exit(1)

saved = client.ref(f"users/{uid}/children/{CHILD_ID_ARG}/snapshot").get()
if not saved:
    print("no saved snapshot for this child")
    sys.exit(1)

print(json.dumps(saved, indent=2, ensure_ascii=False))
