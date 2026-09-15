"""Admin endpoints: stats, feedback, audio pre-generation, user management."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.schemas import (
    FeedbackRequest,
    GetDetailsRequest,
    MakeAdminRequest,
    SetBypassPaymentRequest,
)
from app.services.admin_service import AdminService

router = APIRouter(tags=["admin"])


@router.post("/admin/make-admin/")
async def make_admin(request: MakeAdminRequest):
    svc = AdminService()
    return svc.make_admin(request.idToken, request.targetEmail)


@router.post("/admin/bypass-payment/")
async def get_bypass_payment(request: GetDetailsRequest):
    svc = AdminService()
    return svc.get_bypass_payment(request.idToken)


@router.post("/admin/bypass-payment/set/")
async def set_bypass_payment(request: SetBypassPaymentRequest):
    svc = AdminService()
    return svc.set_bypass_payment(request.idToken, request.enabled)


@router.post("/admin/stats/")
async def get_admin_stats(request: GetDetailsRequest):
    svc = AdminService()
    return svc.get_stats(request.idToken)


@router.post("/admin/feedback/")
async def get_all_feedback(request: GetDetailsRequest):
    svc = AdminService()
    return svc.get_all_feedback(request.idToken)


@router.post("/feedback/")
async def submit_feedback(feedback: FeedbackRequest):
    svc = AdminService()
    # Only what the parent actually answered is stored, so a record is not
    # padded with blanks for questions the form no longer asks.
    answers = {
        key: value
        for key, value in feedback.model_dump(exclude={"idToken", "child_id"}).items()
        if value
    }
    return svc.submit_feedback(feedback.idToken, feedback.child_id, answers)


@router.post("/admin/pregenerate_spelling_audio/")
async def pregenerate_spelling_audio(request: GetDetailsRequest):
    svc = AdminService()
    return await svc.pregenerate_spelling_audio(request.idToken)


@router.post("/admin/pregenerate_story_audio/")
async def pregenerate_story_audio(request: GetDetailsRequest):
    svc = AdminService()
    return await svc.pregenerate_story_audio(request.idToken)


@router.post("/admin/regenerate_story_audio/")
async def regenerate_story_audio(
    request: GetDetailsRequest,
    grade: Optional[str] = Query(None),
    story_id: Optional[str] = Query(None),
):
    svc = AdminService()
    return await svc.regenerate_story_audio(request.idToken, grade, story_id)
