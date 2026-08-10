"""Quick test: verify unrelated_attempt vs error tags."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import MockFirebaseClient
from unittest.mock import patch

fb = MockFirebaseClient()
fb.ref("users/test-uid").set({"name": "T", "email": "t@t.com"})
fb.ref("users/test-uid/children/child-1").set({"name": "C", "age": 6, "grade": "K"})

def ft(t): return {"uid": "test-uid", "email": "t@t.com"}

for p in [
    patch("app.infrastructure.firebase.get_firebase_client", return_value=fb),
    patch("app.infrastructure.repositories.get_firebase_client", return_value=fb),
    patch("app.core.security.get_firebase_client", return_value=fb),
    patch("firebase_admin.auth.verify_id_token", side_effect=ft),
]:
    p.start()

from app.services.assessment_service import AssessmentService
from app.engines.registry import spelling_engine
from app.domain.enums import Grade

svc = AssessmentService()
engine = spelling_engine()
items = engine.get_items(Grade.KINDERGARTEN)

# Mix: correct, misspelled, completely different
test_cases = []
for i, item in enumerate(items):
    if i % 4 == 0:
        inp = item.word  # correct
    elif i % 4 == 1:
        inp = item.word[:-1] if len(item.word) > 2 else item.word + "x"  # misspelling
    elif i % 4 == 2:
        inp = "xyz"  # completely different
    else:
        inp = "dog"  # completely different
    test_cases.append({"word": item.word, "user_input": inp, "type": item.word_type.value, "time": 8.0, "hints_used": 0})

resp = svc.spelling_submit_words("test-token", "child-1", "Kindergarten", test_cases)

print("WORD               INPUT              CORRECT  TAGS")
print("-" * 90)
for pw in resp.get("per_word_tags", []):
    word = pw["item_id"].split(":")[-1]
    tc = next(c for c in test_cases if c["word"].lower() == word.lower())
    status = "OK" if pw["is_correct"] else "WRONG"
    tags_str = ", ".join(pw["tags"])
    print(f"  {word:18s} {tc['user_input']:18s} {status:7s}  [{tags_str}]")
