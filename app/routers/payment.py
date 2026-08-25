"""Payment endpoints: Stripe Checkout for unlocking child assessments."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas import (
    CreateCheckoutSessionRequest,
    PaymentQuoteRequest,
    PaymentStatusRequest,
)
from app.services.payment_service import PaymentService

router = APIRouter(tags=["payment"])


@router.post("/payment/quote/")
async def payment_quote(request: PaymentQuoteRequest):
    svc = PaymentService()
    return svc.quote(request.idToken, request.child_ids)


@router.post("/payment/create-checkout-session/")
async def create_checkout_session(request: CreateCheckoutSessionRequest):
    svc = PaymentService()
    return svc.create_checkout_session(
        request.idToken,
        request.child_ids,
        request.success_url,
        request.cancel_url,
    )


@router.post("/payment/status/")
async def payment_status(request: PaymentStatusRequest):
    svc = PaymentService()
    return svc.get_status(request.idToken, request.payment_id, request.session_id)


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    svc = PaymentService()
    return svc.handle_webhook(payload, signature)
