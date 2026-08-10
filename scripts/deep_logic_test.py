"""Deep logic test: clean per-question listing for all grades.

For each grade, lists every question, the answer we gave, and the tags we got.

Usage:
    $env:PYTHONIOENCODING="utf-8"; python scripts/deep_logic_test.py
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import MockFirebaseClient

_mock_fb = MockFirebaseClient()


def _setup():
    _mock_fb.ref("users/test-uid").set({"name": "Test Parent", "email": "test@test.com"})
    _mock_fb.ref("users/test-uid/children/child-1").set({"name": "Test Child", "age": 6, "grade": "Kindergarten"})

    def fake_verify_token(token: str) -> dict:
        return {"uid": "test-uid", "email": "test@test.com"}

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


def run_grade(grade: str) -> None:
    from app.services.assessment_service import AssessmentService
    from app.engines.registry import logic_engine
    from app.domain.enums import Grade

    svc = AssessmentService()
    engine = logic_engine()
    grade_enum = Grade.parse(grade)
    items = engine.get_items(grade_enum)

    print(f"\n{'='*100}")
    print(f"  LOGIC TEST -- Grade: {grade}  ({len(items)} questions)")
    print(f"{'='*100}")

    # Build answers: rotate through correct, wrong-fast, wrong-slow, correct-self-corrected, skipped
    responses: List[Dict[str, Any]] = []
    answer_log: List[Dict[str, Any]] = []

    for i, item in enumerate(items):
        correct_idx = item.correct_answer_index
        wrong_idx = (correct_idx + 1) % len(item.options)
        expected = item.expected_latency_seconds or 30
        correct_text = item.options[correct_idx].text if hasattr(item.options[correct_idx], "text") else str(item.options[correct_idx])

        if i % 5 == 0:
            selected = correct_idx
            time = float(expected)
            attempts = 1
            self_corrected = False
            given_answer = correct_text
            outcome = "CORRECT"
        elif i % 5 == 1:
            selected = wrong_idx
            time = float(expected) * 0.3
            attempts = 1
            self_corrected = False
            given_answer = item.options[wrong_idx].text if hasattr(item.options[wrong_idx], "text") else str(item.options[wrong_idx])
            outcome = f"WRONG (fast {time:.0f}s)"
        elif i % 5 == 2:
            selected = wrong_idx
            time = float(expected) * 2.0
            attempts = 1
            self_corrected = False
            given_answer = item.options[wrong_idx].text if hasattr(item.options[wrong_idx], "text") else str(item.options[wrong_idx])
            outcome = f"WRONG (slow {time:.0f}s)"
        elif i % 5 == 3:
            selected = correct_idx
            time = float(expected) * 1.2
            attempts = 2
            self_corrected = True
            given_answer = correct_text
            outcome = "CORRECT (self-corrected, 2 attempts)"
        else:
            selected = None
            time = 0
            attempts = 1
            self_corrected = False
            given_answer = "(skipped)"
            outcome = "SKIPPED"

        answer_log.append({
            "item_id": item.item_id,
            "item_type": item.item_type,
            "difficulty": item.difficulty.value,
            "question": item.question_text,
            "options": [opt.text if hasattr(opt, "text") else str(opt) for opt in item.options],
            "correct_idx": correct_idx,
            "correct_answer": correct_text,
            "given_idx": selected,
            "given_answer": given_answer,
            "outcome": outcome,
            "time": time,
            "attempts": attempts,
            "self_corrected": self_corrected,
            "primary_tag": item.primary_tag.value,
        })

        if selected is not None:
            responses.append({
                "item_id": item.item_id,
                "selected_answer_index": selected,
                "response_time_seconds": time,
                "attempts": attempts,
                "self_corrected": self_corrected,
            })

    # Submit
    submit_resp = svc.logic_submit_test("test-token", "child-1", grade, responses)
    per_item = {pi["item_id"]: pi for pi in submit_resp.get("per_item_tags", [])}

    # Print each question with answer and tags
    for i, log in enumerate(answer_log):
        pit = per_item.get(log["item_id"], {})
        tags = pit.get("tags", [])
        is_correct = pit.get("is_correct")
        answered = pit.get("answered")

        print(f"\n  Q{i+1}. [{log['item_type']}] (difficulty={log['difficulty']})")
        print(f"      Question:  \"{log['question']}\"")
        print(f"      Options:")
        for oi, opt in enumerate(log["options"]):
            marker = " <-- CORRECT" if oi == log["correct_idx"] else ""
            chosen = " <-- CHOSEN" if oi == log["given_idx"] else ""
            print(f"        {oi}: {opt}{marker}{chosen}")
        print(f"      Answer:    {log['given_answer']}")
        print(f"      Correct:   {log['correct_answer']}")
        print(f"      Outcome:   {log['outcome']}")
        print(f"      Answered:  {answered}")
        print(f"      Is correct: {is_correct}")
        print(f"      Primary tag: {log['primary_tag']}")
        print(f"      Tags:     {tags}")

    # Test-level tags
    print(f"\n  {'-'*80}")
    print(f"  TEST-LEVEL TAGS (dear_parent_tags):")
    for tag in submit_resp.get("dear_parent_tags", []):
        print(f"    [{tag['polarity'].upper():12s}] {tag['tag']}")
        print(f"      {tag['description']}")
        print(f"      Evidence: {tag.get('evidence', '')}")

    # Summary
    print(f"\n  SUMMARY:")
    print(f"    Score:       {submit_resp.get('correct_answers', 0)}/{submit_resp.get('total_items', 0)}")
    print(f"    Percentage:  {submit_resp.get('percentage', 0)}%")
    print(f"    Level:       {submit_resp.get('level', '')}")
    print(f"    Recommendation: {submit_resp.get('recommendation', '')}")


def main():
    patches = _setup()
    try:
        for grade in ["Kindergarten", "First", "Second", "Third"]:
            run_grade(grade)
            print()
    finally:
        _teardown(patches)


if __name__ == "__main__":
    main()
