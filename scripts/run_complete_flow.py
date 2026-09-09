"""Complete end-to-end flow:
1. Login
2. Submit all 4 tests (logic, spelling, speaking, comprehension)
3. Call each test's complete-result API
4. Generate the Learning Snapshot letter
5. Show everything
"""
import sys
sys.path.insert(0, "Z:/grittt")

import json
import time
import requests

BASE = "https://nvupmmyd66.us-east-1.awsapprunner.com"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else "Test@123"
CHILD_ID = sys.argv[2] if len(sys.argv) > 2 else "242cfda1-9b36-4d0b-bf5b-e930c086e435"
GRADE = "Second"

def post(path, payload, timeout=120):
    r = requests.post(f"{BASE}{path}", json=payload, timeout=timeout)
    return r

def show(title, obj, keys=None):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    if keys:
        for k in keys:
            v = obj.get(k, "") if isinstance(obj, dict) else ""
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)[:200]
            print(f"  {k}: {v}")
    else:
        print(json.dumps(obj, indent=2, ensure_ascii=False)[:2000])


# =====================================================================
# 1. LOGIN
# =====================================================================
print("=" * 70)
print("  STEP 1: LOGIN")
print("=" * 70)
r = post("/login", {"email": EMAIL, "password": PASSWORD})
assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
id_token = r.json().get("id_token") or r.json().get("token")
print(f"  Logged in: {id_token[:25]}...")
print(f"  Child: {CHILD_ID}")
print(f"  Grade: {GRADE}")


# =====================================================================
# 2. LOGIC — get test, submit with varied answers and times
# =====================================================================
print(f"\n{'='*70}")
print(f"  STEP 2: LOGIC QUEST — submit test")
print(f"{'='*70}")

r = post("/logic/get_test/", {"idToken": id_token, "child_id": CHILD_ID, "grade": GRADE})
assert r.status_code == 200, f"get_test failed: {r.status_code}"
items = r.json().get("items", [])
print(f"  Questions: {len(items)}")

# Answer pattern: mostly correct, #3 and #7 wrong; #1 fast, #5 very slow
responses = []
for i, item in enumerate(items):
    correct_idx = item.get("correct_answer_index", 0)
    selected = correct_idx
    if i in (2, 6):  # 3rd and 7th wrong
        selected = (correct_idx + 1) % 4
    t = 10.0
    if i == 0:
        t = 3.0   # fast
    elif i == 4:
        t = 55.0  # slow and careful
    responses.append({
        "item_id": item.get("item_id", ""),
        "selected_answer_index": selected,
        "response_time_seconds": t,
    })

r = post("/logic/submit_test/", {
    "idToken": id_token, "child_id": CHILD_ID,
    "grade": GRADE, "responses": responses,
})
assert r.status_code == 200, f"submit failed: {r.status_code} {r.text[:300]}"
logic_result = r.json()
print(f"  Correct: {logic_result.get('correct_answers')}/{logic_result.get('total_items')}")
tags = logic_result.get("dear_parent_tags", [])
print(f"  Tags: {[t.get('id') for t in tags]}")
strengths = logic_result.get("parent_summary", {}).get("strengths", [])
print(f"  Strengths: {strengths[:3]}")

# Complete result
r = post("/logic/complete_result/", {"idToken": id_token, "child_id": CHILD_ID, "grade": GRADE})
print(f"  complete_result: {r.status_code}")


# =====================================================================
# 3. SPELLING — get words, submit with a mix of correct and convention errors
# =====================================================================
print(f"\n{'='*70}")
print(f"  STEP 3: WORD WIZARD — submit test")
print(f"{'='*70}")

r = post("/grade/", {"grade": GRADE})
assert r.status_code == 200, f"get words failed: {r.status_code}"
words = r.json().get("words", [])
print(f"  Words: {len(words)}")

# Answer pattern: mostly correct, 3 convention-style errors
CONVENTION_SWAPS = {
    "candle": "kandle", "outline": "owtline", "perplex": "purplex",
    "clunk": "clunck", "shower": "shouwer",
}
word_submissions = []
convention_done = 0
for w in words:
    word_text = w.get("word", "")
    user_input = word_text
    if word_text in CONVENTION_SWAPS and convention_done < 3:
        user_input = CONVENTION_SWAPS[word_text]
        convention_done += 1
    word_submissions.append({
        "word": word_text,
        "user_input": user_input,
        "type": w.get("type", "phonics"),
        "time": 8.0,
        "hints_used": 0,
    })

r = post("/submit_words/", {
    "idToken": id_token, "child_id": CHILD_ID,
    "grade": GRADE, "words": word_submissions,
})
assert r.status_code == 200, f"submit failed: {r.status_code} {r.text[:300]}"
spelling_result = r.json()
print(f"  Correct: {spelling_result.get('correct_answers')}/{spelling_result.get('total_items')}")
tags = spelling_result.get("dear_parent_tags", [])
print(f"  Tags: {[t.get('id') for t in tags]}")
strengths = spelling_result.get("parent_summary", {}).get("strengths", [])
print(f"  Strengths: {strengths[:3]}")

# Complete result
r = post("/complete_result/", {"idToken": id_token, "child_id": CHILD_ID, "grade": GRADE})
print(f"  complete_result: {r.status_code}")


# =====================================================================
# 4. COMPREHENSION — get stories, submit with mostly correct answers
# =====================================================================
print(f"\n{'='*70}")
print(f"  STEP 4: STORY EXPLORER — submit test")
print(f"{'='*70}")

