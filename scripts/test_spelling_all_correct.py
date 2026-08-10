"""Quick test: all correct spelling answers - verify positive tags fire."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import MockFirebaseClient
from unittest.mock import patch

fb = MockFirebaseClient()
fb.ref("users/test-uid").set({"name": "Test", "email": "t@t.com"})
fb.ref("users/test-uid/children/child-1").set({"name": "Child", "age": 6, "grade": "Kindergarten"})

def fake_token(t): return {"uid": "test-uid", "email": "t@t.com"}

patches = [
    patch("app.infrastructure.firebase.get_firebase_client", return_value=fb),
    patch("app.infrastructure.repositories.get_firebase_client", return_value=fb),
    patch("app.core.security.get_firebase_client", return_value=fb),
    patch("firebase_admin.auth.verify_id_token", side_effect=fake_token),
]
for p in patches:
    p.start()

from app.services.assessment_service import AssessmentService
from app.engines.registry import spelling_engine
from app.domain.enums import Grade

svc = AssessmentService()
engine = spelling_engine()

for grade_name in ["Kindergarten", "First", "Second", "Third"]:
    grade = Grade.parse(grade_name)
    items = engine.get_items(grade)

    # ALL CORRECT answers
    words = []
    for item in items:
        words.append({
            "word": item.word,
            "user_input": item.word,
            "type": item.word_type.value,
            "time": 8.0,
            "hints_used": 0,
        })

    resp = svc.spelling_submit_words("test-token", "child-1", grade_name, words)

    print(f"\n{'='*70}")
    print(f"  ALL CORRECT -- Grade: {grade_name}")
    print(f"{'='*70}")

    correct_count = sum(1 for pw in resp.get("per_word_tags", []) if pw["is_correct"])
    print(f"  Correct: {correct_count}/{len(items)}")

    print(f"\n  PER-WORD TAGS:")
    for pw in resp.get("per_word_tags", []):
        status = "OK" if pw["is_correct"] else "WRONG"
        tags_str = ", ".join(pw["tags"]) if pw["tags"] else "(none)"
        print(f"    {pw['item_id']:35s} {status:5s} [{tags_str}]")

    print(f"\n  TEST-LEVEL TAGS:")
    for t in resp.get("dear_parent_tags", []):
        print(f"    [{t['polarity']:12s}] {t['tag']} -- {t.get('evidence', '')}")
