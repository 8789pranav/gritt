"""Print a child's saved Learning Snapshot the way a parent reads it.

Reads the cached letter straight from Firebase - no model call, no
regeneration. Usage::

    python scripts/print_snapshot.py [child_id]

Without a child_id, prints the first child of the parent account that has
a saved letter.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EMAIL = os.environ.get("SNAPSHOT_EMAIL", "rajdandeepak@gmail.com")


def main() -> int:
    from firebase_admin import auth as firebase_auth

    from app.infrastructure.firebase import get_firebase_client

    client = get_firebase_client()
    user = firebase_auth.get_user_by_email(EMAIL)
    uid = user.uid

    children = client.ref(f"users/{uid}/children").get() or {}
    child_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not child_id:
        child_id = next(
            (cid for cid, data in children.items() if data.get("snapshot")),
            None,
        )
    if not child_id or child_id not in children:
        print("no child with a saved letter found")
        return 1

    child = children[child_id]
    record = (child.get("snapshot") or {}).get("snapshot") or {}
    if not record:
        print(f"{child.get('name', 'this child')} has no saved letter")
        return 0

    name = child.get("name", "your child")
    line = "=" * 72
    print(line)
    print(f"  LEARNING SNAPSHOT - {name}")
    print(line)

    opening = record.get("opening") or {}
    print(f"\n{record.get('salutation', 'Dear Parent,')}\n")
    print(opening.get("headline", ""))
    print()
    print(opening.get("paragraph", ""))

    noticed = record.get("what_i_noticed") or []
    if noticed:
        print("\nWHAT I NOTICED")
        for item in noticed:
            print(f"\n  {item.get('headline', '')}")
            print(f"  {item.get('paragraph', '')}")

    growing = record.get("still_growing") or []
    if growing:
        print("\nSTILL GROWING")
        for item in growing:
            print(f"\n  {item.get('headline', '')}")
            print(f"  {item.get('paragraph', '')}")
            suggestion = item.get("suggestion") or {}
            if suggestion.get("title"):
                print(f"  Try at home: {suggestion['title']}")
            if suggestion.get("body"):
                print(f"  {suggestion['body']}")

    level = record.get("level_note")
    if level and (level.get("headline") or level.get("paragraph")):
        print("\nA NOTE ON THE LEVEL")
        print(f"\n  {level.get('headline', '')}")
        print(f"  {level.get('paragraph', '')}")

    conference = (record.get("for_the_conference") or {}).get("items") or []
    if conference:
        print("\nFOR THE CONFERENCE")
        for item in conference:
            print(f"\n  {item.get('point', '')}")
            print(f"  Worth asking: {item.get('worth_asking', '')}")

    print(f"\n{record.get('closing', '')}")
    print(f"\n{record.get('signature', '')}")

    meta = record.get("meta") or {}
    print(f"\n{line}")
    print(
        f"  llm_generated={meta.get('llm_generated')}  "
        f"specificity={meta.get('specificity')}  "
        f"voice_slips={len(meta.get('voice_slips') or [])}  "
        f"growth_edges={meta.get('growth_edges_written')}/"
        f"{meta.get('growth_edges_found')}  model={meta.get('model')}"
    )
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
