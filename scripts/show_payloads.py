"""Show complete payloads for all 4 submit_test APIs and run real tests.

Prints the exact JSON payload sent to each submit endpoint, then runs
the real engine and shows the response with tags.

Usage:
    $env:PYTHONIOENCODING="utf-8"; python scripts/show_payloads.py
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
    _mock_fb.ref("users/test-uid").set({"name": "Test Parent", "email": "test@test.com"})
    _mock_fb.ref("users/test-uid/children/child-1").set({"name": "Test Child", "age": 6, "grade": "Kindergarten"})

    def fake_verify_token(token: str) -> dict:
        return {"uid": "test-uid", "email": "test@test.com"}

    async def fake_transcribe(audio_b64, fmt="mp3"):
        return {
            "success": True,
            "transcribed_text": "This is a test transcription.",
            "word_timestamps": [],
            "duration": 3.0,
        }

    async def fake_analyze(original, transcribed, timestamps, duration, grade):
        return {
            "success": True,
            "analysis": {
                "pronunciation": {"normalised": 0.90, "issues": []},
                "fluency": {"normalised": 0.85, "issues": []},
                "prosody": {"normalised": 0.80, "issues": []},
                "grammar": {"normalised": 0.95, "issues": []},
                "overall": {"score": 87, "status": "Good", "level": "Proficient", "parent_tip": "Keep practising."},
                "speaking_rate": {"wpm": 120},
            },
        }

    patches = [
        patch("app.infrastructure.firebase.get_firebase_client", return_value=_mock_fb),
        patch("app.infrastructure.repositories.get_firebase_client", return_value=_mock_fb),
        patch("app.core.security.get_firebase_client", return_value=_mock_fb),
        patch("firebase_admin.auth.verify_id_token", side_effect=fake_verify_token),
    ]

    # Mock the speaking analysis provider
    mock_provider = AsyncMock()
    mock_provider.transcribe = fake_transcribe
    mock_provider.analyze = fake_analyze
    patches.append(patch("app.infrastructure.speech.get_speech_provider", return_value=mock_provider))

    for p in patches:
        p.start()
    return patches


def _teardown(patches):
    for p in patches:
        p.stop()


def test_logic():
    """Logic: /logic/submit_test/"""
    from app.services.assessment_service import AssessmentService
    from app.engines.registry import logic_engine
    from app.domain.enums import Grade

    print(f"\n{'#'*80}")
    print(f"  1. LOGIC -- /logic/submit_test/")
    print(f"{'#'*80}")

    svc = AssessmentService()
    engine = logic_engine()
    items = engine.get_items(Grade.KINDERGARTEN)

    # Build payload with all fields
    responses = []
    for i, item in enumerate(items):
        correct = item.correct_answer_index
        wrong = (correct + 1) % len(item.options)
        if i % 3 == 0:
            sel, time, attempts, sc = correct, 30.0, 1, False
        elif i % 3 == 1:
            sel, time, attempts, sc = wrong, 9.0, 1, False
        else:
            sel, time, attempts, sc = correct, 36.0, 2, True

        responses.append({
            "item_id": item.item_id,
            "selected_answer_index": sel,
            "response_time_seconds": time,
            "attempts": attempts,
            "self_corrected": sc,
            "explanation_provided": None,
        })

    payload = {
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "responses": responses,
    }

    print(f"\n  PAYLOAD SENT:")
    print(f"  {json.dumps(payload, indent=2, ensure_ascii=False)}")

    resp = svc.logic_submit_test("test-token", "child-1", "Kindergarten", responses)

    print(f"\n  RESPONSE (tags only):")
    print(f"  Score: {resp['correct_answers']}/{resp['total_items']} ({resp['percentage']}%)")
    print(f"  Level: {resp['level']}")
    print(f"\n  dear_parent_tags:")
    for t in resp.get("dear_parent_tags", []):
        print(f"    [{t['polarity']}] {t['tag']} -- {t.get('evidence','')}")
    print(f"\n  per_item_tags:")
    for pi in resp.get("per_item_tags", []):
        print(f"    {pi['item_id']}: answered={pi['answered']} correct={pi['is_correct']} tags={pi['tags']}")


def test_spelling():
    """Spelling: /spelling/submit_words/"""
    from app.services.assessment_service import AssessmentService
    from app.engines.registry import spelling_engine
    from app.domain.enums import Grade

    print(f"\n{'#'*80}")
    print(f"  2. SPELLING -- /spelling/submit_words/")
    print(f"{'#'*80}")

    svc = AssessmentService()
    engine = spelling_engine()
    items = engine.get_items(Grade.KINDERGARTEN)

    # Build payload
    words = []
    for i, item in enumerate(items):
        word = item.word
        if i % 3 == 0:
            user_input = word  # correct
            time = 8.0
        elif i % 3 == 1:
            user_input = word[:-1] if len(word) > 1 else word  # wrong (drop last char)
            time = 2.0  # fast
        else:
            user_input = word[:-1] if len(word) > 1 else word  # wrong
            time = 8.0

        words.append({
            "word": word,
            "user_input": user_input,
            "type": item.word_type.value,
            "time": time,
            "hints_used": 0,
        })

    payload = {
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "words": words,
    }

    print(f"\n  PAYLOAD SENT:")
    print(f"  {json.dumps(payload, indent=2, ensure_ascii=False)}")

    from app.schemas import SubmitWordsRequest
    req = SubmitWordsRequest(**payload)
    resp = svc.spelling_submit_words(
        "test-token", "child-1", "Kindergarten",
        [{"word": w["word"], "user_input": w["user_input"], "type": w["type"],
          "time": w["time"], "hints_used": w["hints_used"]} for w in words]
    )

    print(f"\n  RESPONSE (tags only):")
    print(f"  Score: {resp.get('score', '?')}")
    print(f"\n  dear_parent_tags:")
    for t in resp.get("dear_parent_tags", []):
        print(f"    [{t['polarity']}] {t['tag']} -- {t.get('evidence','')}")
    print(f"\n  per_word_tags:")
    for pw in resp.get("per_word_tags", []):
        print(f"    {pw['item_id']}: answered={pw['answered']} correct={pw['is_correct']} tags={pw['tags']}")


def test_comprehension():
    """Comprehension: /comprehension/submit/"""
    from app.services.assessment_service import AssessmentService
    from app.engines.registry import comprehension_engine
    from app.domain.enums import Grade

    print(f"\n{'#'*80}")
    print(f"  3. COMPREHENSION -- /comprehension/submit/")
    print(f"{'#'*80}")

    svc = AssessmentService()
    engine = comprehension_engine()
    stories = engine.get_items(Grade.KINDERGARTEN)

    # Build payload
    story_answers = []
    for story in stories:
        answers = []
        for qi, q in enumerate(story.questions):
            if qi % 3 == 0:
                sel = q.correct_index  # correct
            elif qi % 3 == 1:
                sel = (q.correct_index + 1) % len(q.options)  # wrong
            else:
                continue  # skip

            answers.append({
                "question_id": q.question_id,
                "selected_index": sel,
            })
        story_answers.append({
            "story_id": story.story_id,
            "answers": answers,
        })

    payload = {
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "story_answers": story_answers,
    }

    print(f"\n  PAYLOAD SENT:")
    print(f"  {json.dumps(payload, indent=2, ensure_ascii=False)}")

    resp = svc.comprehension_submit("test-token", "child-1", "Kindergarten", story_answers)

    print(f"\n  RESPONSE (tags only):")
    print(f"  Score: {resp['correct_answers']}/{resp['total_questions']} ({resp['percentage']}%)")
    print(f"  Level: {resp['level']}")
    print(f"\n  dear_parent_tags:")
    for t in resp.get("dear_parent_tags", []):
        print(f"    [{t['polarity']}] {t['tag']} -- {t.get('evidence','')}")
    print(f"\n  per_question_tags:")
    for pq in resp.get("per_question_tags", []):
        print(f"    {pq['item_id']}: answered={pq['answered']} correct={pq['is_correct']} tags={pq['tags']}")


def test_speaking():
    """Speaking: /speaking/submit/"""
    import asyncio
    from app.services.assessment_service import AssessmentService
    from app.engines.registry import speaking_engine
    from app.domain.enums import Grade

    print(f"\n{'#'*80}")
    print(f"  4. SPEAKING -- /speaking/submit/")
    print(f"{'#'*80}")

    svc = AssessmentService()
    engine = speaking_engine()
    sentences = engine.get_items(Grade.KINDERGARTEN)

    # Build payload with submissions for all sentences
    submissions = []
    for s in sentences:
        submissions.append({
            "sentence_id": s.sentence_id,
            "original_sentence": s.sentence,
            "audio_base64": "fake_audio_base64_data",
            "audio_format": "mp3",
        })

    payload = {
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": "Kindergarten",
        "sentence_id": None,
        "original_sentence": None,
        "audio_base64": None,
        "audio_format": "mp3",
        "submissions": submissions,
    }

    print(f"\n  PAYLOAD SENT:")
    print(f"  {json.dumps(payload, indent=2, ensure_ascii=False)}")

    resp = asyncio.run(svc.speaking_submit(
        "test-token", "child-1", "Kindergarten",
        sentence_id=None,
        original_sentence=None,
        audio_base64=None,
        audio_format="mp3",
        submissions=submissions,
    ))

    print(f"\n  RESPONSE (tags only):")
    print(f"  Level: {resp.get('level', '?')}")
    print(f"\n  dear_parent_tags:")
    for t in resp.get("dear_parent_tags", []):
        print(f"    [{t['polarity']}] {t['tag']} -- {t.get('evidence','')}")
    print(f"\n  per_sentence_tags:")
    for ps in resp.get("per_sentence_tags", []):
        print(f"    {ps['item_id']}: answered={ps['answered']} correct={ps['is_correct']} tags={ps['tags']}")


def main():
    patches = _setup()
    try:
        test_logic()
        test_spelling()
        test_comprehension()
        test_speaking()
    finally:
        _teardown(patches)


if __name__ == "__main__":
    main()
