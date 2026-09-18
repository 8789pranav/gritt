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
    letter. A real letter is saved under
    ``users/{uid}/children/{child_id}/snapshot`` so every later call for the
    same child returns the exact same letter. The generic fallback is returned
    but never saved, so a failed run does not become the child's only letter.

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

    # A cached letter is only worth serving if it is a real one. The ones
    # already saved before the writer stopped handing back failures are
    # still in the database, and a parent pressing the button again has to
    # get a new letter rather than the same empty page for ever.
    saved = snapshots.get(uid, request.child_id)
    if saved and _is_real_letter(saved.get("snapshot")):
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

    # Only a real letter is worth keeping forever. The generic fallback is
    # what comes back when the model was unreachable or every draft broke a
    # guardrail - a warm page that says nothing about this child. Caching it
    # froze one bad minute into the parent's only answer: they pressed the
    # button again, got the same empty letter, and reported that the snapshot
    # would not generate. A letter built from no results is the same problem
    # from the other end, so neither is saved and the next call tries again.
    if _is_keepable(letter, evidence):
        snapshots.save(uid, request.child_id, response)
    return response


def _is_real_letter(letter) -> bool:
    """Whether this letter was actually written about a child.

    The generic fallback is warm, correct and about nobody. It is what comes
    back when the model could not be reached or no draft survived the
    guardrails, and it is the one thing that must never be mistaken for the
    child's snapshot.
    """
    if not isinstance(letter, dict):
        return False
    meta = letter.get("meta") or {}
    return bool(meta.get("llm_generated"))


def _is_finished_letter(letter: dict, evidence: dict) -> bool:
    """Whether every part a parent actually reads is filled in.

    "The model replied" is not the same as "the letter is finished". The
    writer ranks drafts on the hard guardrails, and a missing or empty
    section counts only as a voice slip - so a draft with nothing under
    "still growing" can be the best one on offer and still be shipped.
    Showing it is fine; the parent gets a letter. Keeping it is not.

    Sections the evidence never found anything for are left alone. A child
    with no growth edges has nothing to put under that heading, and
    demanding one would mean their letter never saves - the same bug
    wearing the opposite coat.
    """
    opening = letter.get("opening") or {}
    if not (opening.get("headline") and opening.get("paragraph")):
        return False
    if not letter.get("closing"):
        return False
    if not ((letter.get("for_the_conference") or {}).get("items") or []):
        return False
    if evidence.get("strengths") and not (letter.get("what_i_noticed") or []):
        return False
    if evidence.get("growth_edges") and not (letter.get("still_growing") or []):
        return False
    return True


def _is_keepable(letter: dict, evidence: dict) -> bool:
    """Whether this letter is good enough to be the child's one letter.

    Written by the model, about a child who actually did something, and
    finished. Anything less is shown to the parent and thrown away, so the
    next call writes them a real one.
    """
    return bool(
        _is_real_letter(letter)
        and evidence.get("tests_completed")
        and _is_finished_letter(letter, evidence)
    )
