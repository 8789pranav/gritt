"""Router for the holistic final report endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import FinalReportRequest
from app.services.report_service import ReportService

router = APIRouter(tags=["report"])


@router.post("/final_report/")
async def generate_final_report(request: FinalReportRequest):
    """Generate a holistic progress report from all assessment results.

    Collects the latest scores and tags from every assessment type (logic,
    spelling, speaking, comprehension) for the child in the given grade,
    then uses GPT-4o to synthesise a parent-friendly report with strengths,
    growth areas, cross-domain patterns, and actionable recommendations.

    The AI only narrates — it never invents scores or tags. All numbers and
    tags are pre-computed by the assessment engines.
    """
    svc = ReportService()
    return svc.generate_final_report(
        request.idToken, request.child_id, request.grade
    )
