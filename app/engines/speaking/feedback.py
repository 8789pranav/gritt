"""Human-readable feedback, written from the measurements.

The old pipeline asked a language model to write this prose, which meant the
sentences were fluent and not always true - a model given the target sentence
would praise a reading it had not heard. Everything here is generated from
numbers the chain measured, so a sentence about a dropped ending only appears
when an ending was dropped.

It also keeps the response shape the report UI already reads: per-dimension
``score`` and ``feedback``, and per-sentence ``strengths``, ``areas_to_improve``
and ``parent_tip``.
"""

from __future__ import annotations

from typing import Any, Dict, List

#: Score bands used for wording, not for scoring.
STRONG = 85.0
FAIR = 70.0


def _band(score: float) -> str:
    if score >= STRONG:
        return "strong"
    if score >= FAIR:
        return "fair"
    return "weak"


def pronunciation_feedback(measured: Dict[str, Any]) -> str:
    score = measured.get("scores", {}).get("accuracy", 0.0) or 0.0
    findings = measured.get("findings", [])
    wrong = [f for f in findings if "clear_error" in f.get("flags", [])]

    if not measured.get("words"):
        return "No speech was recorded for this sentence."

    if wrong:
        first = wrong[0]
        sub = (first.get("substitutions") or [None])[0]
        if sub:
            return (
                f"{len(wrong)} word{'s' if len(wrong) > 1 else ''} came out "
                f"differently. In “{first['word']}” the "
                f"/{sub['expected']}/ sound was said as /{sub['said']}/."
            )
        return (
            f"{len(wrong)} word{'s' if len(wrong) > 1 else ''} came out "
            f"differently, starting with “{first['word']}”."
        )

    watch = [f for f in findings if "needs_attention" in f.get("flags", [])]
    if watch:
        return (
            f"Mostly clear. “{watch[0]['word']}” was a little "
            f"unclear but recognisable."
        )

    return {
        "strong": "Every word was said clearly.",
        "fair": "Most words were clear.",
        "weak": "Several sounds were hard to make out.",
    }[_band(score)]


def fluency_feedback(measured: Dict[str, Any]) -> str:
    timing = measured.get("timing", {})
    reading = measured.get("reading", {})
    long_pauses = timing.get("long_pause_count", 0)
    pauses = timing.get("pause_count", 0)
    band = reading.get("rate_band")

    if not measured.get("words"):
        return "No speech was recorded for this sentence."

    if long_pauses:
        longest = timing.get("longest_pause_ms", 0)
        return (
            f"Paused {long_pauses} time{'s' if long_pauses > 1 else ''} "
            f"mid-sentence, the longest for {round(longest / 1000, 1)} seconds."
        )
    if band == "below_band":
        return "Read carefully and slowly, working the words out."
    if band == "above_band":
        return "Read quickly and without pausing."
    if pauses:
        return "Read in phrases, with one short pause."
    return "Read smoothly from start to finish."


def prosody_feedback(measured: Dict[str, Any]) -> str:
    score = measured.get("scores", {}).get("prosody") or 0.0
    if not measured.get("words"):
        return "No speech was recorded for this sentence."
    return {
        "strong": "Read with natural expression and rhythm.",
        "fair": "Some expression, though fairly even in tone.",
        "weak": "Read in a flat voice, one word much like the next.",
    }[_band(score)]


def completeness_feedback(measured: Dict[str, Any]) -> str:
    """Kept under the name the report reads for the old grammar dimension."""
    errors = measured.get("errors", {})
    omissions = errors.get("omission", 0)
    insertions = errors.get("insertion", 0)

    if not measured.get("words"):
        return "No speech was recorded for this sentence."
    if omissions:
        return (
            f"{omissions} word{'s were' if omissions > 1 else ' was'} skipped."
        )
    if insertions:
        return (
            f"{insertions} extra word{'s were' if insertions > 1 else ' was'} "
            f"added."
        )
    return "The whole sentence was read, with nothing skipped or added."


