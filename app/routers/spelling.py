"""Spelling assessment endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import (
    AudioRequest,
    CompleteResultRequest,
    GradeInput,
    SubmitWordsRequest,
)
from app.services.assessment_service import AssessmentService
from app.services.audio_service import AudioService

router = APIRouter(tags=["spelling"])


@router.post("/grade/")
async def get_grade_words(grade_input: GradeInput):
    svc = AssessmentService()
    return svc.spelling_get_words(grade_input.grade)


@router.post("/submit_words/")
async def submit_words(request: SubmitWordsRequest):
    svc = AssessmentService()
    words = [w.model_dump() for w in request.words]
    return svc.spelling_submit_words(
        request.idToken, request.child_id, request.grade, words
    )


@router.post("/generate_text_audio/")
async def generate_text_audio(request: AudioRequest):
    svc = AudioService()
    return await svc.generate_text_audio(request.idToken, request.text)


@router.post("/generate_all_grade_audio/")
async def generate_all_grade_audio(request: GradeInput):
    svc = AudioService()
    return await svc.generate_all_grade_audio("", request.grade)


@router.post("/complete_result/")
async def complete_result(request: CompleteResultRequest):
    svc = AssessmentService()
    return svc.spelling_complete_result(
        request.idToken, request.child_id, request.grade
    )
