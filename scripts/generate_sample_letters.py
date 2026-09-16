"""Every kind of Learning Snapshot, through the whole workflow.

Three children - one who found the set easy, one mixed, one who found it hard
- each doing all four activities and then getting a letter. Every step is
reported as it happens: what the child answered, what the engine scored, which
tags fired, and then the letter those tags produced.

Nothing here is a fixture of a letter. The answers go through the real
endpoints, the tags are whatever the engines decide, and the prose is whatever
the model writes. The point is to read a real letter for a child who got most
things wrong, which is the case no guardrail can prove and no test set covers.

Two ways to run it.

    python scripts/generate_sample_letters.py
        In-process. Firebase is in memory, the speech chain is stood in for,
        nothing outside this machine is touched except the model that writes
        the letter. Fast, free of side effects, and the default.

    python scripts/generate_sample_letters.py --base http://127.0.0.1:8099
        Against a real server on localhost: real Firebase, real AWS speech
        scoring real synthesised audio, real letter. This WRITES SCORES to
        the child it names, so it takes a --child and tells you which one.

    python scripts/generate_sample_letters.py strong mixed --out letters/

Needs OPENAI either way: a stubbed letter proves nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# The three children
# ---------------------------------------------------------------------------
PROFILES: Dict[str, Dict[str, Any]] = {
    "strong": {
        "label": "Strong - found the set comfortable",
        "child": {"name": "Vedika", "age": 8, "grade": "Third", "gender": "girl"},
        "watch_for": (
            "A near-perfect run must still produce honest growth edges, and "
            "a note that this level did not stretch her."
        ),
        "misspell": {},
        "misspell_share": 0.0,
        "leave_blank": [],
        "blank_share": 0.0,
        "logic_miss_share": 0.07,
        "logic_seconds": {"combining": 33.0, "default": 6.0},
        "comprehension_miss": "vocabulary_only",
        "speaking": {
            "accuracy": 94.0, "fluency": 92.0, "prosody": 88.0,
            "completeness": 100.0, "wcpm": 128.0, "band": "in_band",
            "omission": 0, "mispronunciation": 1, "prolonged": 2,
            "phonics": {"consonant_blend": 88.0},
        },
        # How a stand-in recording is made when running against a real server.
        "reading": {"speed": 1.0, "drop_every": 0, "swap": {}},
    },
    "mixed": {
        "label": "Mixed - secure in places, still settling in others",
        "child": {"name": "Manju", "age": 7, "grade": "Second", "gender": "boy"},
        "watch_for": (
            "Several read-aloud findings must group into ONE thing to work "
            "on, and the letter should connect his spelling to his speech."
        ),
        "misspell": {
            "strand": "stand", "graph": "drew", "phone": "firm",
            "climax": "climacks", "clunk": "clunck",
        },
        "misspell_share": 0.3,
        "leave_blank": ["quaint"],
        "blank_share": 0.07,
        "logic_miss_share": 0.25,
        "logic_seconds": {"combining": 65.0, "default": 11.0},
        "comprehension_miss": "none",
        "speaking": {
            "accuracy": 82.0, "fluency": 74.0, "prosody": 69.8,
            "completeness": 96.0, "wcpm": 78.0, "band": "in_band",
            "omission": 1, "mispronunciation": 4, "prolonged": 1,
            "phonics": {"consonant_blend": 76.4, "consonant_digraph": 79.0,
                        "long_vowel": 77.5},
        },
        "reading": {"speed": 0.85, "drop_every": 9,
                    "swap": {"the": "duh", "with": "wif"}},
    },
    "struggling": {
        "label": "Struggling - the set was out of reach",
        "child": {"name": "Sam", "age": 6, "grade": "First", "gender": "boy"},
        "watch_for": (
            "The hardest letter to write. It must open on how he worked "
            "rather than what he missed, find real strengths first, and say "
            "plainly that the level below would suit him better."
        ),
        "misspell": {
            "of": "ov", "my": "mi", "said": "sed", "come": "cum",
            "they": "thay", "was": "wuz", "from": "frum", "hi": "pie",
        },
        "misspell_share": 0.65,
        "leave_blank": ["because", "where"],
        "blank_share": 0.15,
        "logic_miss_share": 0.7,
        "logic_seconds": {"combining": 52.0, "default": 21.0},
        "comprehension_miss": "most",
        "speaking": {
            "accuracy": 61.0, "fluency": 52.0, "prosody": 48.0,
            "completeness": 78.0, "wcpm": 34.0, "band": "below_band",
            "omission": 6, "mispronunciation": 7, "prolonged": 3,
            "phonics": {"consonant_blend": 58.0, "short_vowel": 62.0,
                        "ending_consonant": 64.0},
        },
        "reading": {"speed": 0.6, "drop_every": 4,
                    "swap": {"the": "duh", "and": "an", "with": "wif"}},
    },
}

LOCAL_UID = "test-uid"
LOCAL_CHILD = "child-1"

#: The child the repo's own live flow uses. Running live WRITES to it.
LIVE_UID = "7t3NsqdNjsazVdMAUrC2tC8xvpz1"
LIVE_CHILD = "bad5ef52-f131-4859-a997-21d210fb23c9"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def banner(text: str, rule: str = "=") -> None:
    print(f"\n{rule * 74}\n  {text}\n{rule * 74}")


def step(text: str) -> None:
    print(f"\n  --- {text} " + "-" * max(0, 60 - len(text)))


def tag_lines(result: Dict[str, Any]) -> List[str]:
    """The tags an activity fired, as a parent-facing name and a polarity."""
    out = []
    for tag in result.get("dear_parent_tags") or []:
        out.append(
            f"      {tag.get('polarity', '?'):<12} {tag.get('id') or tag.get('tag')}"
            f"  ({tag.get('confidence', '?')})"
        )
    return out or ["      (no tags fired)"]


# ---------------------------------------------------------------------------
# The speech chain, stood in for (in-process mode only)
# ---------------------------------------------------------------------------
def speech_double(profile: Dict[str, Any]):
    spec = profile["speaking"]

    async def fake_analyse_sentence(self, submission, grade):
        from app.engines.speaking.metrics import (
            DisfluencyMetrics, PHONICS_FEATURES, ReadingMetrics, TimingMetrics,
        )

        words = submission.reference_text.rstrip(".").split()
        spoken = max(1, len(words) - (1 if spec["omission"] else 0))
        elapsed = (len(words) / max(spec["wcpm"], 1.0)) * 60.0

        phonics = {name: 90.0 for name in PHONICS_FEATURES}
        phonics.update(spec.get("phonics") or {})

        return {
            "sentence_id": submission.sentence_id,
            "status": "answered",
            "reference": submission.reference_text,
            "recognized": submission.reference_text,
            "verbatim": submission.reference_text.lower(),
            "channel_agreement": 1.0,
            "scores": {
                "accuracy": spec["accuracy"], "fluency": spec["fluency"],
                "completeness": spec["completeness"], "prosody": spec["prosody"],
                "pron_score": round(
                    (spec["accuracy"] + spec["fluency"] + spec["prosody"]) / 3, 1
                ),
            },
            "reading": ReadingMetrics(
                spoken, len(words), spec["completeness"], spec["wcpm"],
                round(elapsed, 1), spec["band"],
            ).as_dict(),
            "timing": {
                **TimingMetrics(
                    elapsed * 1000.0, 1, 0, 210.0, 210.0, 210.0, 4000.0
                ).as_dict(),
                "time_to_speak_ms": submission.time_to_speak_ms or 800.0,
            },
            "disfluency": DisfluencyMetrics([], 0, 0.0, 0, []).as_dict(),
            "phonics": phonics,
            "errors": {
                "omission": spec["omission"], "insertion": 0,
                "mispronunciation": spec["mispronunciation"],
                "unexpected_break": 0,
                "missing_break": 1 if spec["prosody"] < 75 else 0,
                "monotone": 1 if spec["prosody"] < 75 else 0,
                "clear_error": 0, "needs_attention": spec["mispronunciation"],
                "prolonged": spec["prolonged"],
                "words_flagged": spec["mispronunciation"],
            },
            "findings": [], "words": [], "attempt": submission.attempt,
        }

    return fake_analyse_sentence


async def _no_audio(self, text: str, *, speed: float = 1.0):
    """Patched onto the provider itself, so it takes the instance too."""
    return None


def read_aloud(sentence: str, reading: Dict[str, Any]) -> str:
    """A stand-in recording of one child reading one sentence, as WAV.

    A child who is finding it hard does not read the sentence on the page, so
    neither does this: words are dropped and swapped before the audio is made,
    and the server still scores it against the real sentence. The omissions
    and mispronunciations the chain then reports are real measurements of a
    real difference, not numbers we asserted.
    """
    import openai

    from app.core.config import get_settings

    words = sentence.split()
    drop_every = reading.get("drop_every") or 0
    swap = reading.get("swap") or {}

    spoken: List[str] = []
    for index, word in enumerate(words, start=1):
        if drop_every and index % drop_every == 0 and index != 1:
            continue
        bare = word.strip(".,!?").lower()
        spoken.append(swap.get(bare, word))

    client = openai.OpenAI(api_key=get_settings().openai.api_key)
    audio = client.audio.speech.create(
        model="tts-1", voice="nova", input=" ".join(spoken) or sentence,
        response_format="wav", speed=reading.get("speed", 1.0),
    )
    return base64.b64encode(audio.content).decode()


#: How a child who spells by ear writes a word they have not met in print.
#: Every sound stays; only the convention is missing, which is the finding
#: the whole letter is built around.
_BY_EAR = (
    ("ph", "f"), ("ck", "k"), ("tion", "shun"), ("ough", "uf"),
    ("ea", "e"), ("ai", "a"), ("oa", "o"), ("wh", "w"), ("kn", "n"),
    ("wr", "r"), ("mb", "m"), ("ce", "se"), ("ge", "je"),
)


def spell_by_ear(word: str) -> str:
    """What this word looks like written down by sound alone."""
    attempt = word.lower()
    for convention, sound in _BY_EAR:
        if convention in attempt:
            attempt = attempt.replace(convention, sound, 1)
            break
    else:
        # Nothing conventional to miss. A child spelling by ear still writes
        # every sound, so a vowel is never what goes: it is a doubled letter,
        # a silent e, or the middle of a consonant cluster.
        vowels = "aeiou"
        for index in range(len(attempt) - 1):
            if attempt[index] == attempt[index + 1]:
                attempt = attempt[:index] + attempt[index + 1:]
                break
        else:
            if attempt.endswith("e") and len(attempt) > 3:
                attempt = attempt[:-1]
            else:
                for index in range(1, len(attempt) - 1):
                    trio = attempt[index - 1:index + 2]
                    if len(trio) == 3 and not any(c in vowels for c in trio):
                        attempt = attempt[:index] + attempt[index + 1:]
                        break

    if attempt != word.lower():
        return attempt

    # Nothing to drop. A short word goes wrong at the vowel - the sound is
    # there, the letter that spells it is not - which is what a child's
    # spelling actually looks like: wuz for was, cum for come.
    heard_as = {"a": "u", "e": "a", "i": "e", "o": "u", "u": "o"}
    for index, letter in enumerate(attempt):
        if letter in heard_as:
            return attempt[:index] + heard_as[letter] + attempt[index + 1:]
    return attempt


# ---------------------------------------------------------------------------
# Talking to whichever server we are using
# ---------------------------------------------------------------------------
class Session:
    """One child's workflow, against either the in-process app or a server."""

    def __init__(self, client, token: str, child_id: str, grade: str) -> None:
        self._client = client
        self.token = token
        self.child_id = child_id
        self.grade = grade

    async def post(self, path: str, payload: Dict[str, Any],
                   timeout: float = 300.0) -> Dict[str, Any]:
        response = await self._client.post(path, json=payload, timeout=timeout)
        if response.status_code != 200:
            raise RuntimeError(f"{path} -> {response.status_code}: {response.text[:400]}")
        return response.json()

    def ids(self, **extra) -> Dict[str, Any]:
        return {"idToken": self.token, "child_id": self.child_id,
                "grade": self.grade, **extra}