def strengths(measured: Dict[str, Any]) -> List[str]:
    """Only things the measurements actually support."""
    out: List[str] = []
    scores = measured.get("scores", {})
    errors = measured.get("errors", {})
    timing = measured.get("timing", {})

    if (scores.get("accuracy") or 0) >= STRONG:
        out.append("Clear pronunciation")
    if (scores.get("completeness") or 0) >= 95 and not errors.get("omission"):
        out.append("Read every word")
    if (scores.get("prosody") or 0) >= STRONG:
        out.append("Natural expression")
    if not timing.get("long_pause_count") and (scores.get("fluency") or 0) >= STRONG:
        out.append("Smooth phrasing")
    if measured.get("disfluency", {}).get("repetitions"):
        out.append("Went back to correct themselves")
    return out


def areas_to_improve(measured: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    scores = measured.get("scores", {})
    errors = measured.get("errors", {})
    timing = measured.get("timing", {})
    disfluency = measured.get("disfluency", {})

    if errors.get("clear_error"):
        out.append("Sounding out tricky words")
    if errors.get("omission"):
        out.append("Reading every word on the line")
    if timing.get("long_pause_count"):
        out.append("Reading in phrases")
    if (scores.get("prosody") or 0) and scores["prosody"] < 60:
        out.append("Reading with expression")
    if errors.get("prolonged"):
        out.append("Moving on once a word is worked out")
    if disfluency.get("filler_count"):
        out.append("Reading without filler sounds")
    return out


def parent_tip(measured: Dict[str, Any]) -> str:
    """One thing to do, chosen by what actually went wrong."""
    errors = measured.get("errors", {})
    timing = measured.get("timing", {})
    scores = measured.get("scores", {})
    findings = measured.get("findings", [])

    if not measured.get("words"):
        return (
            "Nothing was picked up for this sentence. Check the microphone and "
            "have your child try again."
        )

    wrong = [f for f in findings if "clear_error" in f.get("flags", [])]
    if wrong:
        sub = (wrong[0].get("substitutions") or [None])[0]
        if sub:
            return (
                f"Say “{wrong[0]['word']}” together slowly, listening "
                f"for the /{sub['expected']}/ sound."
            )
        return f"Practise the word “{wrong[0]['word']}” together."
    if errors.get("omission"):
        return "Ask your child to follow the line with a finger as they read."
    if timing.get("long_pause_count"):
        return (
            "Read the same sentence together twice. The second time is usually "
            "much smoother."
        )
    if (scores.get("prosody") or 0) and scores["prosody"] < 60:
        return "Take turns reading a line each, using silly voices."
    return "Keep reading aloud together for a few minutes a day."


def level_for(score: float) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 50:
        return "Developing"
    if score > 0:
        return "Needs Practice"
    return "Not Attempted"


#: Wording for a sentence that carries no usable measurement. Praise or
#: criticism would both be inventions here.
_NOT_ASSESSED = {
    "not_attempted": (
        "This sentence was not recorded.",
        "Nothing was picked up for this sentence. Check the microphone and "
        "have your child try again.",
    ),
    "needs_review": (
        "This recording could not be assessed reliably, so it has not been "
        "scored.",
        "The recording was unclear. Have your child read this one again "
        "somewhere quieter.",
    ),
}


def build(measured: Dict[str, Any]) -> Dict[str, Any]:
    """Everything the report reads, derived from one measured sentence.

    A sentence that was not scored gets said so plainly. Running the wording
    rules over withheld zeroes produced sentences like "Read smoothly from
    start to finish" on a recording we had just refused to score.
    """
    status = measured.get("status")
    if status in _NOT_ASSESSED:
        line, tip = _NOT_ASSESSED[status]
        return {
            "pronunciation_feedback": line,
            "fluency_feedback": line,
            "prosody_feedback": line,
            "completeness_feedback": line,
            "strengths": [],
            "areas_to_improve": [],
            "parent_tip": tip,
        }

    return {
        "pronunciation_feedback": pronunciation_feedback(measured),
        "fluency_feedback": fluency_feedback(measured),
        "prosody_feedback": prosody_feedback(measured),
        "completeness_feedback": completeness_feedback(measured),
        "strengths": strengths(measured),
        "areas_to_improve": areas_to_improve(measured),
        "parent_tip": parent_tip(measured),
    }
