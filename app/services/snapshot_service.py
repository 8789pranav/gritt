"""Stage A of the Learning Snapshot: the deterministic evidence pipeline.

Fetches the latest result for each assessment, extracts the tags, maps them
to the learning areas, and computes an evidence package that the LLM writer
(Stage B) turns into a parent letter.

This stage never calls an LLM. It produces facts; the writer produces words.

The single most important thing this module does is hand the writer the words
the child actually wrote and read. A letter built from tag names could be
about any child. A letter that quotes *fone*, *graff* and *clunck* could only
be about one.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.domain.enums import TestType
from app.core.security import verify_paid_child
from app.services.pronouns import pronouns_for
from app.infrastructure.repositories import ScoreRepository

logger = logging.getLogger(__name__)

_AREA_CONFIG_PATH = os.path.join("data", "tags", "learning_areas.json")

_AREA_CACHE: Optional[Dict[str, Any]] = None

#: A tag backed by at least this many questions was seen often enough to
#: describe as a pattern rather than as a single observation (LS4). The count
#: is of QUESTIONS, never of activities: fourteen comprehension questions in
#: one activity is not "seen once".
SEEN_REPEATEDLY_AT = 3

#: Signal names that report how many items sit behind a tag. Every tag config
#: already declares one of these beside its accuracy, so the count a parent
#: should be told is already measured - it was simply never read.
_COUNT_SIGNAL_SUFFIXES = (
    "_items_count",
    "_attempted",
    "_words_count",
    "_shown",
)

#: Counts that are whole-activity rather than per-construct.
_WHOLE_ACTIVITY_COUNTS = ("sentences_answered", "stories_attempted")

#: LS9: this finding is specific, actionable, and the hardest-won thing in
#: the whole product. It is never ranked out of the letter.
_NEVER_DROP = {"spelling_convention_emerging"}


def _load_area_config() -> Dict[str, Any]:
    """Load and cache the learning-areas mapping."""
    global _AREA_CACHE
    if _AREA_CACHE is None:
        with open(_AREA_CONFIG_PATH, encoding="utf-8") as f:
            _AREA_CACHE = json.load(f)
    return _AREA_CACHE


def _parse_evidence(evidence: Any) -> Dict[str, Any]:
    """Turn ``"pattern_accuracy=1.0, pattern_items_count=3"`` into a dict.

    Not every tag stores its measurements as that string. Some carry them as
    a mapping already, and one child's results brought the whole letter down
    with an AttributeError on the split below - a 500, which is the one
    outcome worse than a thin letter. A mapping is taken as it stands, and
    anything else is read as no measurements rather than as a crash.
    """
    if isinstance(evidence, dict):
        return dict(evidence)
    if not isinstance(evidence, str):
        return {}
    parsed: Dict[str, Any] = {}
    for part in evidence.split(","):
        if "=" not in part:
            continue
        name, _, raw = part.partition("=")
        name = name.strip()
        raw = raw.strip()
        try:
            parsed[name] = float(raw) if "." in raw else int(raw)
        except ValueError:
            parsed[name] = raw
    return parsed


def _questions_behind(evidence: Any, answered_in_activity: int) -> int:
    """How many questions produced this tag (LS4).

    Prefers the construct's own item count, falls back to how much of the
    activity the child completed. Never returns the number of activities -
    that was the bug: one activity was reported as one observation.
    """
    parsed = _parse_evidence(evidence)
    counts = [
        int(value)
        for name, value in parsed.items()
        if isinstance(value, (int, float))
        and (
            name.endswith(_COUNT_SIGNAL_SUFFIXES)
            or name in _WHOLE_ACTIVITY_COUNTS
        )
    ]
    if counts:
        return max(counts)
    return answered_in_activity


#: Round minutes to something a person would say out loud.
_SPOKEN_MINUTES = {
    10: "ten minutes", 15: "fifteen minutes", 20: "twenty minutes",
    25: "twenty-five minutes", 30: "half an hour", 35: "thirty-five minutes",
    40: "forty minutes", 45: "three quarters of an hour",
}


def _span_phrase(minutes: float) -> str:
    """How long the sitting took, in words a parent would use.

    The letter says "I sat with Manju for about twenty minutes" because that
    run took about twenty minutes, not because twenty is in the template.
    """
    if minutes is None:
        return "a short sitting"
    if minutes < 8:
        return "a few minutes"
    if minutes > 50:
        return "a little under an hour" if minutes <= 75 else "a couple of sittings"
    nearest = min(_SPOKEN_MINUTES, key=lambda m: abs(m - minutes))
    return _SPOKEN_MINUTES[nearest]


class SnapshotService:
    """Builds the structured evidence behind the Learning Snapshot."""

    def __init__(self) -> None:
        self._config = _load_area_config()
        self._scores = ScoreRepository()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def build_evidence(
        self,
        id_token: str,
        child_id: str,
        grade: Optional[str] = None,
        *,
        uid: Optional[str] = None,
        child_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fetch all four results and synthesise the evidence package."""
        if uid is None or child_data is None:
            uid, child_data = verify_paid_child(id_token, child_id)
        child_name = child_data.get("name", "")
        # A letter about one child is written in the singular. The pronouns
        # come from the profile, never from the name.
        pronouns = pronouns_for(child_data)

        # A1. Fetch the latest result for every assessment.
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for key, storage_key in (
            ("logic", TestType.LOGIC.storage_key),
            ("spelling", TestType.SPELLING.storage_key),
            ("speaking", TestType.SPEAKING.storage_key),
            ("comprehension", TestType.COMPREHENSION.storage_key),
        ):
            try:
                result = self._scores.get_latest(
                    uid, child_id, storage_key, grade
                )
                # A child is not always assessed at the grade their profile
                # now says. Sadie's profile read Third while all four of her
                # results were recorded at Second, and asking for Third
                # returned nothing at all - no tags, no words, no letter to
                # write. The work the child actually did is the better
                # answer than an empty page, so take it whatever grade it
                # was recorded under.
                if result is None and grade:
                    result = self._scores.get_latest(
                        uid, child_id, storage_key, None
                    )
                    if result is not None:
                        logger.info(
                            "snapshot: no %s result at grade %s; using the "
                            "latest at grade %s instead",
                            key, grade, result.get("grade"),
                        )
                results[key] = result
            except Exception as exc:  # a failed fetch must not sink the letter
                logger.warning("snapshot: could not fetch %s: %s", key, exc)
                results[key] = None

        completed = [k for k, v in results.items() if v]
        display = self._config["test_display_names"]

        # A2. What the child actually did, in their own words (Part 4).
        activity_detail = {
            key: builder(results[key])
            for key, builder in (
                ("spelling", self._spelling_detail),
                ("speaking", self._speaking_detail),
                ("comprehension", self._comprehension_detail),
                ("logic", self._logic_detail),
            )
            if results.get(key)
        }

        # A3. Every fired tag, at tag level, with the activity that fired it.
        signals = self._collect_signals(results, activity_detail)

        # LS9: every growth edge reaches the parent. No limit, and the
        # spelling-conventions finding is pinned to the front when it fired.
        strengths = [s for s in signals if s["polarity"] == "strength"]
        growth_edges = [s for s in signals if s["polarity"] == "growth_edge"]
        neutral = [s for s in signals if s["polarity"] == "neutral"]

        strengths.sort(key=self._signal_rank, reverse=True)
        growth_edges.sort(key=self._signal_rank, reverse=True)

        return {
            "child_name": child_name,
            "pronouns": pronouns,
            "grade": grade,
            "tests_completed": completed,
            "activities_completed": [display[k] for k in completed if k in display],
            # LS6: what actually happened, so the letter cannot invent a week
            # of sessions that never took place.
            "session": self._session_facts(results, display),
            # LS7: a run with nothing to fault still gets its own observation.
            "flawless_activities": self._flawless_activities(
                activity_detail, display
            ),
            "strengths": strengths,
            "growth_edges": growth_edges,
            # The same growth edges, grouped into what a parent can act on.
            # One section of the letter per cluster.
            "growth_clusters": self._growth_clusters(growth_edges),
            "neutral_observations": neutral,
            "areas": self._areas(signals),
            "what_the_child_did": activity_detail,
            # LS10: the only signal names that may appear in the letter.
            "allowed_signal_names": sorted(
                {s["signal_name"] for s in signals}
            ),
            # The facts that make this letter about THIS child. Stage B is
            # checked against them, so a vague letter is caught rather than
            # hoped away.
            # Whether this set fitted the child, so the letter can say so
            # when it did not. Never a score - a direction.
            "level_fit": self._level_fit(activity_detail, growth_edges),
            "must_mention": self._must_mention(activity_detail),
            "could_mention": self._could_mention(activity_detail),
        }

    # ------------------------------------------------------------------
    # Stage A3: every fired tag, one entry each
    # ------------------------------------------------------------------
    def _collect_signals(
        self,
        results: Dict[str, Optional[Dict[str, Any]]],
        activity_detail: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """One entry per fired tag, carrying the activity that produced it.

        Tags are matched per test rather than globally. A tag can only be
        credited to the activity whose result actually carries it, which is
        what LS2 is about: Word Wizard does not get credit for a pattern the
        Logic Quest measured.
        """
        areas = self._config["areas"]
        display = self._config["test_display_names"]
        tag_names = self._config.get("tag_display_names", {})

        # Which area each tag belongs to, for the test that fired it.
        area_of: Dict[Tuple[str, str], Dict[str, str]] = {}
        for area_key, area_cfg in areas.items():
            for test_key, tag_ids in area_cfg["sources"].items():
                for tag_id in tag_ids:
                    area_of[(test_key, tag_id)] = {
                        "area": area_key,
                        "area_display_name": area_cfg["display_name"],
                    }

        signals: List[Dict[str, Any]] = []
        for test_key, result in results.items():
            if not result:
                continue
            answered = int(
                (activity_detail.get(test_key) or {}).get("questions_answered", 0)
            )
            for tag in result.get("dear_parent_tags", []):
                tag_id = tag.get("id") or tag.get("tag", "")
                if not tag_id:
                    continue
                placement = area_of.get((test_key, tag_id))
                if placement is None:
                    # A tag no area claims still happened; it simply has no
                    # section to sit in. Silence is better than a made-up home.
                    continue
                evidence = tag.get("evidence", "")
                count = _questions_behind(evidence, answered)
                signals.append(
                    {
                        "tag": tag_id,
                        # LS10: the agreed name, never one the writer invents.
                        "signal_name": tag_names.get(tag_id, tag_id),
                        "polarity": tag.get("polarity", "neutral"),
                        "confidence": tag.get("confidence", "medium"),
                        "description": tag.get("description", ""),
                        "seen_in": display.get(test_key, test_key),
                        "activity": test_key,
                        # LS4: questions, not activities.
                        "questions_behind": count,
                        "badge": (
                            "seen_repeatedly"
                            if count >= SEEN_REPEATEDLY_AT
                            else "seen_once"
                        ),
                        "measurements": _parse_evidence(evidence),
                        **placement,
                    }
                )
        return signals

    @staticmethod
    def _growth_clusters(
        growth_edges: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Growth edges gathered into one thing to work on each.

        Four sounds that slipped while reading aloud are one thing a parent
        can do something about, not four. The learning area is what makes
        them one: it is the product's own answer to "is this the same
        finding", and it is settled here rather than left to the writer,
        which is what let eleven of seventeen edges fall out of a letter.

        Ordered so the most useful to the parent comes first, by the same
        rank the edges themselves are ordered by.
        """
        clusters: Dict[str, Dict[str, Any]] = {}
        for edge in growth_edges:
            cluster = clusters.setdefault(edge["area"], {
                "cluster": edge["area"],
                "area_display_name": edge["area_display_name"],
                "signals": [],
                "seen_in": [],
                "questions_behind": 0,
            })
            cluster["signals"].append(edge["signal_name"])
            if edge["seen_in"] not in cluster["seen_in"]:
                cluster["seen_in"].append(edge["seen_in"])
            cluster["questions_behind"] += edge.get("questions_behind", 0)

        ordered = list(clusters.values())
        rank = {
            edge["area"]: index
            for index, edge in reversed(list(enumerate(growth_edges)))
        }
        ordered.sort(key=lambda c: rank.get(c["cluster"], 99))
        return ordered

    def _areas(self, signals: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """The merged picture, one entry per area that has evidence.

        LS2: ``seen_in`` lists only the activities that actually fired one of
        the tags in this area.
        """
        grouped: Dict[str, Dict[str, Any]] = {}
        for signal in signals:
            bucket = grouped.setdefault(
                signal["area"],
                {
                    "area": signal["area"],
                    "area_display_name": signal["area_display_name"],
                    "seen_in": [],
                    "signals": [],
                    "questions_behind": 0,
                },
            )
            if signal["seen_in"] not in bucket["seen_in"]:
                bucket["seen_in"].append(signal["seen_in"])
            bucket["signals"].append(
                {
                    "tag": signal["tag"],
                    "signal_name": signal["signal_name"],
                    "polarity": signal["polarity"],
                    "description": signal["description"],
                    "seen_in": signal["seen_in"],
                }
            )
            bucket["questions_behind"] += signal["questions_behind"]

        areas: List[Dict[str, Any]] = []
        for bucket in grouped.values():
            polarities = [s["polarity"] for s in bucket["signals"]]
            # LS1: the headline must follow the tags underneath it. An area
            # with more growth edges than strengths is a growth area, and the
            # writer is told so rather than left to guess from the prose.
            strengths = polarities.count("strength")
            growth = polarities.count("growth_edge")
            bucket["polarity"] = (
                "strength" if strengths > growth
                else "growth_edge" if growth > strengths
                else "mixed"
            )
            bucket["badge"] = (
                "seen_repeatedly"
                if bucket["questions_behind"] >= SEEN_REPEATEDLY_AT
                else "seen_once"
            )
            areas.append(bucket)

        areas.sort(key=lambda a: (len(a["signals"]), a["questions_behind"]), reverse=True)
        return areas

    # ------------------------------------------------------------------
    # Part 4: what the child actually did, per activity
    # ------------------------------------------------------------------
    @staticmethod
    def _spelling_detail(result: Dict[str, Any]) -> Dict[str, Any]:
        """The words, and what the child wrote instead. THE BIG ONE."""
        rows = result.get("results") or []
        words: List[Dict[str, Any]] = []
        convention: List[Dict[str, str]] = []

        for row in rows:
            detail = row.get("detail") or {}
            attempt = (detail.get("user_input") or "").strip()
            mistakes = detail.get("mistakes") or {}
            entry = {
                "word": row.get("label", "") or row.get("item_id", ""),
                "attempt": attempt,
                "correct": bool(row.get("is_correct")),
                "answered": bool(attempt),
                "word_type": detail.get("type", ""),
                "seconds": detail.get("time", 0.0),
            }
            if not entry["correct"] and attempt:
                entry["what_changed"] = sorted(mistakes)
            words.append(entry)
            if "spelling_convention" in mistakes and attempt:
                convention.append({"word": entry["word"], "attempt": attempt})

        answered = [w for w in words if w["answered"]]
        return {
            "activity": "Word Wizard",
            "words": words,
            # The three that carry the whole letter: heard right, spelled by
            # a rule the child has not met yet.
            "heard_right_spelled_by_another_rule": convention,
            "misspellings": [
                {"word": w["word"], "attempt": w["attempt"]}
                for w in answered
                if not w["correct"]
            ],
            "words_correct": sum(1 for w in words if w["correct"]),
            "words_total": len(words),
            "questions_answered": len(answered),
            "key_error_patterns": [
                {"pattern": name, "count": count}
                for name, count in (result.get("error_analysis") or {}).items()
                if count
            ],
            "strengths": result.get("strengths") or [],
            "focus_areas": result.get("focus_areas") or [],
        }

    @staticmethod
    def _speaking_detail(result: Dict[str, Any]) -> Dict[str, Any]:
        """The sentences, the tips already written, and the reading pace."""
        sentences = result.get("sentences") or []
        signals = result.get("signals") or {}

        rows: List[Dict[str, Any]] = []
        tips: List[str] = []
        stretched_on: List[str] = []
        different_on: List[Dict[str, str]] = []

        for sentence in sentences:
            if not sentence.get("answered"):
                continue
            analysis = sentence.get("analysis") or {}
            errors = analysis.get("errors") or {}
            text = sentence.get("sentence", "")
            tip = (analysis.get("parent_tip") or "").strip()
            pronunciation = (
                (analysis.get("pronunciation") or {}).get("feedback") or ""
            ).strip()

            rows.append(
                {
                    "sentence": text,
                    "wcpm": (analysis.get("reading") or {}).get("wcpm", 0.0),
                    "seconds": (analysis.get("timing") or {}).get(
                        "duration_seconds", 0.0
                    ),
                    "stretched_sounds": errors.get("stretched", 0),
                    "skipped_words": errors.get("skipped", 0),
                    "words_that_came_out_differently": errors.get(
                        "mispronounced", 0
                    ),
                    # Ready-written and concrete. These used to be generated
                    # and thrown away.
                    "parent_tip": tip,
                    "pronunciation_feedback": pronunciation,
                }
            )
            if tip and tip not in tips:
                tips.append(tip)
            if errors.get("stretched"):
                stretched_on.append(text)
            if errors.get("mispronounced") and pronunciation:
                different_on.append({"sentence": text, "feedback": pronunciation})

        return {
            "activity": "Voice Challenge",
            "sentences": rows,
            "parent_tips": tips,
            "sentences_where_a_sound_was_stretched": stretched_on,
            "words_that_came_out_differently": different_on,
            "questions_answered": len(rows),
            # The strongest conference currency in the whole payload, and
            # until now invisible in the letter.
            "words_correct_per_minute": signals.get("wcpm", 0.0),
            "pace_against_the_usual_band": signals.get("wcpm_band", ""),
            "read_every_word_score": signals.get("avg_completeness", 0.0),
            "words_skipped": signals.get("omission_count", 0),
            "sounds_stretched": signals.get("prolonged_count", 0),
            "words_read": signals.get("words_read", 0),
        }

    @staticmethod
    def _comprehension_detail(result: Dict[str, Any]) -> Dict[str, Any]:
        """The stories, and what the child worked out or missed, in words."""
        stories = result.get("results") or []
        rows: List[Dict[str, Any]] = []
        worked_out: List[Dict[str, str]] = []
        missed: List[Dict[str, str]] = []
        answered = 0

        for story in stories:
            questions: List[Dict[str, Any]] = []
            for question in story.get("questions") or []:
                if not question.get("answered", True):
                    continue
                answered += 1
                entry = {
                    "question": question.get("question", ""),
                    "kind": question.get("question_type", ""),
                    "chose": question.get("selected_answer", ""),
                    "answer": question.get("correct_answer", ""),
                    "correct": bool(question.get("is_correct")),
                    "seconds": question.get("response_time_seconds", 0.0),
                }
                questions.append(entry)
                target = worked_out if entry["correct"] else missed
                target.append(
                    {
                        "story": story.get("story_title", ""),
                        "question": entry["question"],
                        "kind": entry["kind"],
                        "chose": entry["chose"],
                        "answer": entry["answer"],
                    }
                )
            rows.append(
                {
                    "story_title": story.get("story_title", ""),
                    "questions": questions,
                }
            )

        return {
            "activity": "Story Explorer",
            "stories": rows,
            "worked_out": worked_out,
            "missed": missed,
            "questions_answered": answered,
        }

    @staticmethod
    def _logic_detail(result: Dict[str, Any]) -> Dict[str, Any]:
        """What kind of puzzle, how hard, and how long the child took.

        Every puzzle is listed, even ones the child did not answer, so the
        letter can name the actual question text instead of saying "they were
        there".
        """
        items = result.get("scored_items") or []
        rows: List[Dict[str, Any]] = []
        for item in items:
            detail = item.get("detail") or {}
            status = str(item.get("status") or "answered").lower()
            not_answered = "not" in status or status == "error"
            rows.append(
                {
                    # The puzzle itself. "2-4" is an item number and means
                    # nothing to a parent.
                    "question": detail.get("question_text")
                    or item.get("label", ""),
                    "item_number": item.get("label", ""),
                    "kind": (detail.get("item_type") or "").replace("_", " "),
                    "difficulty": detail.get("difficulty", ""),
                    "answered": not not_answered,
                    "correct": not not_answered and bool(item.get("is_correct")),
                    "seconds": detail.get("response_time_seconds", 0.0),
                    "missed_skill": [
                        t for t in (detail.get("tags") or [])
                        if t.endswith("_missed")
                    ],
                }
            )

        answered = sum(1 for r in rows if r["answered"])

        return {
            "activity": "Logic Quest",
            "questions": rows,
            "took_time_and_got_it_right": [
                r for r in rows
                if r["answered"] and r["correct"] and (r["seconds"] or 0) >= 10
            ],
            "missed": [r for r in rows if r["answered"] and not r["correct"]],
            "questions_answered": answered,
        }

    # ------------------------------------------------------------------
    # What makes the letter unmistakably about this child
    # ------------------------------------------------------------------
    @staticmethod
    def _must_mention(activity_detail: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Facts the letter is required to use, when the child produced them.

        "Sometimes good, sometimes vague" is what happens when specificity
        is asked for but only harm is enforced. These are checked.
        """
        required: List[Dict[str, Any]] = []

        spelling = activity_detail.get("spelling") or {}
        heard_right = spelling.get("heard_right_spelled_by_another_rule") or []
        if heard_right:
            required.append(
                {
                    "what": "the words this child spelled by sound",
                    "why": (
                        "Every sound is right and only the rule is missing. "
                        "This is the most useful finding in the run and the "
                        "one thing no other child's letter could contain."
                    ),
                    "any_of": [m["attempt"] for m in heard_right],
                }
            )
        elif spelling.get("misspellings"):
            required.append(
                {
                    "what": "what this child actually wrote",
                    "why": "A letter that quotes it could only be about them.",
                    "any_of": [m["attempt"] for m in spelling["misspellings"]],
                }
            )

        comprehension = activity_detail.get("comprehension") or {}
        titles = [
            s["story_title"] for s in (comprehension.get("stories") or [])
            if s.get("story_title")
        ]
        if titles:
            required.append(
                {
                    "what": "the story by name",
                    "why": "A parent can talk about it at home.",
                    "any_of": titles,
                }
            )

        return required

    @staticmethod
    def _could_mention(activity_detail: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Concrete detail the letter is measured on, but not failed for.

        The more of this a draft uses, the more it reads like someone who
        was in the room. The writer keeps its most specific attempt.
        """
        spelling = activity_detail.get("spelling") or {}
        speaking = activity_detail.get("speaking") or {}
        comprehension = activity_detail.get("comprehension") or {}
        logic = activity_detail.get("logic") or {}

        return {
            "words_written": [
                m["attempt"] for m in (spelling.get("misspellings") or [])
            ],
            # The words a child got RIGHT are evidence too: without these a
            # flawless speller has nothing quotable, and a letter about them
            # cannot reach across two activities without inventing something.
            #
            # Only the long ones. "Well" and "they" are spelled correctly by
            # everyone and appear inside any sentence, so counting them as
            # this child's own words makes a vague letter look specific.
            # "Turnstile" and "amputate" are the ones a parent notices.
            "words_spelled_correctly": [
                w["word"] for w in (spelling.get("words") or [])
                if w.get("correct") and len(str(w.get("word", ""))) >= 6
            ],
            "sentences_read": [
                s["sentence"] for s in (speaking.get("sentences") or [])
            ],
            "reading_pace": speaking.get("pace_against_the_usual_band", ""),
            "story_titles": [
                s["story_title"] for s in (comprehension.get("stories") or [])
                if s.get("story_title")
            ],
            "questions_worked_out": [
                w["question"] for w in (comprehension.get("worked_out") or [])
            ],
            "questions_missed": [
                m["question"] for m in (comprehension.get("missed") or [])
            ],
            "answers_chosen": [
                m["chose"] for m in (comprehension.get("missed") or []) if m.get("chose")
            ],
            "puzzles": [q["question"] for q in (logic.get("questions") or [])],
        }

    # ------------------------------------------------------------------
    # LS6 / LS7 helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _session_facts(
        results: Dict[str, Optional[Dict[str, Any]]],
        display: Dict[str, str],
    ) -> Dict[str, Any]:
        """When the activities actually happened, and how far apart.

        The letter used to open with "This week, I had the pleasure of
        observing...". Four activities finished five minutes apart. There was
        no week, so the writer is handed the real span instead.
        """
        stamps: List[datetime] = []
        for result in results.values():
            raw = (result or {}).get("timestamp")
            if not raw:
                continue
            try:
                stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            # Results written before the timestamps carried a zone are still
            # in the database, and Python refuses to subtract one of those
            # from a zoned one. A child with an old result and a new one
            # crashed the whole letter on the subtraction below. They were
            # all written in UTC, so that is what the old ones are read as.
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            stamps.append(stamp)

        if not stamps:
            return {
                "activities": [],
                "span_minutes": None,
                "span_phrase": "a short sitting",
                "same_sitting": None,
            }

        span = (max(stamps) - min(stamps)).total_seconds() / 60.0
        return {
            "activities": [display[k] for k, v in results.items() if v and k in display],
            "span_minutes": round(span, 1),
            # The words the letter uses for how long this took. "Twenty
            # minutes" is a fact about one run, not a phrase to hardcode.
            "span_phrase": _span_phrase(span),
            # Everything inside an hour was one sitting, not a series of
            # sessions over time.
            "same_sitting": span <= 60.0,
            "first_at": min(stamps).isoformat(),
            "last_at": max(stamps).isoformat(),
        }

    @staticmethod
    def _level_fit(
        activity_detail: Dict[str, Dict[str, Any]],
        growth_edges: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Did this set of activities fit the child?

        A set the child walked through tells you they are secure, but not
        where their limit is. A set that was out of reach tells you less than
        one pitched right. Both are worth a sentence to a parent, and neither
        is a score: the letter is handed a direction, never a ratio.
        """
        shares: List[float] = []

        spelling = activity_detail.get("spelling") or {}
        if spelling.get("words_total"):
            shares.append(spelling["words_correct"] / spelling["words_total"])

        comprehension = activity_detail.get("comprehension") or {}
        answered = comprehension.get("questions_answered") or 0
        if answered:
            worked_out = len(comprehension.get("worked_out") or [])
            shares.append(worked_out / answered)

        logic = activity_detail.get("logic") or {}
        answered = logic.get("questions_answered") or 0
        if answered:
            right = sum(1 for q in logic.get("questions") or [] if q["correct"])
            shares.append(right / answered)

        if not shares:
            return {"fit": "unknown", "suggest": None}

        share = sum(shares) / len(shares)

        # Comfortable: almost nothing to fault, and the engine found little
        # to grow. The level above would show the parent more.
        if share >= 0.9 and len(growth_edges) <= 2:
            return {
                "fit": "comfortable",
                "suggest": "the level above",
                # What is true, not how to say it. The sentences that used to
                # live here came back in the letter unchanged.
                "means": "secure here, but this set did not find their limit",
            }

        # Out of reach: a set this hard says less about the child than one
        # pitched right, and it is a harder afternoon for them.
        if share <= 0.45:
            return {
                "fit": "too_hard",
                "suggest": "the level below",
                "means": (
                    "out of reach today, so this run says less about the "
                    "child than a set pitched right would"
                ),
            }

        return {"fit": "well_matched", "suggest": None}

    @staticmethod
    def _flawless_activities(
        activity_detail: Dict[str, Dict[str, Any]],
        display: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Activities with nothing to fault (LS7).

        Vedika spelled 15 of 15 and Word Wizard never got a headline of its
        own. A run with no mistakes in it is itself an observation.
        """
        flawless: List[Dict[str, Any]] = []

        spelling = activity_detail.get("spelling")
        if spelling and spelling["words_total"] and not spelling["misspellings"]:
            flawless.append(
                {
                    "activity": display["spelling"],
                    "nothing_to_fault": "every word spelled correctly",
                }
            )

        comprehension = activity_detail.get("comprehension")
        if comprehension and comprehension["questions_answered"] and not comprehension["missed"]:
            flawless.append(
                {
                    "activity": display["comprehension"],
                    "nothing_to_fault": (
                        "every question about the stories worked out, "
                        "including the ones the stories only imply"
                    ),
                }
            )

        logic = activity_detail.get("logic")
        if logic and logic["questions_answered"] and not logic["missed"]:
            flawless.append(
                {
                    "activity": display["logic"],
                    "nothing_to_fault": "every puzzle worked out, hard ones included",
                }
            )

        speaking = activity_detail.get("speaking")
        if speaking and speaking["questions_answered"] and not (
            speaking["words_skipped"] or speaking["words_that_came_out_differently"]
        ):
            flawless.append(
                {
                    "activity": display["speaking"],
                    "nothing_to_fault": "every sentence read without a word skipped",
                }
            )

        return flawless

    # ------------------------------------------------------------------
    @staticmethod
    def _signal_rank(signal: Dict[str, Any]) -> Tuple[int, int, float]:
        """LS9: rank by evidence strength, not by the order tags were read.

        The spelling-conventions finding sorts first whenever it fired: it is
        the most useful thing the product measures and it was the finding the
        old cap dropped.
        """
        confidence_weight = {"high": 2, "medium": 1, "low": 0}
        return (
            1 if signal["tag"] in _NEVER_DROP else 0,
            confidence_weight.get(str(signal.get("confidence")), 1),
            float(signal.get("questions_behind", 0)),
        )


def get_snapshot_service() -> SnapshotService:
    return SnapshotService()
