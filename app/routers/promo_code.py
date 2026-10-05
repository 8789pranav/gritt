"""Promo code endpoints: admin generation/listing and parent redemption."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import (
    GeneratePromoCodesRequest,
    ListPromoCodesRequest,
    RedeemPromoCodeRequest,
)
from app.services.promo_code_service import PromoCodeService

router = APIRouter(tags=["promo-codes"])


@router.post("/admin/promo-codes/generate/")
async def generate_promo_codes(request: GeneratePromoCodesRequest):
    svc = PromoCodeService()
    return svc.generate(request.idToken, request.count)


@router.post("/admin/promo-codes/list/")
async def list_promo_codes(request: ListPromoCodesRequest):
    svc = PromoCodeService()
    return svc.list_codes(request.idToken)


@router.post("/promo-codes/redeem/")
async def redeem_promo_code(request: RedeemPromoCodeRequest):
    svc = PromoCodeService()
    return svc.redeem(request.idToken, request.code, request.child_id)
