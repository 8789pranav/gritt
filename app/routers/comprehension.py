"""Reading comprehension (Story Explorer) endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import (
    ComprehensionGetRequest,
    ComprehensionResultRequest,
    ComprehensionSubmitRequest,
)
from app.services.assessment_service import AssessmentService
from app.services.audio_service import AudioService

router = APIRouter(tags=["comprehension"])


@router.post("/comprehension/get_stories/")
async def get_comprehension_stories(request: ComprehensionGetRequest):
    svc = AudioService()
    return await svc.get_comprehension_stories(
        request.idToken, request.child_id, request.grade
    )


@router.post("/comprehension/submit/")
async def submit_comprehension_test(request: ComprehensionSubmitRequest):
    svc = AssessmentService()
    story_answers = [sa.model_dump() for sa in request.story_answers]
    return svc.comprehension_submit(
        request.idToken, request.child_id, request.grade, story_answers
    )


@router.post("/comprehension/complete_result/")
async def comprehension_complete_result(request: ComprehensionResultRequest):
    svc = AssessmentService()
    return svc.comprehension_complete_result(
        request.idToken, request.child_id, request.grade
    )
