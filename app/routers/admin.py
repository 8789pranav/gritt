"""Admin endpoints: stats, feedback, audio pre-generation, user management."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.schemas import (
    FeedbackRequest,
    GetDetailsRequest,
    MakeAdminRequest,
)
from app.services.admin_service import AdminService

router = APIRouter(tags=["admin"])


@router.post("/admin/make-admin/")
async def make_admin(request: MakeAdminRequest):
    svc = AdminService()
    return svc.make_admin(request.idToken, request.targetEmail)


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
    answers = {
        "q1_grade": feedback.q1_grade,
        "q2_prior_assessments": feedback.q2_prior_assessments,
        "q3_spelling_confidence": feedback.q3_spelling_confidence,
        "q4_assessment_length": feedback.q4_assessment_length,
        "q5_difficulty_level": feedback.q5_difficulty_level,
        "q6_engagement_level": feedback.q6_engagement_level,
        "q7_technical_issues": feedback.q7_technical_issues,
        "q8_results_clarity": feedback.q8_results_clarity,
        "q9_recommendations_helpful": feedback.q9_recommendations_helpful,
        "q10_information_amount": feedback.q10_information_amount,
        "q11_overall_satisfaction": feedback.q11_overall_satisfaction,
        "q12_comments": feedback.q12_comments or "",
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