# ---------------------------------------------------------------------------
# The four activities, each reported as it happens
# ---------------------------------------------------------------------------
async def do_spelling(s: Session, profile: Dict[str, Any]) -> Dict[str, Any]:
    step("Word Wizard")
    words = (await s.post("/grade/", {"grade": s.grade}))["words"]

    # The named words are the interesting ones and they are used wherever
    # they come up. But a grade's list is whatever it is, so the profile's
    # SHARE is what decides how the run actually goes: a child who is
    # finding it hard must find this list hard, not a different one.
    blanks = round(len(words) * profile["blank_share"])
    misses = round(len(words) * profile["misspell_share"])

    payload = []
    for index, entry in enumerate(words):
        word = entry["word"]
        if word in profile["leave_blank"] or (blanks and index < blanks):
            attempt, seconds = "", 34.0
        elif word in profile["misspell"]:
            attempt, seconds = profile["misspell"][word], 22.0
        elif misses and blanks <= index < blanks + misses:
            attempt, seconds = spell_by_ear(word), 22.0
        else:
            attempt, seconds = word, 9.0
        payload.append({"word": word, "user_input": attempt,
                        "type": entry.get("type", "regular"),
                        "time": seconds, "hints_used": 0})

    result = await s.post("/submit_words/", s.ids(words=payload))

    wrote = [f"{p['word']}->{p['user_input'] or '(blank)'}"
             for p in payload if p["user_input"] != p["word"]]
    print(f"      {len(payload)} words shown")
    print(f"      wrote differently: {', '.join(wrote) if wrote else 'nothing'}")
    print("\n".join(tag_lines(result)))
    return result


