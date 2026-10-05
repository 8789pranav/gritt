"""Inspect the evidence package for a named child.

Usage:
  python scripts/_inspect_child_evidence.py "child name" --uid <firebase_uid>
  python scripts/_inspect_child_evidence.py "child name" --token <idToken>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firebase_admin import auth as firebase_auth
from app.infrastructure.firebase import get_firebase_client
from app.services.snapshot_service import SnapshotService


def parse_args(argv):
    name = "new hrms"
    uid = None
    token = None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--uid" and i + 1 < len(argv):
            uid = argv[i + 1]
            i += 2
        elif a == "--token" and i + 1 < len(argv):
            token = argv[i + 1]
            i += 2
        elif not a.startswith("--"):
            name = a
            i += 1
        else:
            i += 1
    return name, uid, token


TARGET, UID_ARG, TOKEN_ARG = parse_args(sys.argv)

client = get_firebase_client()
if UID_ARG:
    uid = UID_ARG
    user = firebase_auth.get_user(uid)
    print(f"uid: {uid}  email: {user.email or '?'}")
elif TOKEN_ARG:
    decoded = firebase_auth.verify_id_token(TOKEN_ARG)
    uid = decoded["uid"]
    print(f"uid: {uid}  email: {decoded.get('email', '?')}")
else:
    print("need --uid or --token")
    sys.exit(1)

children = client.ref(f"users/{uid}/children").get() or {}
print(f"children: {len(children)}")

for child_id, child in children.items():
    if (child or {}).get("name", "").strip().lower() == TARGET.lower():
        print(f"\nchild_id : {child_id}")
        print(f"name     : {child.get('name')}")
        print(f"grade    : {child.get('grade')}")

        svc = SnapshotService()
        evidence = svc.build_evidence("", child_id, uid=uid, child_data=child)

        print("\nstrengths            :", len(evidence.get("strengths") or []))
        print("neutral_observations :", len(evidence.get("neutral_observations") or []))
        print("flawless_activities  :", len(evidence.get("flawless_activities") or []))
        print("kept_at_it           :", len(evidence.get("kept_at_it") or []))
        print("growth_edges         :", len(evidence.get("growth_edges") or []))
        print("growth_clusters      :", len(evidence.get("growth_clusters") or []))

        print("\nwhat_the_child_did keys:", list(evidence.get("what_the_child_did", {}).keys()))
        print("could_mention keys:", list(evidence.get("could_mention", {}).keys()))

        print("\nfirst 5 strengths:")
        for s in (evidence.get("strengths") or [])[:5]:
            print("  -", s.get("signal_name"), "in", s.get("seen_in"))

        print("\nfirst 5 neutral observations:")
        for s in (evidence.get("neutral_observations") or [])[:5]:
            print("  -", s.get("signal_name"), "in", s.get("seen_in"))

        print("\nfirst 5 growth edges:")
        for g in (evidence.get("growth_edges") or [])[:5]:
            print("  -", g.get("signal_name"), "in", g.get("seen_in"))

        print("\nflawless activities:")
        for f in (evidence.get("flawless_activities") or []):
            print("  -", f.get("activity"), ":", (f.get("nothing_to_fault") or "")[:80])

        print("\nkept_at_it:")
        for k in (evidence.get("kept_at_it") or []):
            print("  -", k.get("activity"), ":", (k.get("what") or "")[:80])

        print("\ncould_mention sample:")
        cm = evidence.get("could_mention") or {}
        for key in list(cm.keys())[:8]:
            val = cm[key]
            snippet = json.dumps(val, ensure_ascii=False)[:180]
            print(f"  {key}: {snippet}...")
        break
else:
    print(f"child '{TARGET}' not found")
    names = sorted({(c or {}).get("name", "?") for c in children.values()})
    print("available:", names)
