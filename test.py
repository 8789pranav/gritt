# --------------------------------------------------------------
# test_api.py
# --------------------------------------------------------------
import unittest
import requests
import json
import time
import uuid
from datetime import datetime

BASE_URL = "http://localhost:8000"
HEADERS = {"Content-Type": "application/json"}

# --------------------------------------------------------------
# FIXED CREDENTIALS (as you requested)
# --------------------------------------------------------------
FIXED_EMAIL = "nandita@thedearparentproject.com"
FIXED_PASSWORD = "Test@123"

# --------------------------------------------------------------
# Helper – login once and keep the id_token
# --------------------------------------------------------------
def login_and_get_token() -> str:
    payload = {"email": FIXED_EMAIL, "password": FIXED_PASSWORD}
    resp = requests.post(f"{BASE_URL}/login", headers=HEADERS, data=json.dumps(payload))
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed: {resp.json()}")
    return resp.json()["id_token"]


# --------------------------------------------------------------
# Helper – create a fresh child (unique name each run)
# --------------------------------------------------------------
def create_child(token: str, grade: str = "Kindergarten") -> str:
    child_name = f"TestChild_{int(time.time())}"
    payload = {
        "idToken": token,
        "name": child_name,
        "age": 5,
        "grade": grade,
    }
    resp = requests.post(f"{BASE_URL}/add_child/", headers=HEADERS, data=json.dumps(payload))
    if resp.status_code != 200:
        raise RuntimeError(f"Add child failed: {resp.json()}")
    return resp.json()["child_id"]


# --------------------------------------------------------------
# Helper – get the word list for a grade
# --------------------------------------------------------------
def get_word_list(grade: str) -> list:
    payload = {"grade": grade}
    resp = requests.post(f"{BASE_URL}/grade/", headers=HEADERS, data=json.dumps(payload))
    if resp.status_code != 200:
        raise RuntimeError(f"Grade endpoint failed: {resp.json()}")
    return resp.json()["words"]


# --------------------------------------------------------------
# Helper – submit answers and return the JSON response
# --------------------------------------------------------------
def submit_answers(token: str, child_id: str, grade: str, words: list) -> dict:
    payload = {
        "idToken": token,
        "child_id": child_id,
        "grade": grade,
        "words": words,
    }
    resp = requests.post(f"{BASE_URL}/submit_words/", headers=HEADERS, data=json.dumps(payload))
    if resp.status_code != 200:
        raise RuntimeError(f"Submit words failed: {resp.json()}")
    return resp.json()


# --------------------------------------------------------------
# Helper – get the final report (complete_result)
# --------------------------------------------------------------
def get_complete_result(token: str, child_id: str, grade: str) -> dict:
    payload = {"idToken": token, "child_id": child_id, "grade": grade}
    resp = requests.post(f"{BASE_URL}/complete_result/", headers=HEADERS, data=json.dumps(payload))
    if resp.status_code != 200:
        raise RuntimeError(f"Complete result failed: {resp.json()}")
    return resp.json()