async def do_logic(s: Session, profile: Dict[str, Any]) -> Dict[str, Any]:
    step("Logic Quest")
    from app.domain.enums import Grade
    from app.engines.registry import logic_engine

    shown = (await s.post("/logic/get_test/", s.ids()))["items"]
    by_id = {i.item_id: i for i in logic_engine().get_items(Grade(s.grade))}
    seconds = profile["logic_seconds"]

    # Hardest first: a child who is finding it hard misses the hard ones,
    # not a named item type that may not exist at this grade.
    hardest = sorted(
        range(len(shown)),
        key=lambda i: {"hard": 0, "medium": 1, "easy": 2}.get(
            str(getattr(by_id[shown[i]["item_id"]], "difficulty", "")).lower(), 1
        ),
    )[:round(len(shown) * profile["logic_miss_share"])]

    responses, missed = [], []
    for index, entry in enumerate(shown):
        item = by_id[entry["item_id"]]
        miss = index in hardest
        if miss:
            missed.append(item.item_type)
        responses.append({
            "item_id": item.item_id,
            "selected_answer_index": (item.correct_answer_index + 1)
            % len(item.options) if miss else item.correct_answer_index,
            "response_time_seconds": seconds.get(item.item_type,
                                                 seconds["default"]),
            "attempts": 1, "self_corrected": False,
        })

    result = await s.post("/logic/submit_test/", s.ids(responses=responses))
    print(f"      {len(responses)} puzzles answered, "
          f"{len(missed)} missed ({', '.join(sorted(set(missed))) or 'none'})")
    print("\n".join(tag_lines(result)))
    return result


