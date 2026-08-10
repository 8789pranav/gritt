"""Deep spelling test: exercises the real spelling engine end-to-end.

Runs against the actual engine (no API mocks) for every grade, with
per-word answers designed to trigger various tags.  Prints the full
JSON response for submit_words and complete_result.

Usage:
    python scripts/deep_spelling_test.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch Firebase before importing app modules
from tests.conftest import MockFirebaseClient

_mock_fb = MockFirebaseClient()


def _setup():
    """Patch Firebase and auth so we can run without real credentials."""
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

    # Apply patches
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


def _intentional_misspell(word: str) -> str:
    """Create a plausible misspelling that triggers phonics feature errors."""
    # Common error patterns per word type
    if word == "cat":
        return "ct"   # missing vowel -> short_vowel_error
    if word == "pen":
        return "pn"   # missing vowel -> short_vowel_error
    if word == "big":
        return "bg"   # missing vowel -> short_vowel_error
    if word == "hat":
        return "ht"   # missing vowel -> short_vowel_error
    if word == "dog":
        return "dg"   # missing vowel -> short_vowel_error
    if word == "cake":
        return "cak"  # missing silent_e -> silent_e_error
    if word == "bike":
        return "bik"  # missing silent_e -> silent_e_error
    if word == "like":
        return "lik"  # missing silent_e -> silent_e_error
    if word == "ship":
        return "sip"  # digraph error (sh -> s) -> consonant_digraph_error
    if word == "chip":
        return "cip"  # digraph error (ch -> c) -> consonant_digraph_error
    if word == "fish":
        return "fis"  # digraph error (sh -> s) -> consonant_digraph_error
    if word == "that":
        return "tat"  # digraph error (th -> t) -> consonant_digraph_error
    if word == "black":
        return "bak"  # blend error (bl -> b) + missing ending -> consonant_blend_error
    if word == "stop":
        return "sop"  # blend error (st -> s) -> consonant_blend_error
    if word == "flag":
        return "fag"  # blend error (fl -> f) -> consonant_blend_error
    if word == "the":
        return "th"   # sight word error
    if word == "said":
        return "sed"  # sight word error
    if word == "was":
        return "wuz"  # sight word error
    if word == "of":
        return "ov"   # sight word error
    if word == "to":
        return "too"  # sight word error
    # Default: drop the last char
    return word[:-1] if len(word) > 1 else word


def _fast_time() -> float:
    """Return a fast response time to trigger rushed_attempt tags."""
    return 2.0


def _slow_time() -> float:
    """Return a slow response time (no rush)."""
    return 8.0


def run_grade_test(grade: str) -> None:
    """Run a full spelling test for one grade with mixed answers."""
    from app.services.assessment_service import AssessmentService

    svc = AssessmentService()

    # Step 1: Get words for the grade
    print(f"\n{'='*80}")
    print(f"  SPELLING DEEP TEST — Grade: {grade}")
    print(f"{'='*80}")

    words_resp = svc.spelling_get_words(grade)
    words = words_resp["words"]
    print(f"\n--- Step 1: Get Words ({len(words)} words) ---")
    for i, w in enumerate(words):
        print(f"  {i+1}. \"{w['word']}\" (type={w['type']})  sentence: \"{w['sentence']}\"")

    # Step 2: Build answers — mix of correct, wrong, and fast-wrong
    # Strategy: answer every word, but make every 3rd word wrong
    # and make wrong answers fast to trigger rushed_attempt
    submitted_words: List[Dict[str, Any]] = []
    print(f"\n--- Step 2: Submitting Answers ---")
    for i, w in enumerate(words):
        word = w["word"]
        wtype = w["type"]

        if i % 3 == 0:
            # Correct answer, slow
            user_input = word
            time = _slow_time()
            hints = 0
            status = "CORRECT"
        elif i % 3 == 1:
            # Wrong answer, fast (triggers rushed_attempt)
            user_input = _intentional_misspell(word)
            time = _fast_time()
            hints = 0
            status = f"WRONG (fast={time}s)"
        else:
            # Wrong answer, slow (no rush, but still triggers feature errors)
            user_input = _intentional_misspell(word)
            time = _slow_time()
            hints = 0
            status = f"WRONG (slow={time}s)"

        print(f"  {i+1}. \"{word}\" -> \"{user_input}\"  [{status}]")
        submitted_words.append({
            "word": word,
            "user_input": user_input,
            "type": wtype,
            "time": time,
            "hints_used": hints,
        })

    # Submit
    submit_resp = svc.spelling_submit_words(
        "test-token", "child-1", grade, submitted_words
    )

    print(f"\n--- Step 3: Submit Response (full JSON) ---")
    print(json.dumps(submit_resp, indent=2, ensure_ascii=False, default=str))

    # Step 4: Get complete result
    complete_resp = svc.spelling_complete_result(
        "test-token", "child-1", grade
    )

    print(f"\n--- Step 4: Complete Result (full JSON) ---")
    print(json.dumps(complete_resp, indent=2, ensure_ascii=False, default=str))

    # Step 5: Summary analysis
    print(f"\n--- Step 5: Per-Word Tag Analysis ---")
    per_word = submit_resp.get("per_word_tags", [])
    for pw in per_word:
        word_idx = per_word.index(pw)
        word_label = words[word_idx]["word"] if word_idx < len(words) else "?"
        tags_str = ", ".join(pw["tags"]) if pw["tags"] else "(none)"
        correct_str = "OK" if pw["is_correct"] else "WRONG"
        answered_str = "answered" if pw["answered"] else "NOT answered"
        print(f"  {word_idx+1}. \"{word_label}\" {correct_str} [{answered_str}] tags: [{tags_str}]")

    print(f"\n--- Step 6: Test-Level Tags (dear_parent_tags) ---")
    for tag in submit_resp.get("dear_parent_tags", []):
        print(f"  [{tag['polarity'].upper():12s}] {tag['tag']:40s} (conf={tag['confidence']})")
        print(f"               {tag['description']}")
        if tag.get("evidence"):
            print(f"               Evidence: {tag['evidence']}")

    print(f"\n--- Step 7: Error Analysis ---")
    ea = submit_resp.get("error_analysis", {})
    if ea:
        for error_type, count in ea.items():
            print(f"  {error_type}: {count}")
    else:
        print("  (no errors)")

    print(f"\n--- Step 8: Assessment Summary ---")
    summary = submit_resp.get("assessment_summary", {})
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))

    print(f"\n--- Step 9: Strengths & Focus Areas ---")
    print(f"  Strengths:    {submit_resp.get('strengths', [])}")
    print(f"  Focus Areas:  {submit_resp.get('focus_areas', [])}")
    print(f"  Confidence:   {submit_resp.get('confidence', '')}")
    print(f"  Recommendation: {submit_resp.get('instructional_recommendation', '')}")


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
