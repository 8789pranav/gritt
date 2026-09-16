"""Router for the Learning Snapshot letter endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.security import verify_paid_child
from app.infrastructure.repositories import SnapshotRepository
from app.schemas import SnapshotRequest
from app.services.snapshot_service import get_snapshot_service
from app.services.snapshot_writer import get_snapshot_writer

router = APIRouter(tags=["snapshot"])


@router.post("/snapshot/")
async def generate_snapshot(request: SnapshotRequest):
    """Return the Learning Snapshot letter for a child, generating it once.

    The first call builds the evidence package and asks the model to write the
    letter. The result is saved under ``users/{uid}/children/{child_id}/snapshot``
    so every later call for the same child returns the exact same letter.

    Stage A (deterministic) fetches the latest result for every assessment,
    maps the fired tags to the five learning areas, and computes the evidence
    package - including the words the child actually wrote and read. Stage B
    asks the model to write the letter in Eko's voice, then validates it
    against hard guardrails: no scores, no labels, no clinical language, no
    comparison to other children, no praise headline over a growth edge, and
    no quoted misspelling that reads as a correction. If the guardrails fail
    or the LLM is unavailable, a warm generic letter is returned instead.
    """
    service = get_snapshot_service()
    writer = get_snapshot_writer()
    snapshots = SnapshotRepository()

    uid, child_data = verify_paid_child(request.idToken, request.child_id)

    saved = snapshots.get(uid, request.child_id)
    if saved:
        return saved

    evidence = service.build_evidence(
        request.idToken,
        request.child_id,
        request.grade,
        uid=uid,
        child_data=child_data,
    )
    letter = writer.write(evidence)

    response = {
        "success": True,
        "child_id": request.child_id,
        "child_name": evidence.get("child_name", ""),
        "grade": evidence.get("grade", request.grade),
        "tests_completed": evidence.get("tests_completed", []),
        "snapshot": letter,
    }

    snapshots.save(uid, request.child_id, response)
    return response
