"""Promo code service: admin-generated single-use codes that unlock one
child without payment.

Rules:
    * Only admins can generate and list promo codes.
    * A code can be redeemed exactly once; after redemption its status
      becomes ``"used"`` and it can never be used again.
    * One code unlocks exactly one child for the parent who redeems it.
    * Every generation and redemption is recorded for audit.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import verify_admin, verify_token
from app.infrastructure.repositories import (
    ChildRepository,
    PromoCodeRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)

# Codes look like ``DPP-AB7C-9KQ2``: a fixed prefix, two groups of four
# unambiguous characters (no 0/O/1/I to avoid confusion).
_CODE_ALPHABET = "".join(
    c for c in (string.ascii_uppercase + string.digits)
    if c not in "0OI1"
)
_CODE_PREFIX = "DPP"
_MAX_GENERATE = 500


def _generate_code() -> str:
    group1 = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
    group2 = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
    return f"{_CODE_PREFIX}-{group1}-{group2}"


def _normalize_code(code: str) -> str:
    return code.strip().upper()


class PromoCodeService:
    """Generate, list, and redeem single-use promo codes."""

    def __init__(self) -> None:
        from app.infrastructure.firebase import get_firebase_client

        self._client = get_firebase_client()
        self._codes = PromoCodeRepository(self._client)
        self._children = ChildRepository(self._client)
        self._users = UserRepository(self._client)

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- admin: generate ----------------------------------------------------
    def generate(self, id_token: str, count: int) -> Dict[str, Any]:
        admin_uid = verify_admin(id_token)
        if count < 1:
            raise ValidationError("count must be at least 1")
        if count > _MAX_GENERATE:
            raise ValidationError(f"count must be at most {_MAX_GENERATE}")

        now = self._utc_now()
        batch_id = secrets.token_hex(8)
        created: List[str] = []
        # Guard against (astronomically unlikely) collisions.
        seen: set[str] = set()
        attempts = 0
        while len(created) < count:
            attempts += 1
            code = _generate_code()
            if code in seen or self._codes.get(code):
                if attempts > count * 20:
                    raise ValidationError("Could not generate unique codes; retry")
                continue
            seen.add(code)
            self._codes.create(code, {
                "code": code,
                "status": "active",
                "created_by": admin_uid,
                "created_at": now,
                "batch_id": batch_id,
            })
            created.append(code)

        logger.info(
            "Admin %s generated %d promo codes (batch %s)",
            admin_uid, len(created), batch_id,
        )
        return {
            "success": True,
            "count": len(created),
            "batch_id": batch_id,
            "codes": created,
        }

    # -- admin: list --------------------------------------------------------
    def list_codes(self, id_token: str) -> Dict[str, Any]:
        verify_admin(id_token)
        all_codes = self._codes.get_all()
        items: List[Dict[str, Any]] = []
        for code_key, data in all_codes.items():
            items.append({
                "code": data.get("code", code_key),
                "status": data.get("status", "active"),
                "created_by": data.get("created_by", ""),
                "created_at": data.get("created_at", ""),
                "batch_id": data.get("batch_id", ""),
                "used_by": data.get("used_by", ""),
                "used_for_child": data.get("used_for_child", ""),
                "used_at": data.get("used_at", ""),
            })
        # Newest first; codes without created_at sort last.
        items.sort(key=lambda i: i.get("created_at") or "", reverse=True)

        active = sum(1 for i in items if i["status"] == "active")
        used = sum(1 for i in items if i["status"] == "used")
        return {
            "total": len(items),
            "active": active,
            "used": used,
            "codes": items,
        }

    # -- parent: redeem -----------------------------------------------------
    def redeem(self, id_token: str, code: str, child_id: str) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]

        if not code or not child_id:
            raise ValidationError("code and child_id are required")

        normalized = _normalize_code(code)
        record = self._codes.get(normalized)
        if not record:
            raise NotFoundError("Promo code not found")

        if record.get("status") != "active":
            raise ValidationError("This promo code has already been used or is no longer valid")

        # Validate the child belongs to this parent and is not already unlocked.
        child = self._children.get(uid, child_id)
        if not child:
            raise NotFoundError("Child not found")
        if child.get("payment_status") == "paid":
            raise ValidationError(
                f"{child.get('name', 'This child')} is already unlocked"
            )

        now = self._utc_now()

        # Claim the code first (check-then-write, mirroring the payment
        # webhook's idempotency guard). Re-read to be safe against a race.
        record = self._codes.get(normalized)
        if not record or record.get("status") != "active":
            raise ValidationError("This promo code has already been used or is no longer valid")
        self._codes.update(normalized, {
            "status": "used",
            "used_by": uid,
            "used_for_child": child_id,
            "used_at": now,
        })

        # Unlock the child, mirroring the Stripe webhook's _complete_payment.
        self._client.ref(f"users/{uid}/children/{child_id}").update({
            "payment_status": "paid",
            "paid_at": now,
            "paid_via": "promo_code",
            "promo_code": normalized,
        })

        # Keep the lifetime-paid counter consistent with the pricing rule.
        user_data = self._users.get(uid) or {}
        counter = user_data.get("lifetime_paid_children")
        base = counter if isinstance(counter, int) else self._lifetime_paid_count(uid) - 1
        self._users.update(uid, {"lifetime_paid_children": max(base, 0) + 1})

        logger.info(
            "Promo code %s redeemed by uid %s for child %s",
            normalized, uid, child_id,
        )
        return {
            "success": True,
            "message": "Child unlocked successfully",
            "code": normalized,
            "child_id": child_id,
            "child_name": child.get("name", ""),
        }

    def _lifetime_paid_count(self, uid: str) -> int:
        user_data = self._users.get(uid) or {}
        counter = user_data.get("lifetime_paid_children")
        if isinstance(counter, int):
            return counter
        children = self._children.list(uid)
        return sum(
            1 for c in children.values() if c.get("payment_status") == "paid"
        )
