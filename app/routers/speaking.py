"""Speaking (Voice Challenge) assessment endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import (
    GetDetailsRequest,
    SpeakingAnalyzeRequest,
    SpeakingSentenceRequest,
    SpeakingSubmitRequest,
    SpeakingResultRequest,
)
from app.services.admin_service import AdminService
from app.services.assessment_service import AssessmentService
from app.services.audio_service import AudioService

router = APIRouter(tags=["speaking"])


@router.post("/speaking/get_sentence/")
async def get_speaking_sentence(request: SpeakingSentenceRequest):
    svc = AudioService()
    return await svc.get_speaking_sentence(
        request.idToken, request.child_id, request.grade
    )


@router.post("/speaking/get_all_sentences/")
async def get_all_speaking_sentences(request: SpeakingSentenceRequest):
    svc = AudioService()
    return await svc.get_all_speaking_sentences(
        request.idToken, request.child_id, request.grade
    )


@router.post("/speaking/analyze/")
async def analyze_speaking(request: SpeakingAnalyzeRequest):
    svc = AssessmentService()
    return await svc.speaking_analyze(
        request.idToken,
        request.child_id,
        request.grade,
        request.original_sentence,
        request.audio_base64,
        request.audio_format,
    )


@router.post("/speaking/submit/")
async def submit_speaking_test(request: SpeakingSubmitRequest):
    svc = AssessmentService()
    submissions = None
    if request.submissions:
        submissions = [s.model_dump() for s in request.submissions]
    return await svc.speaking_submit(
        request.idToken,
        request.child_id,
        request.grade,
        sentence_id=request.sentence_id,
        original_sentence=request.original_sentence,
        audio_base64=request.audio_base64,
        audio_format=request.audio_format,
        submissions=submissions,
    )


@router.post("/speaking/complete_result/")
async def speaking_complete_result(request: SpeakingResultRequest):
    svc = AssessmentService()
    return svc.speaking_complete_result(
        request.idToken, request.child_id, request.grade
    )


@router.post("/admin/pregenerate_speaking_audio/")
async def pregenerate_speaking_audio(request: GetDetailsRequest):
    svc = AdminService()
    return await svc.pregenerate_speaking_audio(request.idToken)
