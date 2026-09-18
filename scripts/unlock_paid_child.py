"""Unlock a child whose parent paid but whose entitlement was lost.

`payment_status: "paid"` lives on the child record, so deleting a child
throws away what the parent bought (see TODO.md #1). The payment record
survives, but nothing reads it to restore access, and there is no admin
endpoint for this. Until that is fixed properly, this is the repair.

It writes three fields and nothing else:

    payment_status        -> "paid"
    paid_at               -> now
    unlocked_from_payment -> the payment this honours

The payment record itself is left alone. It is the audit trail of what
Stripe actually did, and rewriting it would erase the evidence that this
went wrong.

Usage - prints the record and exits, writing nothing::

    python scripts/unlock_paid_child.py <uid> <child_id> <payment_id>

Add ``--confirm`` to write. The record is backed up to
``scripts/_backups/`` first either way (gitignored - it holds one parent's
child, by name, and belongs on the machine that made the repair rather than
in the project history).

The case this was written for: a parent paid on a live Stripe session for a
child; that child was deleted and re-added, so the child on the account now
is the same one with a new id and no entitlement. Look up the three ids from
``payments/`` and the parent's ``users/{uid}/children`` before running this,
then::

    python scripts/unlock_paid_child.py <uid> <child_id> <payment_id> --confirm
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app.infrastructure.firebase import get_firebase_client

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_backups")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    confirm = "--confirm" in sys.argv
    if len(args) != 3:
        print(__doc__)
        return 2
    uid, child_id, payment_id = args

    client = get_firebase_client()
    path = f"users/{uid}/children/{child_id}"
    ref = client.ref(path)

    before = ref.get()
    print(f"=== {path} ===")
    print(json.dumps(before, indent=2))
    if before is None:
        print("\nABORT: no such child. Nothing written.")
        return 1

    # Check the payment really is this parent's, and really was completed.
    # Unlocking against a payment that was never made is the opposite
    # mistake and just as easy to make by hand.
    payment = client.ref(f"payments/{payment_id}").get()
    if not payment:
        print(f"\nABORT: payment {payment_id} not found. Nothing written.")
        return 1
    if payment.get("parent_uid") != uid:
        print("\nABORT: that payment belongs to a different parent. Nothing written.")
        return 1
    if payment.get("status") != "completed":
        print(f"\nABORT: payment status is {payment.get('status')!r}, not "
              "'completed'. Nothing written.")
        return 1
    print(f"\npayment {payment_id}: {payment.get('amount_cents')} "
          f"{payment.get('currency')} completed {payment.get('completed_at')}")
    print(f"  paid for: {payment.get('items')}")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup = os.path.join(BACKUP_DIR, f"{child_id}.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump({"path": path, "data": before}, f, indent=2)
    print(f"\nbacked up to {backup}")

    if before.get("payment_status") == "paid":
        print("\nAlready paid. Nothing to do.")
        return 0

    if not confirm:
        print("\nDry run. Re-run with --confirm to write:")
        print('  payment_status        -> "paid"')
        print("  paid_at               -> now")
        print(f'  unlocked_from_payment -> "{payment_id}"')
        return 0

    ref.update({
        "payment_status": "paid",
        "paid_at": datetime.now(timezone.utc).isoformat(),
        "unlocked_from_payment": payment_id,
    })

    after = ref.get()
    print("\n=== AFTER ===")
    for key in sorted(set(before) | set(after)):
        b = before.get(key, "<absent>")
        a = after.get(key, "<absent>")
        mark = "" if b == a else "   <== CHANGED"
        print(f"  {key:22s} {str(b):30s} -> {a}{mark}")

    unlocked = after.get("payment_status") == "paid"
    print(f"\ntests and snapshot: {'UNLOCKED' if unlocked else 'STILL BLOCKED'}")
    return 0 if unlocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