async def do_comprehension(s: Session, profile: Dict[str, Any]) -> Dict[str, Any]:
    step("Story Explorer")
    from app.domain.enums import Grade
    from app.engines.registry import comprehension_engine

    await s.post("/comprehension/get_stories/", s.ids())
    stories = comprehension_engine().get_items(Grade(s.grade))
    miss = profile["comprehension_miss"]

    story_answers, right_count, total = [], 0, 0
    for story in stories:
        answers = []
        for index, question in enumerate(story.questions):
            kind = question.question_type.value
            if miss == "none":
                right = True
            elif miss == "vocabulary_only":
                right = kind != "vocabulary" or index % 4 != 1
            else:
                right = kind == "inferential" and index % 3 == 0
            right_count += 1 if right else 0
            total += 1
            answers.append({
                "question_id": question.question_id,
                "selected_index": question.correct_index if right
                else (question.correct_index + 1) % len(question.options),
                "response_time_seconds": 9.0 if right else 21.0,
            })
        story_answers.append({"story_id": story.story_id, "answers": answers})

    result = await s.post("/comprehension/submit/",
                          s.ids(story_answers=story_answers))
    print(f"      {len(stories)} stories, {total} questions, "
          f"{total - right_count} missed")
    print("\n".join(tag_lines(result)))
    return result


