"""Payment service: Stripe Checkout for unlocking child assessments.

Pricing rule (single source of truth):
    * the first child a parent ever pays for costs ``first_child_price_cents``
    * every child after that (same or later purchase) costs
      ``additional_child_price_cents``

Children are only ever marked ``paid`` from the Stripe webhook (or the
idempotent fallback in :meth:`PaymentService.get_status` that retrieves the
session directly from Stripe), never from a client redirect.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.exceptions import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from app.core.security import verify_token
from app.infrastructure.repositories import (
    ChildRepository,
    PaymentRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


class PaymentService:
    """Quotes, Stripe Checkout sessions, webhook processing, and status."""

    def __init__(self) -> None:
        from app.infrastructure.firebase import get_firebase_client

        self._client = get_firebase_client()
        self._children = ChildRepository(self._client)
        self._payments = PaymentRepository(self._client)
        self._users = UserRepository(self._client)
        self._settings = get_settings()

    # -- helpers -------------------------------------------------------------
    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _stripe(self):
        import stripe

        if not self._settings.stripe.is_configured:
            raise ValidationError("Payments are not configured on the server")
        stripe.api_key = self._settings.stripe.secret_key
        return stripe

    def _lifetime_paid_count(self, uid: str) -> int:
        """Number of children this parent has ever paid for.

        Uses the counter maintained by the webhook; falls back to counting
        currently-paid children (covers accounts unlocked manually).
        """
        user_data = self._users.get(uid) or {}
        counter = user_data.get("lifetime_paid_children")
        if isinstance(counter, int):
            return counter
        children = self._children.list(uid)
        return sum(
            1 for c in children.values() if c.get("payment_status") == "paid"
        )

    def _validate_children(self, uid: str, child_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not child_ids:
            raise ValidationError("No children selected")
        if len(set(child_ids)) != len(child_ids):
            raise ValidationError("Duplicate children in selection")
        result: Dict[str, Dict[str, Any]] = {}
        for child_id in child_ids:
            child = self._children.get(uid, child_id)
            if not child:
                raise NotFoundError(f"Child {child_id} not found")
            if child.get("payment_status") == "paid":
                raise ValidationError(
                    f"Child {child.get('name', child_id)} is already unlocked"
                )
            result[child_id] = child
        return result

    def _price_items(
        self, uid: str, children: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        stripe_cfg = self._settings.stripe
        paid_count = self._lifetime_paid_count(uid)
        items = []
        for child_id, child in children.items():
            amount = (
                stripe_cfg.first_child_price_cents
                if paid_count == 0
                else stripe_cfg.additional_child_price_cents
            )
            paid_count += 1
            items.append(
                {
                    "child_id": child_id,
                    "name": child.get("name", ""),
                    "grade": child.get("grade", ""),
                    "amount_cents": amount,
                }
            )
        return items

    def _validate_redirect_url(self, url: str, label: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValidationError(f"Invalid {label}")
        allowed = self._settings.stripe.allowed_redirect_origins
        if allowed:
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in allowed:
                raise ValidationError(f"{label} origin is not allowed")

    # -- public API ------------------------------------------------------------
    def quote(self, id_token: str, child_ids: List[str]) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        children = self._validate_children(uid, child_ids)
        items = self._price_items(uid, children)
        return {
            "items": items,
            "total_cents": sum(i["amount_cents"] for i in items),
            "currency": self._settings.stripe.currency,
        }

    def create_checkout_session(
        self,
        id_token: str,
        child_ids: List[str],
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        self._validate_redirect_url(success_url, "success_url")
        self._validate_redirect_url(cancel_url, "cancel_url")

        children = self._validate_children(uid, child_ids)
        items = self._price_items(uid, children)
        total_cents = sum(i["amount_cents"] for i in items)
        currency = self._settings.stripe.currency

        stripe = self._stripe()
        payment_id = str(uuid.uuid4())

        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": currency,
                        "unit_amount": item["amount_cents"],
                        "product_data": {
                            "name": f"{item['name']}'s Learning Profile",
                            "description": (
                                "All four assessments plus the full learning "
                                "report. One-time payment."
                            ),
                        },
                    },
                    "quantity": 1,
                }
                for item in items
            ],
            metadata={
                "payment_id": payment_id,
                "parent_uid": uid,
                "child_ids": ",".join(child_ids),
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )

        self._payments.create(
            payment_id,
            {
                "parent_uid": uid,
                "child_ids": child_ids,
                "items": items,
                "amount_cents": total_cents,
                "currency": currency,
                "stripe_session_id": session.id,
                "status": "pending",
                "created_at": self._utc_now(),
            },
        )

        return {"payment_id": payment_id, "checkout_url": session.url}

    # -- webhook ---------------------------------------------------------------
    def handle_webhook(self, payload: bytes, signature: Optional[str]) -> Dict[str, Any]:
        import stripe

        webhook_secret = self._settings.stripe.webhook_secret
        if not webhook_secret:
            raise ValidationError("Stripe webhook secret is not configured")
        try:
            event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
        except Exception as exc:
            logger.warning("Stripe webhook signature verification failed: %s", exc)
            raise AuthorizationError("Invalid webhook signature")

        event_type = event["type"]
        session = event["data"]["object"]

        if event_type == "checkout.session.completed":
            self._complete_payment(session)
        elif event_type == "checkout.session.expired":
            self._expire_payment(session)
        else:
            logger.info("Ignoring Stripe event type %s", event_type)

        return {"received": True}

    def _complete_payment(self, session: Dict[str, Any]) -> None:
        """Idempotently mark the payment completed and unlock its children."""
        payment = self._payments.get_by_session(session["id"])
        if not payment:
            logger.error("No payment record for Stripe session %s", session["id"])
            return
        payment_id = payment.get("payment_id") or session.get("metadata", {}).get(
            "payment_id", ""
        )
        if payment.get("status") == "completed":
            logger.info("Payment %s already completed; skipping", payment_id)
            return

        uid = payment["parent_uid"]
        child_ids = payment.get("child_ids", []) or []
        now = self._utc_now()

        newly_paid = 0
        for child_id in child_ids:
            child = self._children.get(uid, child_id)
            if child is None:
                logger.warning(
                    "Paid child %s no longer exists for uid %s", child_id, uid
                )
                newly_paid += 1  # still counts toward lifetime total
                continue
            if child.get("payment_status") != "paid":
                self._client.ref(f"users/{uid}/children/{child_id}").update(
                    {"payment_status": "paid", "paid_at": now}
                )
                newly_paid += 1

        # Maintain the lifetime counter used by the pricing rule
        user_data = self._users.get(uid) or {}
        counter = user_data.get("lifetime_paid_children")
        base = counter if isinstance(counter, int) else self._lifetime_paid_count(uid) - newly_paid
        self._users.update(uid, {"lifetime_paid_children": max(base, 0) + newly_paid})

        self._payments.update(
            payment_id,
            {"status": "completed", "completed_at": now},
        )
        logger.info(
            "Payment %s completed; unlocked %d child(ren) for uid %s",
            payment_id,
            newly_paid,
            uid,
        )

    def _expire_payment(self, session: Dict[str, Any]) -> None:
        payment = self._payments.get_by_session(session["id"])
        if not payment or payment.get("status") != "pending":
            return
        payment_id = payment.get("payment_id") or session.get("metadata", {}).get(
            "payment_id", ""
        )
        self._payments.update(payment_id, {"status": "expired"})

    # -- status ------------------------------------------------------------------
    def get_status(
        self,
        id_token: str,
        payment_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]

        payment: Optional[Dict[str, Any]] = None
        if payment_id:
            payment = self._payments.get(payment_id)
            if payment is not None:
                payment.setdefault("payment_id", payment_id)
        if payment is None and session_id:
            payment = self._payments.get_by_session(session_id)
        if not payment or payment.get("parent_uid") != uid:
            raise NotFoundError("Payment not found")

        # Fallback for a delayed/missed webhook: ask Stripe directly.
        if payment.get("status") == "pending" and self._settings.stripe.is_configured:
            try:
                stripe = self._stripe()
                session = stripe.checkout.Session.retrieve(
                    payment["stripe_session_id"]
                )
                if session.payment_status == "paid":
                    self._complete_payment({"id": session.id, "metadata": session.metadata or {}})
                    payment = self._payments.get(payment["payment_id"]) or payment
            except Exception as exc:
                logger.warning("Stripe session lookup failed: %s", exc)

        return {
            "payment_id": payment.get("payment_id", payment_id or ""),
            "status": payment.get("status", "pending"),
            "child_ids": payment.get("child_ids", []),
        }
