"""Drop a child's cached Learning Snapshot so the next request rewrites it.

A snapshot is generated once and cached, so a parent sees the same wording
every time they open it. When a cached letter is wrong - or is the generic
fallback saved before the writer stopped handing failures back - this clears
it and the next request builds a fresh one.

On the deployed code this is rarely needed: the endpoint already regenerates
a cached letter that is not a real one. It is for the cases that guard does
not cover - a letter that is real but wrong, or a record that predates the
guard reaching production.

Usage - prints what is cached and exits, writing nothing::

    python scripts/clear_cached_snapshot.py <uid> <child_id>

Add ``--confirm`` to delete. The letter is backed up to ``scripts/_backups/``
first either way, so it can be put back by hand if that turns out to be
wrong.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app.infrastructure.firebase import get_firebase_client

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_backups")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    confirm = "--confirm" in sys.argv
    if len(args) != 2:
        print(__doc__)
        return 2
    uid, child_id = args

    client = get_firebase_client()
    path = f"users/{uid}/children/{child_id}/snapshot"
    ref = client.ref(path)

    child = client.ref(f"users/{uid}/children/{child_id}").get()
    if not child:
        print(f"ABORT: no child at users/{uid}/children/{child_id}")
        return 1
    print(f"child   : {child.get('name')!r}  grade={child.get('grade')!r}  "
          f"paid={child.get('payment_status')!r}")

    cached = ref.get()
    if not cached:
        print("\nNothing cached. The next request already writes a fresh letter.")
        return 0

    letter = cached.get("snapshot") or {}
    meta = letter.get("meta") or {}
    print(f"cached  : llm_generated={meta.get('llm_generated')} "
          f"guardrails_passed={meta.get('guardrails_passed')} "
          f"specificity={meta.get('specificity')}")
    print(f"          growth edges {meta.get('growth_edges_written')} written "
          f"of {meta.get('growth_edges_found')} found")
    print(f"          sections: {sorted(k for k in letter if k != 'meta')}")
    if not meta.get("llm_generated"):
        print("          ^ this is the generic fallback: a letter about nobody")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup = os.path.join(BACKUP_DIR, f"{child_id}-snapshot.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump({"path": path, "data": cached}, f, indent=2)
    print(f"\nbacked up to {backup}")

    if not confirm:
        print("\nDry run. Re-run with --confirm to delete it.")
        print("The next request to /snapshot/ will then write a new letter.")
        return 0

    ref.delete()

    if ref.get():
        print("\nFAILED: the letter is still there.")
        return 1
    print("\nDeleted. The next request to /snapshot/ writes a fresh letter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