async def do_speaking(s: Session, profile: Dict[str, Any],
                      live: bool) -> Dict[str, Any]:
    step("Voice Challenge")
    sentences = (await s.post("/speaking/get_all_sentences/", s.ids()))["sentences"]

    submissions = []
    for sentence in sentences:
        if live:
            print(f"      recording {sentence['sentence_id']}...")
            audio = read_aloud(sentence["sentence"], profile["reading"])
        else:
            audio = "ZmFrZS1hdWRpbw=="
        submissions.append({
            "sentence_id": sentence["sentence_id"],
            "original_sentence": sentence["sentence"],
            "audio_base64": audio, "audio_format": "wav",
            "time_to_speak_ms": 900.0,
        })

    result = await s.post("/speaking/submit/", s.ids(submissions=submissions))
    signals = result.get("signals") or {}
    print(f"      {len(submissions)} sentences read")
    print(f"      pace {signals.get('wcpm')} wcpm ({signals.get('wcpm_band')}), "
          f"words skipped {signals.get('omission_count')}, "
          f"sounds stretched {signals.get('prolonged_count')}")
    print("\n".join(tag_lines(result)))
    return result


# ---------------------------------------------------------------------------
# One child, start to finish
# ---------------------------------------------------------------------------
async def run_in_process(key: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import MockFirebaseClient

    firebase = MockFirebaseClient()

    with patch("app.infrastructure.firebase.get_firebase_client",
               return_value=firebase), \
         patch("app.infrastructure.repositories.get_firebase_client",
               return_value=firebase), \
         patch("app.core.security.get_firebase_client", return_value=firebase), \
         patch("firebase_admin.auth.verify_id_token",
               side_effect=lambda token: {"uid": LOCAL_UID,
                                          "email": "parent@test.com"}), \
         patch("app.engines.speaking.pipeline.SpeakingPipeline.analyse_sentence",
               new=speech_double(profile)), \
         patch("app.infrastructure.tts.TTSProvider.synthesize", new=_no_audio):

        firebase.ref(f"users/{LOCAL_UID}").set(
            {"name": "Parent", "email": "parent@test.com", "isAdmin": False})
        firebase.ref(f"users/{LOCAL_UID}/children/{LOCAL_CHILD}").set(
            {**profile["child"], "payment_status": "paid"})

        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://local") as client:
            session = Session(client, "local-token", LOCAL_CHILD,
                              profile["child"]["grade"])
            await run_activities(session, profile, live=False)
            snapshot = await session.post("/snapshot/", {
                "idToken": session.token, "child_id": session.child_id,
                "grade": session.grade,
            })

        from app.services.snapshot_service import SnapshotService
        evidence = SnapshotService().build_evidence(
            session.token, session.child_id, session.grade)

    return {"key": key, "profile": profile, "evidence": evidence,
            "letter": snapshot["snapshot"]}


async def run_live(key: str, profile: Dict[str, Any], base: str,
                   uid: str, child_id: str) -> Dict[str, Any]:
    """Against a real server. This writes scores to a real child."""
    from httpx import AsyncClient

    import firebase_admin  # noqa: F401  (initialised by get_firebase_client)
    from firebase_admin import auth as fb_auth
    import requests

    from app.core.config import get_settings
    from app.infrastructure.firebase import get_firebase_client

    get_firebase_client()
    custom = fb_auth.create_custom_token(uid).decode()
    signed = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
        params={"key": get_settings().firebase.api_key},
        json={"token": custom, "returnSecureToken": True}, timeout=30,
    )
    signed.raise_for_status()
    token = signed.json()["idToken"]

    grade = profile["child"]["grade"]
    async with AsyncClient(base_url=base) as client:
        session = Session(client, token, child_id, grade)
        await run_activities(session, profile, live=True)
        snapshot = await session.post("/snapshot/", {
            "idToken": token, "child_id": child_id, "grade": grade,
        })

    from app.services.snapshot_service import SnapshotService
    evidence = SnapshotService().build_evidence(token, child_id, grade)
    return {"key": key, "profile": profile, "evidence": evidence,
            "letter": snapshot["snapshot"]}


