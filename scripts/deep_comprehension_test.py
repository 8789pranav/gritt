"""Deep comprehension test: exercises the real comprehension engine end-to-end.

Runs against the actual engine (no API mocks) for every grade, answering
each question with a mix of correct, wrong, and skipped answers to trigger
various tags.  Prints the full JSON response for submit and complete_result.

Usage:
    $env:PYTHONIOENCODING="utf-8"; python scripts/deep_comprehension_test.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import MockFirebaseClient

_mock_fb = MockFirebaseClient()


def _setup():
    """Patch Firebase, auth, and TTS so we can run without real credentials."""
    _mock_fb.ref("users/test-uid").set({
        "name": "Test Parent",
        "email": "test@test.com",
    })
    _mock_fb.ref("users/test-uid/children/child-1").set({
        "name": "Test Child",
        "age": 6,
        "grade": "Kindergarten",
    })

    def fake_verify_token(token: str) -> dict:
        if not token or token == "invalid":
            raise Exception("Invalid token")
        return {"uid": "test-uid", "email": "test@test.com"}

    async def fake_synthesize(text: str, speed: float = 1.0) -> str:
        return "fake_audio_base64"

    patches = [
        patch("app.infrastructure.firebase.get_firebase_client", return_value=_mock_fb),
        patch("app.infrastructure.repositories.get_firebase_client", return_value=_mock_fb),
        patch("app.core.security.get_firebase_client", return_value=_mock_fb),
        patch("firebase_admin.auth.verify_id_token", side_effect=fake_verify_token),
    ]

    for p in patches:
        p.start()
    return patches


def _teardown(patches):
    for p in patches:
        p.stop()


def run_grade_test(grade: str) -> None:
    """Run a full comprehension test for one grade with mixed answers."""
    from app.services.assessment_service import AssessmentService
    from app.engines.registry import comprehension_engine
    from app.domain.enums import Grade

    svc = AssessmentService()
    engine = comprehension_engine()
    grade_enum = Grade.parse(grade)

    # Step 1: Get stories directly from engine
    print(f"\n{'='*80}")
    print(f"  COMPREHENSION DEEP TEST -- Grade: {grade}")
    print(f"{'='*80}")

    stories = engine.get_items(grade_enum)
    total_questions = sum(len(s.questions) for s in stories)

    print(f"\n--- Step 1: Get Stories ({len(stories)} stories, {total_questions} questions) ---")
    for si, story in enumerate(stories):
        print(f"\n  Story {si+1}: \"{story.title}\" ({len(story.questions)} questions)")
        print(f"  Text: \"{story.story_text[:100]}...\"")
        for qi, q in enumerate(story.questions):
            print(f"    Q{qi+1} [{q.question_type.value}] {q.question}")
            for oi, opt in enumerate(q.options):
                marker = " <-- CORRECT" if oi == q.correct_index else ""
                print(f"      {oi}: {opt}{marker}")

    # Step 2: Build answers -- mix of correct, wrong, and skipped
    print(f"\n--- Step 2: Submitting Answers ---")
    story_answers: List[Dict[str, Any]] = []
    all_q_info = []  # track for display

    for story in stories:
        answers = []
        for q in story.questions:
            correct_idx = q.correct_index
            wrong_idx = (correct_idx + 1) % len(q.options)

            # Strategy: every 3rd question skipped, every 3rd answered wrong, rest correct
            q_num = len(all_q_info)
            if q_num % 3 == 0:
                # Correct answer
                selected = correct_idx
                status = "CORRECT"
                answered = True
            elif q_num % 3 == 1:
                # Wrong answer
                selected = wrong_idx
                status = f"WRONG (selected {selected}, correct is {correct_idx})"
                answered = True
            else:
                # Skipped (don't include in answers)
                selected = None
                status = "SKIPPED"
                answered = False

            print(f"  {q.question_id} [{q.question_type.value}] -> {status}")
            all_q_info.append({
                "question_id": q.question_id,
                "question": q.question,
                "type": q.question_type.value,
                "correct_idx": correct_idx,
                "selected": selected,
                "answered": answered,
                "status": status,
            })

            if answered:
                answers.append({
                    "question_id": q.question_id,
                    "selected_index": selected,
                })

        story_answers.append({
            "story_id": story.story_id,
            "answers": answers,
        })

    # Step 3: Submit
    submit_resp = svc.comprehension_submit(
        "test-token", "child-1", grade, story_answers
    )

    print(f"\n--- Step 3: Submit Response (full JSON) ---")
    print(json.dumps(submit_resp, indent=2, ensure_ascii=False, default=str))

    # Step 4: Get complete result
    complete_resp = svc.comprehension_complete_result(
        "test-token", "child-1", grade
    )

    print(f"\n--- Step 4: Complete Result (full JSON) ---")
    print(json.dumps(complete_resp, indent=2, ensure_ascii=False, default=str))

    # Step 5: Per-question tag analysis
    print(f"\n--- Step 5: Per-Question Tag Analysis ---")
    per_q = submit_resp.get("per_question_tags", [])
    for pq in per_q:
        qid = pq["item_id"]
        q_info = next((q for q in all_q_info if q["question_id"] == qid), None)
        q_label = q_info["question"][:50] if q_info else qid
        q_type = q_info["type"] if q_info else "?"
        tags_str = ", ".join(pq["tags"]) if pq["tags"] else "(none)"
        correct_str = "OK" if pq["is_correct"] else "WRONG"
        answered_str = "answered" if pq["answered"] else "NOT answered"
        print(f"  {qid} [{q_type}] {correct_str} [{answered_str}]")
        print(f"    Q: \"{q_label}\"")
        print(f"    Tags: [{tags_str}]")

    # Step 6: Test-level tags
    print(f"\n--- Step 6: Test-Level Tags (dear_parent_tags) ---")
    for tag in submit_resp.get("dear_parent_tags", []):
        print(f"  [{tag['polarity'].upper():12s}] {tag['tag']:40s} (conf={tag['confidence']})")
        print(f"               {tag['description']}")
        if tag.get("evidence"):
            print(f"               Evidence: {tag['evidence']}")

    # Step 7: Story breakdown
    print(f"\n--- Step 7: Story Breakdown ---")
    for sb in submit_resp.get("results", []):
        print(f"  Story: \"{sb.get('title', '?')}\"")
        for qa in sb.get("questions", []):
            qid = qa.get("question_id", "?")
            q_info = next((q for q in all_q_info if q["question_id"] == qid), None)
            correct_idx = q_info["correct_idx"] if q_info else "?"
            selected = qa.get("selected_index", "?")
            is_correct = qa.get("is_correct", False)
            q_type = qa.get("question_type", "?")
            status = "OK" if is_correct else "WRONG"
            print(f"    {qid} [{q_type}] selected={selected} correct={correct_idx} -> {status}")

    # Step 8: Summary
    print(f"\n--- Step 8: Summary ---")
    print(f"  Total questions:  {submit_resp.get('total_questions', '?')}")
    print(f"  Correct answers:  {submit_resp.get('correct_answers', '?')}")
    print(f"  Percentage:       {submit_resp.get('percentage', '?')}")
    print(f"  Level:            {submit_resp.get('level', '?')}")
    print(f"  Status:           {submit_resp.get('status', '?')}")
    print(f"  Recommendation:   {submit_resp.get('recommendation', '?')}")
    print(f"  Message:          {submit_resp.get('message', '?')}")

    # Step 9: Complete result parent summary
    print(f"\n--- Step 9: Parent Summary (from complete_result) ---")
    ps = complete_resp.get("parent_summary", {})
    print(json.dumps(ps, indent=2, ensure_ascii=False, default=str))


def main():
    patches = _setup()
    try:
        grades = ["Kindergarten", "First", "Second", "Third"]
        for grade in grades:
            run_grade_test(grade)
            print()
    finally:
        _teardown(patches)


if __name__ == "__main__":
    main()
