"""Router for the Learning Snapshot letter endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import SnapshotRequest
from app.services.snapshot_service import get_snapshot_service
from app.services.snapshot_writer import get_snapshot_writer

router = APIRouter(tags=["snapshot"])


@router.post("/snapshot/")
async def generate_snapshot(request: SnapshotRequest):
    """Generate the Learning Snapshot letter for a child.

    Stage A (deterministic) fetches the latest result for every assessment,
    maps the fired tags to the five learning areas, and computes the evidence
    package. Stage B asks GPT-4o to write the letter, then validates it
    against hard guardrails: no scores, no labels, no clinical language, no
    comparison to other children. If the guardrails fail or the LLM is
    unavailable, a warm generic letter is returned instead.
    """
    service = get_snapshot_service()
    writer = get_snapshot_writer()

    evidence = service.build_evidence(
        request.idToken, request.child_id, request.grade
    )
    letter = writer.write(evidence)

    return {
        "success": True,
        "child_id": request.child_id,
        "child_name": evidence.get("child_name", ""),
        "grade": evidence.get("grade", request.grade),
        "tests_completed": evidence.get("tests_completed", []),
        "snapshot": letter,
    }