async def run_activities(session: Session, profile: Dict[str, Any],
                         live: bool) -> None:
    await do_spelling(session, profile)
    await do_logic(session, profile)
    await do_comprehension(session, profile)
    await do_speaking(session, profile, live=live)


# ---------------------------------------------------------------------------
# Reading the letter, and checking it
# ---------------------------------------------------------------------------
def render(letter: Dict[str, Any]) -> str:
    out: List[str] = [letter.get("salutation", "Dear Parent,"), ""]

    opening = letter.get("opening") or {}
    out += [opening.get("headline", ""), "", opening.get("paragraph", ""), ""]

    for item in letter.get("what_i_noticed") or []:
        out += [item.get("headline", ""), ""]
        for quote in item.get("quotes") or []:
            out.append(f"    {quote.get('wrote')}  /  for {quote.get('for_word')}")
        if item.get("quotes"):
            out.append("")
        out += [item.get("paragraph", ""), ""]

    if letter.get("still_growing"):
        out += ["Still growing", ""]
    for item in letter.get("still_growing") or []:
        out += [item.get("headline", ""), "", item.get("paragraph", ""), ""]
        suggestion = item.get("suggestion") or {}
        if suggestion.get("title"):
            out.append(f"    {suggestion['title']} {suggestion.get('body', '')}")
        if suggestion.get("because"):
            out.append(f"    {suggestion['because']}")
        out.append("")

    note = letter.get("level_note")
    if note:
        out += [note.get("headline", ""), "", note.get("paragraph", ""), ""]

    conference = letter.get("for_the_conference") or {}
    if conference.get("items"):
        out += [conference.get("headline", ""), ""]
    for item in conference.get("items") or []:
        out += [f"  - {item.get('point', '')}",
                f"    {item.get('worth_asking', '')}"]
    out.append("")

    out += [letter.get("caveat", ""), "", letter.get("signature", "Eko"), "",
            letter.get("disclaimer", "")]
    return "\n".join(out)


