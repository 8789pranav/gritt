"""Logic Quest assessment endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.schemas import (
    CompleteLogicResultRequest,
    GetDetailsRequest,
    GetLogicTestRequest,
    SubmitLogicResponseRequest,
    SubmitLogicTestRequest,
)
from app.services.admin_service import AdminService
from app.services.assessment_service import AssessmentService
from app.services.audio_service import AudioService

router = APIRouter(tags=["logic"])


@router.get("/logic/ui")
async def logic_ui():
    """Serve the logic assessment web UI."""
    from app.core.config import get_settings

    static_dir = get_settings().paths.static_dir
    path = static_dir / "logic_test_web.html"
    if not path.exists():
        path = static_dir.parent / "logic_test_web.html"
    return FileResponse(str(path))


@router.post("/logic/get_test/")
async def logic_get_test(request: GetLogicTestRequest):
    svc = AssessmentService()
    return svc.logic_get_test(request.idToken, request.child_id, request.grade)


@router.post("/logic/get_test_with_audio/")
async def logic_get_test_with_audio(request: GetLogicTestRequest):
    svc = AudioService()
    return await svc.logic_test_with_audio(
        request.idToken, request.child_id, request.grade
    )


@router.post("/logic/submit_response/")
async def logic_submit_response(request: SubmitLogicResponseRequest):
    svc = AssessmentService()
    return svc.logic_submit_response(
        request.idToken,
        request.child_id,
        request.item_id,
        request.selected_answer_index,
        request.response_time_seconds,
        request.attempts,
        request.self_corrected,
        request.explanation_provided,
    )


@router.post("/logic/submit_test/")
async def logic_submit_test(request: SubmitLogicTestRequest):
    svc = AssessmentService()
    responses = [r.model_dump() for r in request.responses]
    return svc.logic_submit_test(
        request.idToken, request.child_id, request.grade, responses
    )


@router.post("/logic/complete_result/")
async def logic_complete_result(request: CompleteLogicResultRequest):
    svc = AssessmentService()
    return svc.logic_complete_result(
        request.idToken, request.child_id, request.grade
    )


@router.post("/admin/pregenerate_logic_audio/")
async def pregenerate_logic_audio(request: GetDetailsRequest):
    svc = AdminService()
    return await svc.pregenerate_logic_audio(request.idToken)