r = post("/comprehension/get_stories/", {
    "idToken": id_token, "child_id": CHILD_ID, "grade": GRADE
})
assert r.status_code == 200, f"get_stories failed: {r.status_code}"
stories = r.json().get("stories", [])
total_qs = sum(len(s.get("questions", [])) for s in stories)
print(f"  Stories: {len(stories)}, Questions: {total_qs}")

# Answer pattern: all correct except question 4 of story 1
story_answers = []
q_idx = 0
for s in stories:
    answers = []
    for q in s.get("questions", []):
        selected = 0
        if q_idx == 3:  # 4th question wrong
            selected = 1
        answers.append({
            "question_id": q.get("id", q.get("question_id", "")),
            "selected_index": selected,
            "response_time_seconds": 12.0,
        })
        q_idx += 1
    story_answers.append({"story_id": s.get("story_id", ""), "answers": answers})

r = post("/comprehension/submit/", {
    "idToken": id_token, "child_id": CHILD_ID,
    "grade": GRADE, "story_answers": story_answers,
})
assert r.status_code == 200, f"submit failed: {r.status_code} {r.text[:300]}"
comp_result = r.json()
print(f"  Correct: {comp_result.get('correct_answers')}/{comp_result.get('total_questions')}")
tags = comp_result.get("dear_parent_tags", [])
print(f"  Tags: {[t.get('id') for t in tags]}")
strengths = comp_result.get("parent_summary", {}).get("strengths", [])
print(f"  Strengths: {strengths[:3]}")

# Complete result
r = post("/comprehension/complete_result/", {"idToken": id_token, "child_id": CHILD_ID, "grade": GRADE})
print(f"  complete_result: {r.status_code}")


# =====================================================================
# 5. SPEAKING — get sentence, TTS, analyze, submit
# =====================================================================
print(f"\n{'='*70}")
print(f"  STEP 5: VOICE CHALLENGE — submit test")
print(f"{'='*70}")

# Get a sentence
r = post("/speaking/get_sentence/", {"idToken": id_token, "child_id": CHILD_ID, "grade": GRADE})
if r.status_code == 200:
    sentence_data = r.json()
    sentence = sentence_data.get("sentence", sentence_data.get("text", "The cat sat on the mat."))
    print(f"  Sentence: {sentence[:60]}...")

    # TTS the sentence (simulating the child reading it)
    r = post("/generate_text_audio/", {"idToken": id_token, "text": sentence}, timeout=60)
    if r.status_code == 200:
        audio_b64 = r.json().get("base64_audio", "")
        print(f"  TTS audio: {len(audio_b64)} chars")

        # Analyze
        r = post("/speaking/analyze/", {
            "idToken": id_token, "child_id": CHILD_ID,
            "grade": GRADE, "original_sentence": sentence,
            "audio_base64": audio_b64, "audio_format": "mp3",
        }, timeout=120)
        if r.status_code == 200:
            analysis = r.json()
            print(f"  Analyze: {r.status_code}")
            overall = analysis.get("overall", {})
            print(f"  Overall score: {overall.get('score', 'N/A')}")

            # Submit the analyzed result
            r = post("/speaking/submit/", {
                "idToken": id_token, "child_id": CHILD_ID,
                "grade": GRADE,
                "original_sentence": sentence,
                "audio_base64": audio_b64,
                "audio_format": "mp3",
            }, timeout=120)
            print(f"  Submit: {r.status_code}")
            if r.status_code == 200:
                spk = r.json()
                tags = spk.get("dear_parent_tags", [])
                print(f"  Tags: {[t.get('id') for t in tags]}")
        else:
            print(f"  Analyze failed: {r.status_code} {r.text[:200]}")
    else:
        print(f"  TTS failed: {r.status_code}")
else:
    print(f"  get_sentence failed: {r.status_code}")

# Complete result
r = post("/speaking/complete_result/", {"idToken": id_token, "child_id": CHILD_ID, "grade": GRADE})
print(f"  complete_result: {r.status_code}")


# =====================================================================
# 6. GENERATE THE LEARNING SNAPSHOT
# =====================================================================
print(f"\n{'='*70}")
print(f"  STEP 6: LEARNING SNAPSHOT — generate letter")
print(f"{'='*70}")

from app.services.snapshot_service import SnapshotService
from app.services.snapshot_writer import SnapshotWriter
from app.core.security import verify_paid_child
from unittest.mock import patch

svc = SnapshotService()
uid, child_data = verify_paid_child(id_token, CHILD_ID)
child_name = child_data.get("name", "")

with patch("app.services.snapshot_service.verify_paid_child",
           return_value=(uid, {"name": child_name})):
    evidence = svc.build_evidence(id_token, CHILD_ID, GRADE)

print(f"  Child: {child_name}")
print(f"  Tests: {evidence['tests_completed']}")
print(f"  Strengths: {len(evidence['observations'])}")
print(f"  Growth edges: {len(evidence['growth_edges'])}")
for obs in evidence["observations"]:
    print(f"    + {obs['area_display_name']} ({obs['evidence_strength']}) in {obs['seen_in']}")
for obs in evidence["growth_edges"]:
    print(f"    - {obs['area_display_name']} ({obs['evidence_strength']}) in {obs['seen_in']}")

print(f"\n  Calling LLM to write the letter...")
writer = SnapshotWriter()
letter = writer.write(evidence)

response = {
    "success": True,
    "child_id": CHILD_ID,
    "child_name": child_name,
    "grade": GRADE,
    "tests_completed": evidence["tests_completed"],
    "snapshot": letter,
}

print(f"\n{'='*70}")
print(f"  FINAL RESPONSE: POST /snapshot/")
print(f"{'='*70}")
print(json.dumps(response, indent=2, ensure_ascii=False))