_COUNTS = re.compile(
    r"\b(?:all|only|every one of)\s+(?:\d+|one|two|three|four|five|six|seven|"
    r"eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen)\s+"
    r"(?:words?|questions?|puzzles?|sentences?)\b|\d+\s*%|\d+\s*out of\s*\d+",
    re.I,
)
#: The product's own rules, not a second copy of them. A checker that is
#: more forgiving than the thing it checks reports PASS on what the product
#: has already recorded as a violation, which is how a known problem goes
#: unnoticed in a report that says everything is fine.
from app.services.snapshot_writer import (  # noqa: E402
    _ABSTRACT_HEADLINE as _LABELS,
    _OPENING_TALLY as _WORDLESS_TALLY,
)


def inspect(result: Dict[str, Any]) -> List[Tuple[str, bool]]:
    from app.services.snapshot_writer import _prose

    letter, evidence = result["letter"], result["evidence"]
    # The prose only. `meta` carries the violation messages, and those quote
    # example sentences - a check that reads them is checking its own notes.
    body = "\n".join(_prose(letter))
    opening = " ".join(str(v) for v in (letter.get("opening") or {}).values())
    meta = letter.get("meta") or {}
    pronouns = evidence.get("pronouns") or {}

    activities = evidence.get("activities_completed") or []
    covered = {name for item in letter.get("still_growing") or []
               for name in item.get("signals") or []}
    expected = {g["signal_name"] for g in evidence.get("growth_edges") or []}
    conference = (letter.get("for_the_conference") or {}).get("items") or []

    checks = [
        ("came from the model, not the fallback", bool(meta.get("llm_generated"))),
        ("every promise held", bool(meta.get("guardrails_passed"))),
        ("no count of right or wrong anywhere", not _COUNTS.search(body)),
        ("the opening names no activity",
         not any(a.lower() in opening.lower() for a in activities)),
        ("the opening says what the child did, not what they are",
         not _LABELS.search(opening)),
        ("the opening does not count what went right, even without a number",
         not _WORDLESS_TALLY.search(opening)),
        ("every growth edge reached the parent", not (expected - covered)),
        ("grouped into something a parent can act on",
         1 <= len(letter.get("still_growing") or []) <= 5),
        ("three things for the conference, each with a question",
         len(conference) == 3 and all(i.get("worth_asking") for i in conference)),
        ("framed as a letter",
         bool(letter.get("salutation") and letter.get("caveat")
              and letter.get("signature"))),
    ]

    if pronouns.get("known"):
        # Only a "they" that means THIS CHILD counts. A "they" that means the
        # words in a story is correct English, so the script asks exactly the
        # question the product asks, rather than a cruder one.
        from app.services.snapshot_writer import _plural_pronoun_for_the_child

        checks.append((
            f"written in the singular ({pronouns['subject']}/{pronouns['object']})",
            not _plural_pronoun_for_the_child(
                letter, evidence.get("child_name") or "")))
    else:
        checks.append(("no pronoun guessed for a child with none recorded",
                       not re.search(r"\b(he|she|his|her|him)\b", body, re.I)))

    wanted = (evidence.get("level_fit") or {}).get("suggest")
    checks.append((
        f"a note about the level ({wanted})" if wanted
        else "no note about the level, because the set fitted",
        bool(letter.get("level_note")) == bool(wanted)))
    return checks


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Snapshot for every kind of child.")
    parser.add_argument("profiles", nargs="*", metavar="PROFILE",
                        help=f"which to generate ({', '.join(PROFILES)})")
    parser.add_argument("--out", default="sample_letters",
                        help="directory for the letters")
    parser.add_argument("--base", default=None,
                        help="a running server, e.g. http://127.0.0.1:8099. "
                             "WRITES SCORES to the child named by --child")
    parser.add_argument("--uid", default=LIVE_UID, help="live mode: the parent")
    parser.add_argument("--child", default=LIVE_CHILD, help="live mode: the child")
    args = parser.parse_args()

    unknown = [p for p in args.profiles if p not in PROFILES]
    if unknown:
        print(f"unknown profile(s): {', '.join(unknown)}. "
              f"choose from {', '.join(PROFILES)}")
        return 2
    chosen = args.profiles or list(PROFILES)

    from app.core.config import get_settings
    if not get_settings().openai.is_configured:
        print("OPENAI is not configured, so no letter can be written. This "
              "script calls the real model on purpose: a stubbed letter "
              "proves nothing.")
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.base:
        banner(f"LIVE against {args.base}")
        print(f"  This writes scores to child {args.child} under {args.uid}.")
        print("  Each profile overwrites the last, which is what the snapshot "
              "reads.\n")

    failures: List[str] = []
    samples: List[Dict[str, Any]] = []
    for key in chosen:
        profile = PROFILES[key]
        child = profile["child"]
        banner(f"{profile['label']}\n  {child['name']}, grade {child['grade']}"
               f"\n  Watch for: {profile['watch_for']}")

        started = time.time()
        if args.base:
            result = asyncio.run(
                run_live(key, profile, args.base, args.uid, args.child))
        else:
            result = asyncio.run(run_in_process(key, profile))
        letter = result["letter"]

        step("THE LETTER")
        print()
        print(render(letter))

        step("CHECKS")
        checks = inspect(result)
        for label, passed in checks:
            print(f"      {'PASS' if passed else 'FAIL'}  {label}")
            if not passed:
                failures.append(f"{key}: {label}")

        meta = letter.get("meta") or {}
        print(f"\n      {meta.get('growth_edges_found')} growth edges found, "
              f"written in {meta.get('growth_edges_written')} section(s); "
              f"specificity {meta.get('specificity')}; "
              f"{time.time() - started:.0f}s")
        if meta.get("voice_slips"):
            print(f"      voice slips shipped: {meta['voice_slips']}")

        (out_dir / f"{key}.json").write_text(json.dumps(
            {"evidence": result["evidence"], "letter": letter},
            indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        (out_dir / f"{key}.txt").write_text(render(letter), encoding="utf-8")
        print(f"\n      saved to {out_dir / f'{key}.json'} and .txt")

        evidence = result["evidence"]
        samples.append({
            "profile": key,
            "label": profile["label"],
            "watch_for": profile["watch_for"],
            "child": {
                **profile["child"],
                "pronouns": (evidence.get("pronouns") or {}).get("key"),
            },
            "checks": [
                {"check": label, "passed": bool(passed)}
                for label, passed in checks
            ],
            "checks_passed": sum(1 for _, passed in checks if passed),
            "checks_failed": sum(1 for _, passed in checks if not passed),
            # What the child actually did, beside what the letter made of it.
            "the_sitting": {
                "activities": evidence.get("activities_completed"),
                "span_minutes": (evidence.get("session") or {}).get("span_minutes"),
                "level_fit": evidence.get("level_fit"),
                "growth_edges": [
                    g["signal_name"] for g in evidence.get("growth_edges") or []
                ],
                "growth_clusters": [
                    {"cluster": c["area_display_name"],
                     "seen_in": c["seen_in"], "signals": c["signals"]}
                    for c in evidence.get("growth_clusters") or []
                ],
                "strengths": [
                    g["signal_name"] for g in evidence.get("strengths") or []
                ],
                "words_this_child_wrote": (
                    (evidence.get("what_the_child_did") or {})
                    .get("spelling", {}).get("misspellings")
                ),
            },
            "letter_as_read": render(letter),
            "letter": letter,
            "evidence": evidence,
        })

    combined = out_dir / "all_samples.json"
    combined.write_text(json.dumps({
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ran_against": args.base or "in-process (no server, speech stood in for)",
        "model": get_settings().openai.analysis_model,
        "checks_passed": sum(s["checks_passed"] for s in samples),
        "checks_failed": sum(s["checks_failed"] for s in samples),
        "failures": failures,
        "samples": samples,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    banner("every letter held" if not failures
           else f"{len(failures)} check(s) failed:\n  "
                + "\n  ".join(failures))
    print(f"  All {len(samples)} sample(s) together: {combined}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
