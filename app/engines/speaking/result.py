"""The per-sentence result, in one place.

Both /speaking/submit/ and /speaking/complete_result/ return the same object
for a sentence, built here, so the two endpoints cannot drift apart.

Five things per sentence, and nothing else:

    sentence_id / sentence   which sentence this is
    answered                 did the child attempt it
    transcription            what was actually said
    analysis                 a score and a line of feedback per dimension
    tags                     what the tag engine made of it

Each dimension is one percentage and one sentence of feedback. The per-word
and per-phoneme detail is still measured - it is what produces the score and
what the feedback quotes - but it is not carried in the response. A report
that lists twenty phoneme accuracies buries the one thing a parent needs,
which is the number and what to do about it.

The detail remains reachable for diagnosis through /lab, and the sound the
child actually made survives in ``transcription.spoken_sounds``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.engines.speaking.feedback import build as build_feedback
from app.engines.speaking.feedback import level_for

#: The three states a sentence can be in.
ANSWERED = "answered"
NOT_ATTEMPTED = "not_attempted"
NEEDS_REVIEW = "needs_review"


def _pct(value: Any) -> float:
    """Every score is a percentage, rounded once, here."""
    try:
        return round(float(value or 0.0), 1)
    except (TypeError, ValueError):
        return 0.0


def build_sentence(
    measured: Dict[str, Any],
    sentence_text: str,
    tags: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """One sentence, from its measurement set."""
    status = measured.get("status", NOT_ATTEMPTED)
    scores = measured.get("scores", {}) or {}
    feedback = build_feedback(measured)
    reading = measured.get("reading", {}) or {}
    timing = measured.get("timing", {}) or {}
    disfluency = measured.get("disfluency", {}) or {}
    errors = measured.get("errors", {}) or {}

    heard = measured.get("recognized", "") or ""
    spoken_sounds = " ".join(
        w.get("spoken_ipa", "") for w in measured.get("words", [])
        if w.get("spoken_ipa")
    )

    overall = _pct(scores.get("pron_score"))

    return {
        "sentence_id": measured.get("sentence_id", ""),
        "sentence": sentence_text,
        "answered": status == ANSWERED,
        "status": status,
        #: Why a sentence was not scored, when it was not.
        "reason": measured.get("reason") or measured.get("message") or "",

        # What the child actually said. "heard" is Azure's recognition, which
        # aligns to the reference and so reads as the target sentence however
        # it was said. "verbatim" keeps fillers. "spoken_sounds" is the only
        # one that survives a mispronunciation: a child who says "dot" for
        # "dog" shows a /t/ where the word needs a /g/.
        "transcription": {
            "heard": heard,
            "verbatim": measured.get("verbatim", "") or "",
            "spoken_sounds": spoken_sounds,
            "matches_reference": (
                heard.strip().lower().rstrip(".")
                == sentence_text.strip().lower().rstrip(".")
            ),
        },

        "analysis": {
            "overall": {
                "score": overall,
                "level": level_for(overall),
            },
            "pronunciation": {
                "score": _pct(scores.get("accuracy")),
                "feedback": feedback["pronunciation_feedback"],
            },
            "fluency": {
                "score": _pct(scores.get("fluency")),
                "feedback": feedback["fluency_feedback"],
            },
            "prosody": {
                "score": _pct(scores.get("prosody")),
                "feedback": feedback["prosody_feedback"],
            },
            "completeness": {
                "score": _pct(scores.get("completeness")),
                "feedback": feedback["completeness_feedback"],
            },
            # The measurements a teacher reads as numbers rather than prose.
            "reading": {
                "wcpm": reading.get("wcpm", 0.0),
                "accuracy_pct": reading.get("accuracy_pct", 0.0),
                "correct_words": reading.get("correct_words", 0),
                "total_words": reading.get("total_words", 0),
                "rate_band": reading.get("rate_band", ""),
            },
            "timing": {
                "time_to_speak_ms": timing.get("time_to_speak_ms"),
                "time_to_first_word_ms": timing.get("time_to_first_word_ms", 0.0),
                "pause_count": timing.get("pause_count", 0),
                "long_pause_count": timing.get("long_pause_count", 0),
                "longest_pause_ms": timing.get("longest_pause_ms", 0.0),
            },
            "disfluency": {
                "fillers": disfluency.get("fillers", []),
                "filler_count": disfluency.get("filler_count", 0),
                "repetitions": disfluency.get("repetitions", 0),
            },
            "errors": {
                "mispronounced": errors.get("clear_error", 0),
                "unclear": errors.get("needs_attention", 0),
                "skipped": errors.get("omission", 0),
                "added": errors.get("insertion", 0),
                "stretched": errors.get("prolonged", 0),
            },
            "phonics": measured.get("phonics", {}),
            "strengths": feedback["strengths"],
            "areas_to_improve": feedback["areas_to_improve"],
            "parent_tip": feedback["parent_tip"],
            "attempt": measured.get("attempt", 1),
        },

        "tags": list(tags or []),
    }


def build_sentences(
    measured: Sequence[Dict[str, Any]],
    sentence_text_by_id: Dict[str, str],
    tags_by_id: Optional[Dict[str, Sequence[str]]] = None,
) -> List[Dict[str, Any]]:
    tags_by_id = tags_by_id or {}
    return [
        build_sentence(
            m,
            sentence_text_by_id.get(m.get("sentence_id", ""), ""),
            tags_by_id.get(m.get("sentence_id", "")),
        )
        for m in measured
    ]