# --------------------------------------------------------------
# Test class
# --------------------------------------------------------------
class TestScoringAndBand(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\n=== SETTING UP TEST ENVIRONMENT ===")
        cls.id_token = login_and_get_token()
        cls.grade = "Kindergarten"               # change if you want another grade
        cls.child_id = create_child(cls.id_token, cls.grade)
        print(f"Using child_id: {cls.child_id}")

    # ------------------------------------------------------------------
    # 1. ALL CORRECT → status = "At" (or "Above" for higher grades)
    # ------------------------------------------------------------------
    def test_all_correct(self):
        words = get_word_list(self.grade)

        # answer every word correctly
        answers = [
            {
                "word": w["word"],
                "user_input": w["word"],          # correct
                "type": w["type"],
                "time": 1.0,
                "hints_used": 0,
            }
            for w in words
        ]

        result = submit_answers(self.id_token, self.child_id, self.grade, answers)
        eval_ = result["evaluation"]

        self.assertEqual(eval_["status"], "At")          # Kindergarten expects "At"
        self.assertEqual(eval_["correct_count"], len(words))

    # ------------------------------------------------------------------
    # 2. ALL WRONG → status = "Below"
    # ------------------------------------------------------------------
    def test_all_wrong(self):
        words = get_word_list(self.grade)

        answers = [
            {
                "word": w["word"],
                "user_input": "xxxx",               # obviously wrong
                "type": w["type"],
                "time": 1.0,
                "hints_used": 0,
            }
            for w in words
        ]

        result = submit_answers(self.id_token, self.child_id, self.grade, answers)
        eval_ = result["evaluation"]

        self.assertEqual(eval_["status"], "Below")
        self.assertEqual(eval_["correct_count"], 0)

    # ------------------------------------------------------------------
    # 3. EXACTLY 2 CORRECT → status = "Below"
    # ------------------------------------------------------------------
    def test_two_correct(self):
        words = get_word_list(self.grade)
        # make first two correct, the rest wrong
        answers = []
        for i, w in enumerate(words):
            answers.append(
                {
                    "word": w["word"],
                    "user_input": w["word"] if i < 2 else "xxxx",
                    "type": w["type"],
                    "time": 1.0,
                    "hints_used": 0,
                }
            )

        result = submit_answers(self.id_token, self.child_id, self.grade, answers)
        eval_ = result["evaluation"]

        self.assertEqual(eval_["correct_count"], 2)
        self.assertEqual(eval_["status"], "Below")   # < 70 %

    # ------------------------------------------------------------------
    # 4. 70 % CORRECT → status = "At"
    # ------------------------------------------------------------------
    def test_seventy_percent_correct(self):
        words = get_word_list(self.grade)
        total = len(words)
        correct_needed = int(total * 0.70)               # at least 70 %

        answers = []
        for i, w in enumerate(words):
            answers.append(
                {
                    "word": w["word"],
                    "user_input": w["word"] if i < correct_needed else "xxxx",
                    "type": w["type"],
                    "time": 1.0,
                    "hints_used": 0,
                }
            )

        result = submit_answers(self.id_token, self.child_id, self.grade, answers)
        eval_ = result["evaluation"]

        self.assertGreaterEqual(eval_["correct_count"], correct_needed)
        self.assertEqual(eval_["status"], "At")

    # ------------------------------------------------------------------
    # 5. 81 % CORRECT → status = "Above"
    # ------------------------------------------------------------------
    def test_above_grade(self):
        words = get_word_list(self.grade)
        total = len(words)
        correct_needed = int(total * 0.81)               # > 80 %

        answers = []
        for i, w in enumerate(words):
            answers.append(
                {
                    "word": w["word"],
                    "user_input": w["word"] if i < correct_needed else "xxxx",
                    "type": w["type"],
                    "time": 1.0,
                    "hints_used": 0,
                }
            )

        result = submit_answers(self.id_token, self.child_id, self.grade, answers)
        eval_ = result["evaluation"]

        self.assertGreaterEqual(eval_["correct_count"], correct_needed)
        self.assertEqual(eval_["status"], "Above")

    # ------------------------------------------------------------------
    # 6. FINAL REPORT – grade band & placement
    # ------------------------------------------------------------------
    def test_grade_band_and_placement(self):
        # Use a **perfect** submission so the band is “At/Above”
        words = get_word_list(self.grade)

        perfect = [
            {
                "word": w["word"],
                "user_input": w["word"],
                "type": w["type"],
                "time": 1.0,
                "hints_used": 0,
            }
            for w in words
        ]

        submit_answers(self.id_token, self.child_id, self.grade, perfect)

        report = get_complete_result(self.id_token, self.child_id, self.grade)
        band = report["parent_summary"]["grade_band"]

        self.assertEqual(band["band"], "K-3rd")
        self.assertEqual(band["placement"], "At/Above Grade Level")
        self.assertIn(band["next_step"], ["Continue current grade", "Unlock next assessment"])

    # ------------------------------------------------------------------
    # 7. NEGATIVE – invalid grade in submit_words → 400
    # ------------------------------------------------------------------
    def test_submit_invalid_grade(self):
        words = get_word_list(self.grade)

        payload = {
            "idToken": self.id_token,
            "child_id": self.child_id,
            "grade": "GarbageGrade",
            "words": [{"word": words[0]["word"], "user_input": words[0]["word"], "type": words[0]["type"], "time": 1.0, "hints_used": 0}],
        }
        resp = requests.post(f"{BASE_URL}/submit_words/", headers=HEADERS, data=json.dumps(payload))
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)