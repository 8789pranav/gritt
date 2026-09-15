"""Bug List v2 verification: all four activities, then the letter, on localhost.

Signs in as a real user with a service-account custom token, submits every
activity fresh against a locally running server, then generates the Learning
Snapshot and checks each bug from the list against the live response.

    python scripts/run_local_flow_v2.py [base_url]

Results are appended, never overwritten: ScoreRepository.save() pushes a new
key per run.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "Z:/grittt")

import requests

from app.core.config import get_settings
from app.domain.enums import Grade
from app.engines.registry import comprehension_engine, logic_engine, spelling_engine

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
UID = "7t3NsqdNjsazVdMAUrC2tC8xvpz1"
CHILD_ID = "bad5ef52-f131-4859-a997-21d210fb23c9"
GRADE = "Second"

#: The run from the bug report: every sound right, the rule not yet met.
SPELLING_ATTEMPTS = {
    "clunk": "clunck",
    "graph": "graff",
    "phone": "fone",
    "coast": "cost",
    "climax": "climacks",
    "said": "sed",
}

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(bug: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, bug, detail))
    print(f"  [{PASS if ok else FAIL}] {bug}{(' - ' + detail) if detail else ''}")


def post(path: str, payload: dict, timeout: int = 180):
    return requests.post(f"{BASE}{path}", json=payload, timeout=timeout)


def banner(text: str) -> None:
    print(f"\n{'=' * 72}\n  {text}\n{'=' * 72}")


# ---------------------------------------------------------------------------
# 0. A real ID token, minted from the service account
# ---------------------------------------------------------------------------
banner("STEP 0: sign in")

import firebase_admin
from firebase_admin import auth as fb_auth

from app.infrastructure.firebase import get_firebase_client

get_firebase_client()  # initialises the admin app
custom_token = fb_auth.create_custom_token(UID).decode()
api_key = get_settings().firebase.api_key
r = requests.post(
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
    params={"key": api_key},
    json={"token": custom_token, "returnSecureToken": True},
    timeout=30,
)
r.raise_for_status()
ID_TOKEN = r.json()["idToken"]
print(f"  Signed in as {UID}")
print(f"  Child {CHILD_ID} (Grade {GRADE})")
print(f"  Server {BASE}")


# ---------------------------------------------------------------------------
# 1. Logic Quest
# ---------------------------------------------------------------------------
banner("STEP 1: LOGIC QUEST")

items = logic_engine().get_items(Grade.SECOND)
r = post("/logic/get_test/", {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE})
r.raise_for_status()
print(f"  Questions: {len(r.json()['items'])}")

responses = []
for item in items:
    missed = item.item_type in ("rule_boundary", "dual_rule")
    responses.append(
        {
            "item_id": item.item_id,
            "selected_answer_index": (item.correct_answer_index + 1) % len(item.options)
            if missed
            else item.correct_answer_index,
            "response_time_seconds": 11.0 if item.item_type == "combining" else 7.0,
            "attempts": 1,
            "self_corrected": False,
        }
    )

r = post(
    "/logic/submit_test/",
    {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE, "responses": responses},
)
r.raise_for_status()
logic = r.json()
print(f"  Correct: {logic['correct_answers']}/{logic['total_items']}")
print(f"  Tags: {[t['tag'] for t in logic['dear_parent_tags']]}")

r = post("/logic/complete_result/", {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE})
r.raise_for_status()
logic_result = r.json()

accuracy = logic_result["parent_summary"]["overall_accuracy"]
expected = round(logic_result["correct_answers"] / logic_result["total_items"] * 100, 1)
check("L-D11 parent accuracy is not 0", accuracy == expected and accuracy > 0,
      f"reads {accuracy}")

logic_tag_ids = {t.id for t in __import__(
    "app.tagging.config_loader", fromlist=["x"]).load_tag_config(
    __import__("app.domain.enums", fromlist=["x"]).TestType.LOGIC).tags}
wrong_rows = [r for r in logic_result["teacher_admin_detail"]["table_data"] if not r["correct"]]
bad = [r["error_type"] for r in wrong_rows if r["error_type"] in logic_tag_ids
       or "_" in (r["error_type"] or "")]
check("L-D12 teacher table prints plain English", not bad,
      f"{[r['error_type'] for r in wrong_rows]}")

check("L-D13 hard item counts are counted as shown",
      logic["signals"]["pattern_hard_count"] == 0
      and logic["signals"]["systematic_hard_count"] == 2,
      f"pattern={logic['signals']['pattern_hard_count']} "
      f"systematic={logic['signals']['systematic_hard_count']}")

double = []
for entry in logic["per_item_tags"]:
    tags = set(entry["tags"])
    for tag in tags:
        if tag.endswith("_missed") and tag[: -len("_missed")] in tags:
            double.append(entry["item_id"])
check("L-D14 one outcome tag per question", not double, f"{double}")

growth = [t["tag"] for t in logic["dear_parent_tags"] if t["polarity"] == "growth_edge"]
check("L-D15 one weakness is not counted twice",
      not any("rule_maintenance" in t for t in growth), f"{growth}")


# ---------------------------------------------------------------------------
# 2. Word Wizard
# ---------------------------------------------------------------------------
banner("STEP 2: WORD WIZARD")

words = spelling_engine().get_items(Grade.SECOND)
r = post(
    "/submit_words/",
    {
        "idToken": ID_TOKEN,
        "child_id": CHILD_ID,
        "grade": GRADE,
        "words": [
            {
                "word": w.word,
                "user_input": SPELLING_ATTEMPTS.get(w.word, w.word),
                "type": w.word_type.value,
                "time": 8.0,
                "hints_used": 0,
            }
            for w in words
        ],
    },
)
r.raise_for_status()
spelling = r.json()
print(f"  Tags: {[t['tag'] for t in spelling['dear_parent_tags']]}")

r = post("/complete_result/", {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE})
r.raise_for_status()
spelling_result = r.json()
summary = spelling_result["parent_summary"]
print(f"  Words correct: {summary['words_correct']}/{summary['words_total']}")
print(f"  overall_accuracy {summary['overall_accuracy']}  "
      f"sound_accuracy {summary['sound_accuracy']}")

check("#76 overall_accuracy counts whole words",
      summary["overall_accuracy"]
      == round(summary["words_correct"] / summary["words_total"] * 100),
      f"{summary['overall_accuracy']}")
check("#76 the sound figure has its own name and explanation",
      "sound_accuracy" in summary and bool(summary.get("sound_accuracy_note")))

table = {row["word"]: row["attempt"] for row in
         spelling_result["teacher_admin_detail"]["table_data"]}
check("Part 4 the words and attempts are in the payload",
      table.get("clunk") == "clunck" and table.get("graph") == "graff"
      and table.get("phone") == "fone",
      "clunck / graff / fone")
check("Spelling conventions tag still fires",
      "spelling_convention_emerging" in
      {t["tag"] for t in spelling["dear_parent_tags"]})


# ---------------------------------------------------------------------------
# 3. Story Explorer
# ---------------------------------------------------------------------------
banner("STEP 3: STORY EXPLORER")

stories = comprehension_engine().get_items(Grade.SECOND)
story_answers = []
for story in stories:
    answers = []
    for q in story.questions:
        right = q.question_type.value == "inferential" or q.question_id in (
            "s1_q1", "s2_q1", "s1_q6",
        )
        answers.append(
            {
                "question_id": q.question_id,
                "selected_index": q.correct_index if right
                else (q.correct_index + 1) % len(q.options),
                "response_time_seconds": 12.5,
            }
        )
    story_answers.append({"story_id": story.story_id, "answers": answers})

r = post(
    "/comprehension/submit/",
    {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE,
     "story_answers": story_answers},
)
r.raise_for_status()
comprehension = r.json()
print(f"  Correct: {comprehension['correct_answers']}/{comprehension['total_questions']}")
print(f"  Tags: {[t['tag'] for t in comprehension['dear_parent_tags']]}")

r = post("/comprehension/complete_result/",
         {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE})
r.raise_for_status()
comprehension_result = r.json()

times = [row["time"] for row in comprehension_result["teacher_admin_detail"]["table_data"]]
check("C5 response times are filled", all(t == 12.5 for t in times), f"{times[:3]}...")

kinds = {q["question_type"] for s in comprehension_result["story_breakdown"]
         for q in s["questions"]}
check("Part 4 the breakdown says what kind each question was",
      kinds <= {"literal", "inferential", "vocabulary"} and kinds, f"{sorted(kinds)}")

rust_story = next(s for s in stories if "rust" in s.story_text)
rust_sentence = next(s for s in rust_story.story_text.split(".") if "rust" in s)
check("S5 the rust passage gives a clue", "reddish-brown" in rust_sentence.lower(),
      rust_sentence.strip()[:70] + "...")


# ---------------------------------------------------------------------------
# 4. Voice Challenge
# ---------------------------------------------------------------------------
banner("STEP 4: VOICE CHALLENGE")

r = post("/speaking/get_all_sentences/",
         {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE})
r.raise_for_status()
sentences = r.json()["sentences"]
print(f"  Sentences: {len(sentences)} (reading each one back as audio)")

# The Azure chain scores WAV. The cached sentence audio is MP3, which is what
# the child HEARS; a recording of a child is WAV, which is what the client
# sends. So the stand-in recordings are synthesised as WAV here.
import base64 as _b64
import openai as _openai

_client = _openai.OpenAI(api_key=get_settings().openai.api_key)


def read_aloud(text: str) -> str:
    """A stand-in for a child reading one sentence, as WAV."""
    audio = _client.audio.speech.create(
        model="tts-1", voice="nova", input=text, response_format="wav", speed=0.95
    )
    return _b64.b64encode(audio.content).decode()


submissions = []
for s in sentences:
    print(f"    recording {s['sentence_id']}...")
    submissions.append(
        {
            "sentence_id": s["sentence_id"],
            "original_sentence": s["sentence"],
            "audio_base64": read_aloud(s["sentence"]),
            "audio_format": "wav",
            "time_to_speak_ms": 900.0,
        }
    )
print(f"  Submitting {len(submissions)} recordings...")

r = post(
    "/speaking/submit/",
    {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE,
     "submissions": submissions},
    timeout=300,
)
r.raise_for_status()
speaking = r.json()
print(f"  Answered: {speaking['answered_count']}")
print(f"  Tags: {[t['tag'] for t in speaking['dear_parent_tags']]}")
print(f"  wcpm {speaking['signals']['wcpm']} band {speaking['signals']['wcpm_band']}")

r = post("/speaking/complete_result/",
         {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE})
r.raise_for_status()
speaking_result = r.json()

banned = ("level", "grade_placement", "instructional_level", "percentage",
          "user_score", "total_marks")
present = [f for f in banned if f in speaking]
for section in ("summary", "parent_summary", "teacher_admin_detail"):
    present += [f"{section}.{f}" for f in banned if f in speaking_result[section]]
check("A11 no labels, placement or scores in Voice Challenge", not present, f"{present}")

text = json.dumps(speaking_result)
labels = [l for l in ("Excellent Speaker", "Good Speaker", "Above Grade Level",
                      "At Grade Level", "Below Grade Level") if l in text]
check("A11 no speaker label survives anywhere", not labels, f"{labels}")

speaking_tags = {t["tag"] for t in speaking["dear_parent_tags"]}
check("Part 5 a reading pace tag fires",
      any(t.startswith("reading_pace_") for t in speaking_tags),
      f"{[t for t in speaking_tags if t.startswith('reading_pace_')]}")

pauses = speaking["signals"]["total_pause_count"]
print(f"  A8 pause detection: total_pause_count={pauses}, "
      f"long={speaking['signals']['total_long_pause_count']}")

tips = [s["analysis"]["parent_tip"] for s in speaking["sentences"]
        if s.get("answered") and s["analysis"].get("parent_tip")]
check("Part 4 parent tips are generated and available", bool(tips),
      (tips[0][:60] + "...") if tips else "none")


# ---------------------------------------------------------------------------
# 5. The Learning Snapshot
# ---------------------------------------------------------------------------
banner("STEP 5: LEARNING SNAPSHOT")

r = post("/snapshot/", {"idToken": ID_TOKEN, "child_id": CHILD_ID, "grade": GRADE},
         timeout=300)
r.raise_for_status()
snapshot = r.json()
letter = snapshot["snapshot"]

out = "C:/Users/WIN/AppData/Local/Temp/claude/z--grittt/793245ad-dce5-4dbf-b8a2-070ceb702144/scratchpad/letter.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(snapshot, f, indent=2, ensure_ascii=False)
print(f"  Letter written to {out}")

meta = letter["meta"]
print(f"  llm_generated {meta['llm_generated']}  "
      f"guardrails_passed {meta['guardrails_passed']}")
print(f"  growth edges found {meta['growth_edges_found']}  "
      f"written {meta['growth_edges_written']}")

check("Letter came from the model, not the fallback", meta["llm_generated"])
covered = {
    name
    for item in letter.get("still_growing") or []
    for name in item.get("signals") or []
}
check("LS9 every growth edge reached the parent",
      len(covered) >= meta["growth_edges_found"],
      f"{len(covered)} signals covered, {meta['growth_edges_found']} found")
check("Growth edges are grouped into something a parent can act on",
      1 <= meta["growth_edges_written"] <= 5,
      f"{meta['growth_edges_written']} sections")

body = json.dumps(letter, ensure_ascii=False)
check("LS3 no Listening Channel", "Listening" not in body)
check("LS5 no 'what helped' section", "what_helped" not in letter)
check("LS5 full_picture is merged away", "full_picture" not in letter)
check("LS6 no invented week", "this week" not in body.lower()
      and "our sessions" not in body.lower())
_re = __import__("re")
if meta.get("pronouns_known"):
    check(f"Written in the singular ({meta['pronouns']}/...)",
          not _re.search(r"\b(they|them|their)\b", body, _re.I))
else:
    check("No pronoun is guessed for a child whose profile does not say",
          not _re.search(r"\b(he|she|his|her|him)\b", body, _re.I))
check("No count of what the child got right or wrong", not _re.search(
    r"\b(all|only)\s+(\d+|fifteen|fourteen|thirteen|twelve|eleven|ten|nine|"
    r"eight|seven|six|five|four|three|two)\s+"
    r"(words?|questions?|puzzles?|sentences?)\b", body, _re.I)
      and not _re.search(r"\d+\s*(%|out of\s*\d+)", body))

opening = " ".join(str(v) for v in (letter.get("opening") or {}).values())
ACTIVITY_NAMES = json.load(
    open("data/tags/learning_areas.json", encoding="utf-8")
)["test_display_names"].values()
check("The opening names no activity",
      not any(a.lower() in opening.lower() for a in ACTIVITY_NAMES))
check("The opening says what the child did, not what the child is",
      not _re.search(r"ha[sd] (a|an) (knack|keen eye|gift)|is a (strong|natural)",
                     opening, _re.I))
check("The letter is framed as a letter",
      letter.get("salutation") and letter.get("signature")
      and letter.get("caveat"))
check("LS10 no invented signal name 'Adaptability'", "Adaptability" not in body)
check("Eko's voice: no exclamation marks", "!" not in body)
check("Conference section is present and has three items",
      len((letter.get("for_the_conference") or {}).get("items") or []) == 3)
check("Every conference item ends with a question to ask",
      all(i.get("worth_asking") for i in
          (letter.get("for_the_conference") or {}).get("items") or []))

quoted = [w for w in ("fone", "graff", "clunck") if w in body]
check("The letter quotes what the child actually wrote", bool(quoted), f"{quoted}")

conventions_named = any(
    "spelling" in json.dumps(item, ensure_ascii=False).lower()
    for item in letter.get("still_growing", [])
)
check("LS9 the spelling conventions finding reached the parent", conventions_named)


# ---------------------------------------------------------------------------
banner("THE LETTER")
print(f"\n{letter['opening']['headline']}\n")
print(letter["opening"]["paragraph"])

for item in letter.get("what_i_noticed", []):
    print(f"\n--- {item.get('headline', '')}")
    print(f"    [{', '.join(item.get('signals') or [])}] "
          f"seen in {', '.join(item.get('seen_in') or [])} "
          f"({item.get('badge', '')})")
    print(f"    {item.get('paragraph', '')}")

print(f"\n\n### STILL GROWING ({len(letter.get('still_growing', []))})")
for item in letter.get("still_growing", []):
    print(f"\n--- {item.get('headline', '')}")
    print(f"    [{', '.join(item.get('signals') or [])}] "
          f"seen in {', '.join(item.get('seen_in') or [])}")
    print(f"    {item.get('paragraph', '')}")
    s = item.get("suggestion") or {}
    print(f"    TRY: {s.get('title', '')} - {s.get('body', '')}")
    print(f"    {s.get('because', '')}")

conference = letter.get("for_the_conference") or {}
print(f"\n\n### {conference.get('headline', '')}")
for i, item in enumerate(conference.get("items") or [], 1):
    print(f"\n{i}. {item.get('point', '')}")
    print(f"   {item.get('worth_asking', '')}")

print(f"\n\n{letter.get('closing', '')}")
print(f"\n{letter.get('disclaimer', '')}")


# ---------------------------------------------------------------------------
banner("RESULT")
failed = [r for r in results if r[0] == FAIL]
for status, bug, detail in results:
    print(f"  [{status}] {bug}")
print(f"\n  {len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
