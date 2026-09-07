"""Assessment orchestration service.

Wires engines, tagging, and persistence together for all four test types.
Each method corresponds to one or more API endpoints.

The service layer is responsible for:
  1. Converting API-grade strings to ``Grade`` enums.
  2. Converting raw request dicts into domain response objects.
  3. Calling the engine's ``evaluate()`` pipeline.
  4. Shaping the ``AssessmentResult`` into the legacy-compatible response dicts.
  5. Persisting results to Firebase via ``ScoreRepository``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import InvalidGradeError, ResultNotFoundError
from app.core.security import verify_paid_child
from app.domain.enums import Grade, TestType, WordType
from app.domain.models import (
    ComprehensionResponse,
    LogicResponse,
    SpeakingResponse,
    SpellingResponse,
)
from app.engines.registry import (
    comprehension_engine,
    logic_engine,
    speaking_engine,
    spelling_engine,
)
from app.infrastructure.repositories import ScoreRepository, sanitize_data

logger = logging.getLogger(__name__)

VALID_GRADES = ["Kindergarten", "First", "Second", "Third"]


def _parse_grade(grade_str: str) -> Grade:
    """Convert a string from the API into a ``Grade`` enum."""
    try:
        return Grade.parse(grade_str)
    except ValueError:
        raise InvalidGradeError(grade_str, VALID_GRADES)


def _tag_outputs_to_dicts(tags):
    """Serialise ``TagOutput`` objects into plain dicts for JSON storage."""
    return [
        {
            "tag": t.tag,
            "confidence": t.confidence.value if hasattr(t.confidence, "value") else str(t.confidence),
            "polarity": t.polarity.value if hasattr(t.polarity, "value") else str(t.polarity),
            "description": t.description,
            "evidence": t.evidence,
        }
        for t in tags
    ]


def _speaking_table(sentences):
    from app.engines.speaking.result import teacher_table

    return teacher_table(sentences)


def _restore_sentences(stored):
    """Re-add the keys Firebase drops when reading sentences back.

    The Realtime Database stores no empty containers, so a sentence with no
    tags, no findings or no words comes back missing those keys entirely
    rather than holding an empty list - and a client doing .length on one of
    them breaks on exactly the unattempted sentences.
    """
    restored = []
    for entry in (stored or []):
        entry = dict(entry or {})
        entry.setdefault("tags", [])
        analysis = dict(entry.get("analysis") or {})
        for key in ("strengths", "areas_to_improve"):
            analysis.setdefault(key, [])
        for key in ("overall", "pronunciation", "fluency", "prosody",
                    "completeness", "reading", "timing", "disfluency",
                    "errors", "phonics"):
            analysis.setdefault(key, {})
        disfluency = dict(analysis.get("disfluency") or {})
        disfluency.setdefault("fillers", [])
        analysis["disfluency"] = disfluency
        entry["analysis"] = analysis
        entry.setdefault("transcription", {})
        entry.setdefault("answered", entry.get("status") == "answered")
        restored.append(entry)
    return restored


def _restore_per_item_tags(stored):
    """Re-add the keys Firebase drops when reading per-item tags back.

    The Realtime Database stores no empty containers, so an unanswered item -
    which by design carries an empty tag list - comes back with no ``tags``
    key at all rather than ``tags: []``. A client doing ``p.tags.length``
    then breaks on exactly the blank words #54 was about.
    """
    return [
        {
            "item_id": entry.get("item_id", ""),
            "answered": entry.get("answered", False),
            "is_correct": entry.get("is_correct"),
            "tags": entry.get("tags") or [],
        }
        for entry in (stored or [])
    ]


def _sentence_tags(measured: Dict[str, Any]) -> List[str]:
    """Per-sentence observations, from the measurements rather than a model."""
    if measured.get("status") == "not_attempted":
        return []
    if measured.get("status") == "needs_review":
        return ["needs_review"]

    tags: List[str] = []
    scores = measured.get("scores", {})
    errors = measured.get("errors", {})
    timing = measured.get("timing", {})
    disfluency = measured.get("disfluency", {})

    if (scores.get("accuracy") or 0) >= 85:
        tags.append("read_accurately")
    elif (scores.get("accuracy") or 0) < 70:
        tags.append("decoding_difficulty")

    if errors.get("clear_error"):
        tags.append("mispronounced_words")
    if errors.get("prolonged"):
        tags.append("stretched_sounds")
    if errors.get("omission"):
        tags.append("skipped_words")
    if timing.get("long_pause_count"):
        tags.append("long_pauses")
    if disfluency.get("filler_count"):
        tags.append("filler_used")
    if disfluency.get("repetitions"):
        tags.append("repeated_words")
    if (scores.get("prosody") or 0) and scores["prosody"] < 60:
        tags.append("flat_delivery")

    return tags


def _per_item_tags_to_dicts(per_items):
    """Serialise ``PerItemTags`` into plain dicts."""
    return [
        {
            "item_id": p.item_id,
            "answered": p.answered,
            "is_correct": p.is_correct,
            "tags": p.tags,
        }
        for p in per_items
    ]


class AssessmentService:
    """Orchestrates scoring, tagging, and persistence for all assessments."""

    def __init__(self) -> None:
        from app.infrastructure.firebase import get_firebase_client

        self._client = get_firebase_client()
        self._scores = ScoreRepository(self._client)

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # =====================================================================
    # LOGIC
    # =====================================================================
    def logic_get_test(self, id_token: str, child_id: str, grade: str) -> Dict[str, Any]:
        verify_paid_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = logic_engine()
        items = engine.get_items(grade_enum)

        formatted = []
        for item in items:
            fmt: Dict[str, Any] = {
                "item_id": item.item_id,
                "item_number": item.item_number,
                "item_type": item.item_type,
                "question_text": item.question_text,
                "difficulty": item.difficulty.value,
                "options": [
                    {
                        "index": opt.index,
                        "text": opt.text,
                        "image_url": opt.image_url,
                    }
                    for opt in item.options
                ],
            }
            if hasattr(item, "sort_config") and item.sort_config:
                fmt["sort_config"] = {
                    "cards": item.sort_config.cards,
                    "rounds": [
                        {
                            "round_number": r.round_number,
                            "sort_rule": r.sort_rule,
                            "num_bins": r.num_bins,
                            "rule_shown": r.rule_shown,
                        }
                        for r in item.sort_config.rounds
                    ],
                }
            formatted.append(fmt)

        import uuid as _uuid

        return {
            "success": True,
            "test_id": str(_uuid.uuid4()),
            "grade": grade,
            "total_items": len(items),
            "instructions": (
                "Listen to each question carefully, then choose your answer. "
                "Think about patterns, relationships, and rules. Take your time!"
            ),
            "items": formatted,
        }

    def logic_submit_response(self, id_token: str, child_id: str, item_id: str,
                              selected_answer_index: int, response_time_seconds: float = 0.0,
                              attempts: int = 1, self_corrected: bool = False,
                              explanation_provided: Optional[str] = None) -> Dict[str, Any]:
        verify_paid_child(id_token, child_id)
        engine = logic_engine()

        all_items = engine.get_all_items()
        item = next((i for i in all_items if i.item_id == item_id), None)
        if not item:
            from app.core.exceptions import ItemNotFoundError

            raise ItemNotFoundError(item_id)

        is_correct = selected_answer_index == item.correct_answer_index

        if is_correct and response_time_seconds < item.expected_latency_seconds:
            feedback = "Correct! You found the right answer. And you were quick!"
        elif is_correct:
            feedback = "Correct! You found the right answer."
        else:
            feedback = "Not quite right. Try again or review the pattern."

        return {
            "item_id": item_id,
            "is_correct": is_correct,
            "tags_earned": [],
            "feedback": feedback,
            "correct_answer_index": item.correct_answer_index,
            "correct_answer": item.options[item.correct_answer_index].text,
        }

    def logic_submit_test(self, id_token: str, child_id: str, grade: str,
                          responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        uid, _ = verify_paid_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = logic_engine()

        domain_responses = [
            LogicResponse(
                item_id=r["item_id"],
                selected_answer_index=r["selected_answer_index"],
                response_time_seconds=r.get("response_time_seconds", 0.0),
                attempts=r.get("attempts", 1),
                self_corrected=r.get("self_corrected", False),
                explanation_provided=r.get("explanation_provided"),
            )
            for r in responses
        ]

        result = engine.evaluate(child_id, grade_enum, domain_responses)

        tag_dicts = _tag_outputs_to_dicts(result.tags)
        per_item_dicts = _per_item_tags_to_dicts(result.per_item_tags)

        logic_scored_items = [s.model_dump() for s in result.score.scored_items]
        logic_tag_map = {p["item_id"]: p.get("tags", []) for p in per_item_dicts}
        for item in logic_scored_items:
            item["detail"]["tags"] = logic_tag_map.get(item.get("item_id", ""), [])

        # G4: Use human-readable descriptions instead of raw tag ids for parent summary.
        strengths = [
            t.description for t in result.tags if t.polarity.value == "strength"
        ]
        focus_areas = [
            t.description for t in result.tags if t.polarity.value == "growth_edge"
        ]

        # G2: Ensure the report never shows only a growth edge with no strength.
        if focus_areas and not strengths:
            strengths = ["Your child is working on these skills and making progress."]

        per_item_map_submit = {
            p.get("item_id", ""): p.get("tags", [])
            for p in per_item_dicts
        }

        def _error_type_for_submit(item_dict: Dict[str, Any]) -> Optional[str]:
            if item_dict.get("is_correct"):
                return None
            tags = per_item_map_submit.get(item_dict.get("item_id", ""), [])
            if "impulsive_response" in tags:
                return "Impulsive response"
            if "reasoning_under_load" in tags or "reasoning_under_load_emerging" in tags:
                return "Reasoning under load"
            if "trial_and_error_strategy" in tags:
                return "Trial and error"
            for tag in tags:
                if tag.endswith("_missed"):
                    return tag.replace("_missed", "").replace("_", " ")
            return "Incorrect"

        table_data_submit = [
            {
                "question": s.get("label", ""),
                # L-D1: these must match the keys LogicScorer writes into
                # ScoredItem.detail, or the teacher table reads null.
                "selected_index": s.get("detail", {}).get("selected_answer_index"),
                "correct_index": s.get("detail", {}).get("correct_answer_index"),
                "correct": s.get("is_correct", False),
                "error_type": _error_type_for_submit(s),
                "time": s.get("detail", {}).get("response_time_seconds", 0.0),
                "icon": "Correct" if s.get("is_correct") else "Incorrect",
            }
            for s in logic_scored_items
        ]

        score_id = self._scores.save(
            uid, child_id, TestType.LOGIC.storage_key,
            {
                "grade": grade,
                "score": result.score.correct_answers,
                "percentage": result.score.percentage,
                "correct_answers": result.score.correct_answers,
                "total_items": result.score.total_items,
                "level": result.score.level,
                "signals": result.signals,
                "dear_parent_tags": tag_dicts,
                "per_item_tags": per_item_dicts,
                "recommendation": result.recommendation,
                "timestamp": self._utc_now(),
                "responses": sanitize_data(responses),
                "scored_items": sanitize_data(logic_scored_items),
            },
        )

        return {
            "success": True,
            "user_id": uid,
            "child_id": child_id,
            "grade": grade,
            "score_id": score_id,
            "score": result.score.correct_answers,
            "percentage": result.score.percentage,
            "correct_answers": result.score.correct_answers,
            "total_items": result.score.total_items,
            "level": result.score.level,
            "parent_summary": {
                "overall_accuracy": result.score.percentage,
                "level": result.score.level,
                "strengths": strengths,
                "focus_areas": focus_areas,
                "recommendation": result.recommendation,
                "note": "Assessment is instructional and not a clinical diagnosis.",
            },
            "dear_parent_tags": tag_dicts,
            "per_item_tags": per_item_dicts,
            "teacher_admin_detail": {
                "test_level": grade,
                "questions": result.score.total_items,
                "correct": result.score.correct_answers,
                "instructional_level": result.score.level,
                "table_data": table_data_submit,
            },
            "recommendation": result.recommendation,
            "signals": result.signals,
            "scored_items": logic_scored_items,
            "timestamp": self._utc_now(),
        }

    def logic_complete_result(self, id_token: str, child_id: str,
                              grade: Optional[str] = None) -> Dict[str, Any]:
        uid, _ = verify_paid_child(id_token, child_id)
        latest = self._scores.get_latest(uid, child_id, TestType.LOGIC.storage_key, grade)
        if not latest:
            raise ResultNotFoundError("logic", child_id, grade)

        scored_items = latest.get("scored_items", [])
        per_item_tags = _restore_per_item_tags(latest.get("per_item_tags", []))
        dear_parent_tags = latest.get("dear_parent_tags", [])

        per_item_map = {p["item_id"]: p["tags"] for p in per_item_tags}

        def _error_type_for(item: Dict[str, Any]) -> Optional[str]:
            if item.get("is_correct"):
                return None
            tags = per_item_map.get(item.get("item_id", ""), [])
            if "impulsive_response" in tags:
                return "Impulsive response"
            if "reasoning_under_load" in tags or "reasoning_under_load_emerging" in tags:
                return "Reasoning under load"
            if "trial_and_error_strategy" in tags:
                return "Trial and error"
            for tag in tags:
                if tag.endswith("_missed"):
                    return tag.replace("_missed", "").replace("_", " ")
            return "Incorrect"

        table_data = [
            {
                "question": s.get("label", ""),
                # L-D1: selected_index / correct_index / time never existed
                # in ScoredItem.detail, so every row read null, null and 0.0.
                "selected_index": s.get("detail", {}).get("selected_answer_index"),
                "correct_index": s.get("detail", {}).get("correct_answer_index"),
                "correct": s.get("is_correct", False),
                "error_type": _error_type_for(s),
                "time": s.get("detail", {}).get("response_time_seconds", 0.0),
                "icon": "Correct" if s.get("is_correct") else "Incorrect",
            }
            for s in scored_items
        ]

        strengths = [
            t.get("description", "") for t in dear_parent_tags
            if t.get("polarity") == "strength"
        ]
        focus_areas = [
            t.get("description", "") for t in dear_parent_tags
            if t.get("polarity") == "growth_edge"
        ]

        # G2: Ensure the report never shows only a growth edge with no strength.
        if focus_areas and not strengths:
            strengths = ["Your child is working on these skills and making progress."]

        return {
            "user_id": uid,
            "child_id": child_id,
            "grade": latest.get("grade"),
            "score": latest.get("score", 0),
            "percentage": latest.get("percentage", 0),
            "correct_answers": latest.get("correct_answers", 0),
            "total_items": latest.get("total_items", 0),
            "level": latest.get("level", ""),
            "parent_summary": {
                "overall_accuracy": latest.get("percentage", 0),
                "level": latest.get("level", ""),
                "strengths": strengths,
                "focus_areas": focus_areas,
                "recommendation": latest.get("recommendation", ""),
                "note": "Assessment is instructional and not a clinical diagnosis.",
            },
            "dear_parent_tags": dear_parent_tags,
            "per_item_tags": per_item_tags,
            "teacher_admin_detail": {
                "test_level": latest.get("grade", grade),
                "questions": len(scored_items),
                "correct": sum(1 for s in scored_items if s.get("is_correct")),
                "instructional_level": latest.get("level", ""),
                "table_data": table_data,
            },
            "recommendation": latest.get("recommendation", ""),
            "signals": latest.get("signals", {}),
            "scored_items": scored_items,
            "timestamp": latest.get("timestamp", ""),
        }

    # =====================================================================
    # SPELLING
    # =====================================================================
    def spelling_get_words(self, grade: str) -> Dict[str, Any]:
        grade_enum = _parse_grade(grade)
        engine = spelling_engine()
        words = engine.build_test(grade_enum)
        return {
            "grade": grade,
            "words": [
                {
                    "word": w.word,
                    "type": w.word_type.value,
                    "sentence": w.sentence,
                }
                for w in words
            ],
        }

    def spelling_submit_words(self, id_token: str, child_id: str, grade: str,
                              words: List[Dict[str, Any]]) -> Dict[str, Any]:
        uid, _ = verify_paid_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = spelling_engine()

        domain_responses = [
            SpellingResponse(
                item_id=w.get("word", ""),
                word=w.get("word", ""),
                user_input=w.get("user_input", ""),
                word_type=WordType(w.get("type", "regular")),
                response_time_seconds=w.get("time", 0.0),
                hints_used=w.get("hints_used", 0),
            )
            for w in words
        ]

        # Only score the words that were actually given to the child.
        # For Kindergarten, build_test draws a random sample of 15 from 31,
        # so we must filter the full bank to just the submitted words.
        submitted_words = {w.get("word", "").strip().lower() for w in words}
        test_items = [
            item for item in engine.get_items(grade_enum)
            if item.word.strip().lower() in submitted_words
        ]

        result = engine.evaluate(child_id, grade_enum, domain_responses, items=test_items)

        tag_dicts = _tag_outputs_to_dicts(result.tags)
        per_item_dicts = _per_item_tags_to_dicts(result.per_item_tags)

        summary = engine.summary_by_category(result.score)
        confidence = engine.confidence_label(result.score)
        focus = engine.focus_areas(result.score)
        strengths = engine.strengths(result.signals)
        error_breakdown = engine.scorer.error_breakdown(result.score)

        scored_items = [s.model_dump() for s in result.score.scored_items]

        per_word_tag_map = {
            p["item_id"]: p.get("tags", [])
            for p in per_item_dicts
        }
        for item in scored_items:
            item_id = item.get("item_id", "")
            item["detail"]["tags"] = per_word_tag_map.get(item_id, [])

        score_id = self._scores.save(
            uid, child_id, TestType.SPELLING.storage_key,
            {
                "grade": grade,
                "evaluation": {
                    "status": engine.scorer.status_for(result.score.percentage),
                    "level": result.score.level,
                    "percentage": result.score.percentage,
                },
                "assessment_summary": sanitize_data(summary),
                "error_analysis": sanitize_data(error_breakdown),
                "instructional_recommendation": result.recommendation,
                "dear_parent_tags": tag_dicts,
                "per_word_tags": per_item_dicts,
                "results": sanitize_data(scored_items),
                "signals": result.signals,
                "confidence": confidence,
                "strengths": strengths,
                "focus_areas": focus,
                "timestamp": self._utc_now(),
            },
        )

        return {
            "user_id": uid,
            "child_id": child_id,
            "grade": grade,
            "score_id": score_id,
            "results": scored_items,
            "evaluation": {
                "status": engine.scorer.status_for(result.score.percentage),
                "level": result.score.level,
                "percentage": result.score.percentage,
            },
            "assessment_summary": summary,
            "error_analysis": error_breakdown,
            "instructional_recommendation": result.recommendation,
            "confidence": confidence,
            "strengths": strengths,
            "focus_areas": focus,
            "dear_parent_tags": tag_dicts,
            "per_word_tags": per_item_dicts,
        }

    def spelling_complete_result(self, id_token: str, child_id: str,
                                 grade: Optional[str] = None) -> Dict[str, Any]:
        uid, _ = verify_paid_child(id_token, child_id)
        latest = self._scores.get_latest(uid, child_id, TestType.SPELLING.storage_key, grade)
        if not latest:
            raise ResultNotFoundError("spelling", child_id, grade)

        results = latest.get("results", [])
        total_words = len(results)
        correct_count = sum(1 for r in results if r.get("is_correct"))
        overall_acc = round(
            sum(r.get("points", 0) for r in results)
            / max(sum(r.get("max_points", 0) for r in results), 1)
            * 100, 1
        ) if results else 0

        phonics = [r for r in results if r.get("detail", {}).get("type") == WordType.REGULAR.value]
        sight = [r for r in results if r.get("detail", {}).get("type") in (
            WordType.SIGHT.value, WordType.NONSENSE.value
        )]

        # #53 / Q3: both scores must match the accuracies in signals, whose
        # denominator is every word SHOWN — sound-alikes and blanks stay in
        # the pool as not-yet-correct rather than shrinking it.
        def _phonics_ok(result: Dict[str, Any]) -> bool:
            """True when the child produced every sound, spelling aside.

            phonics_score means phonics. A convention error (candel, fone) or
            a homophone means the child heard the word correctly and wrote a
            plausible spelling, so it does not count against phonics. Genuine
            sound changes (hambuger, fen for fan) still do.
            """
            if result.get("is_correct"):
                return True
            mistakes = result.get("detail", {}).get("mistakes", {})
            return "spelling_convention" in mistakes or "homophone_error" in mistakes

        phonics_pct = (
            sum(1 for r in phonics if _phonics_ok(r)) / len(phonics) * 100
        ) if phonics else 0
        sight_pct = (
            sum(1 for r in sight if r.get("is_correct")) / len(sight) * 100
        ) if sight else 0

        per_word_tags = _restore_per_item_tags(latest.get("per_word_tags", []))
        per_word_tag_map = {
            p["item_id"]: p["tags"] for p in per_word_tags
        }

        def _error_type_for(result: Dict[str, Any]) -> Optional[str]:
            if result.get("is_correct"):
                return None

            # #55: blank (not answered) words should have no error_type.
            user_input = result.get("detail", {}).get("user_input", "").strip()
            if not user_input:
                return None

            tags = per_word_tag_map.get(result.get("item_id", ""), [])
            if "unrelated_attempt" in tags:
                return "Unrelated attempt"
            if "unrelated_attempt_sightword" in tags:
                return "Sight word (unrelated)"
            if "homophone_error" in tags:
                return "Homophone"

            if result.get("detail", {}).get("type") == WordType.SIGHT.value:
                return "Sight word"

            mistakes = result.get("detail", {}).get("mistakes", {})
            if "spelling_convention" in mistakes:
                return "Spelling convention"
            feature_key = next(
                (k for k in mistakes if k not in ("spelling", "unrelated_attempt", "spelling_convention", "homophone_error")),
                None,
            )
            if feature_key:
                # Every other error_type is capitalised ("Spelling convention",
                # "Homophone"); phonics features were the odd one out.
                return feature_key.replace("_", " ").replace(" error", "").capitalize()
            # #62: if the word has a spelling_error tag or "spelling" mistake
            # key, return "Spelling" instead of None.
            if "spelling_error" in tags or "spelling" in mistakes:
                return "Spelling"
            # #61: rushed_attempt is the least specific error type — check it
            # last so more descriptive tags take priority.
            if "rushed_attempt" in tags:
                return "Rushed attempt"
            return None

        table_data = [
            {
                "word": r.get("label", ""),
                "attempt": r.get("detail", {}).get("user_input", ""),
                "correct": r.get("is_correct", False),
                "error_type": _error_type_for(r),
                "time": r.get("detail", {}).get("time", 0.0),
                "hints_used": r.get("detail", {}).get("hints_used", 0),
                # #54: blank words should show "Not answered" icon.
                "icon": (
                    "Correct" if r.get("is_correct")
                    else ("Not answered" if not r.get("detail", {}).get("user_input", "").strip() else "Incorrect")
                ),
            }
            for r in results
        ]

        return {
            "user_id": uid,
            "child_id": child_id,
            "grade": latest.get("grade", grade),
            "parent_summary": {
                "overall_accuracy": round(overall_acc),
                "phonics_score": round(phonics_pct),
                "sight_word_score": round(sight_pct),
                "confidence": latest.get("confidence", "Medium"),
                "key_error_patterns": [
                    {"pattern": k, "count": v}
                    for k, v in latest.get("error_analysis", {}).items()
                    if v > 0
                ],
                "strengths": latest.get("strengths", []),
                "focus_areas": latest.get("focus_areas", []),
                "recommendation": latest.get("instructional_recommendation", ""),
                "note": "Note: Placement is instructional and not a clinical diagnosis.",
            },
            "dear_parent_tags": latest.get("dear_parent_tags", []),
            "per_word_tags": per_word_tags,
            "teacher_admin_detail": {
                "test_level": latest.get("grade", grade),
                "words": total_words,
                "correct": correct_count,
                "instructional_level": latest.get("grade", grade),
                "table_data": table_data,
            },
        }

    # =====================================================================
    # SPEAKING
    # =====================================================================
    async def speaking_analyze(self, id_token: str, child_id: str, grade: str,
                               original_sentence: str, audio_base64: str,
                               audio_format: str = "wav",
                               time_to_speak_ms: Optional[float] = None) -> Dict[str, Any]:
        """Score a single sentence. Same chain as a full submission."""
        verify_paid_child(id_token, child_id)

        from app.engines.speaking.pipeline import SentenceSubmission, SpeakingPipeline

        measured = await SpeakingPipeline().analyse_sentence(
            SentenceSubmission(
                sentence_id="single",
                reference_text=original_sentence,
                audio_base64=audio_base64,
                audio_format=audio_format or "wav",
                time_to_speak_ms=time_to_speak_ms,
            ),
            grade,
        )

        if measured.get("status") == "not_attempted":
            from app.core.exceptions import AnalysisError

            raise AnalysisError(
                measured.get("message") or "No speech was detected in the recording."
            )

        from app.engines.speaking.feedback import build as build_feedback
        from app.engines.speaking.feedback import level_for as feedback_level

        scores = measured.get("scores", {})
        fb = build_feedback(measured)
        return {
            "original_sentence": original_sentence,
            "transcribed_text": measured.get("recognized", ""),
            "verbatim_text": measured.get("verbatim", ""),
            "status": measured.get("status"),
            "duration_seconds": round(
                (measured.get("timing", {}).get("speaking_span_ms") or 0) / 1000.0, 2
            ),
            "analysis_method": "azure_pronunciation_assessment",
            "pronunciation": {
                "score": scores.get("accuracy", 0.0),
                "feedback": fb["pronunciation_feedback"],
                "words": measured.get("words", []),
                "findings": measured.get("findings", []),
            },
            "fluency": {
                "score": scores.get("fluency", 0.0),
                "fluency_score": scores.get("fluency", 0.0),
                "feedback": fb["fluency_feedback"],
                **measured.get("timing", {}),
            },
            "prosody": {
                "score": scores.get("prosody") or 0.0,
                "feedback": fb["prosody_feedback"],
            },
            "completeness": {
                "score": scores.get("completeness", 0.0),
                "feedback": fb["completeness_feedback"],
            },
            "grammar": {
                "score": scores.get("completeness", 0.0),
                "feedback": fb["completeness_feedback"],
                "issues": [],
            },
            "reading": measured.get("reading", {}),
            "disfluency": measured.get("disfluency", {}),
            "phonics": measured.get("phonics", {}),
            "errors": measured.get("errors", {}),
            "overall": {
                "score": scores.get("pron_score", 0.0),
                "level": feedback_level(scores.get("pron_score", 0.0)),
                "strengths": fb["strengths"],
                "areas_to_improve": fb["areas_to_improve"],
                "recommendation": fb["parent_tip"],
                "parent_tip": fb["parent_tip"],
            },
            "channel_agreement": measured.get("channel_agreement"),
        }

    async def speaking_submit(self, id_token: str, child_id: str, grade: str,
                              sentence_id: Optional[str] = None,
                              original_sentence: Optional[str] = None,
                              audio_base64: Optional[str] = None,
                              audio_format: Optional[str] = "mp3",
                              submissions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Score a whole speaking submission through the Azure signal chain.

        Sentences are analysed concurrently: App Runner enforces a fixed
        120-second request timeout, and eight sentences one after another do
        not fit inside it.
        """
        uid, _ = verify_paid_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = speaking_engine()

        from app.engines.speaking.pipeline import (
            SentenceSubmission,
            SpeakingPipeline,
            aggregate,
        )
        from app.engines.speaking.result import build_sentences, teacher_table

        all_sentences = engine.get_items(grade_enum)

        submitted: Dict[str, Dict[str, Any]] = {}
        if submissions:
            for item in submissions:
                data = item if isinstance(item, dict) else item.model_dump()
                submitted[data.get("sentence_id")] = data
        elif sentence_id:
            submitted[sentence_id] = {
                "sentence_id": sentence_id,
                "original_sentence": original_sentence or "",
                "audio_base64": audio_base64 or "",
                "audio_format": audio_format or "wav",
            }

        pipeline_input: List[SentenceSubmission] = []
        for sent in all_sentences:
            item = submitted.get(sent.sentence_id) or {}
            pipeline_input.append(SentenceSubmission(
                sentence_id=sent.sentence_id,
                reference_text=sent.sentence,
                audio_base64=item.get("audio_base64") or "",
                audio_format=item.get("audio_format") or "wav",
                time_to_speak_ms=item.get("time_to_speak_ms"),
                attempt=int(item.get("attempt") or 1),
            ))

        measured = await SpeakingPipeline().analyse(pipeline_input, grade)
        signals = aggregate(measured, grade)

        by_id = {m["sentence_id"]: m for m in measured}
        text_by_id = {sent.sentence_id: sent.sentence for sent in all_sentences}

        # Per-sentence tags first, so the sentence object can carry them.
        tags_by_id = {
            m["sentence_id"]: _sentence_tags(m) for m in measured
        }

        sentences = build_sentences(measured, text_by_id, tags_by_id)

        domain_responses: List[SpeakingResponse] = []
        total_score = 0.0
        answered_count = 0
        for sent in all_sentences:
            m = by_id[sent.sentence_id]
            if m.get("status") == "answered":
                total_score += m.get("scores", {}).get("pron_score", 0.0) or 0.0
                answered_count += 1
            item = submitted.get(sent.sentence_id) or {}
            domain_responses.append(SpeakingResponse(
                item_id=sent.sentence_id,
                sentence_id=sent.sentence_id,
                original_sentence=sent.sentence,
                audio_base64=item.get("audio_base64", ""),
                audio_format=item.get("audio_format", "wav"),
            ))

        # The tag engine reads the aggregate signals directly - the chain has
        # already done every measurement the old deriver used to approximate.
        from app.tagging.emitter import emit_tags

        tags = emit_tags(TestType.SPEAKING, signals)
        tag_dicts = _tag_outputs_to_dicts(tags)

        per_item_dicts = [
            {
                "item_id": m["sentence_id"],
                "answered": m.get("status") == "answered",
                "is_correct": None,
                "tags": tags_by_id[m["sentence_id"]],
            }
            for m in measured
        ]

        max_score = len(all_sentences) * 100
        user_score = round(total_score, 1)
        # The headline is the average of the sentences the child actually
        # read. Dividing by every sentence in the test reported 12% for a
        # child who read one sentence at 95.9, which describes how much of
        # the test was attempted, not how well it was read. Attempted is
        # reported separately, where it can be read for what it is.
        avg_score = round(total_score / answered_count, 1) if answered_count else 0
        percentage = avg_score

        if avg_score >= 90:
            level = "Excellent Speaker"
        elif avg_score >= 75:
            level = "Good Speaker"
        elif avg_score >= 50:
            level = "Developing Speaker"
        else:
            level = "Needs Improvement"

        test_id = self._scores.save(
            uid, child_id, TestType.SPEAKING.storage_key,
            {
                "grade": grade,
                "sentences": sanitize_data(sentences),
                "total_marks": max_score,
                "user_score": user_score,
                "answered_count": answered_count,
                "average_score": avg_score,
                "percentage": percentage,
                "level": level,
                "signals": sanitize_data(signals),
                "dear_parent_tags": tag_dicts,
                "per_sentence_tags": per_item_dicts,
                "timestamp": self._utc_now(),
            },
        )

        return {
            "success": True,
            "user_id": uid,
            "child_id": child_id,
            "grade": grade,
            "test_id": test_id,
            "total_marks": max_score,
            "user_score": user_score,
            "answered_count": answered_count,
            "average_score": avg_score,
            "percentage": percentage,
            "level": level,
            "sentences": sentences,
            "teacher_admin_detail": {
                "test_level": grade,
                "sentences": len(sentences),
                "answered": answered_count,
                "instructional_level": level,
                "table_data": teacher_table(sentences),
            },
            "signals": signals,
            "dear_parent_tags": tag_dicts,
            "per_sentence_tags": per_item_dicts,
            "message": (
                f"Submission completed: {answered_count} answered, "
                f"{len(sentences) - answered_count} not attempted."
            ),
        }

    def speaking_complete_result(self, id_token: str, child_id: str,
                                 grade: Optional[str] = None) -> Dict[str, Any]:
        """The stored result, in the same per-sentence shape submit returns."""
        uid, _ = verify_paid_child(id_token, child_id)
        latest = self._scores.get_latest(
            uid, child_id, TestType.SPEAKING.storage_key, grade)
        if not latest:
            raise ResultNotFoundError("speaking", child_id, grade)

        percentage = latest.get("percentage", 0)
        if percentage >= 90:
            placement = "Above Grade Level"
        elif percentage >= 75:
            placement = "At Grade Level"
        else:
            placement = "Below Grade Level"

        sentences = _restore_sentences(latest.get("sentences", []))
        dear_parent_tags = latest.get("dear_parent_tags", [])

        return {
            "user_id": uid,
            "child_id": child_id,
            "grade": latest.get("grade"),
            "timestamp": latest.get("timestamp", ""),

            "summary": {
                "sentences": len(sentences),
                "answered": sum(1 for s in sentences if s["answered"]),
                "needs_review": sum(
                    1 for s in sentences if s["status"] == "needs_review"),
                "total_marks": latest.get("total_marks", 0),
                "user_score": latest.get("user_score", 0),
                "average_score": latest.get("average_score", 0),
                "percentage": percentage,
                "level": latest.get("level", ""),
                "grade_placement": placement,
            },

            "parent_summary": {
                "level": latest.get("level", ""),
                "strengths": [
                    t.get("description") or t.get("tag", "")
                    for t in dear_parent_tags if t.get("polarity") == "strength"
                ],
                "focus_areas": [
                    t.get("description") or t.get("tag", "")
                    for t in dear_parent_tags
                    if t.get("polarity") == "growth_edge"
                ],
                "grade_placement": placement,
                "note": (
                    "Assessment is instructional and not a clinical diagnosis."
                ),
            },

            "dear_parent_tags": dear_parent_tags,
            "signals": latest.get("signals", {}),
            "sentences": sentences,

            # Derived from `sentences` above, never stored alongside them, so
            # the table cannot drift from the results it summarises.
            "teacher_admin_detail": {
                "test_level": latest.get("grade", grade),
                "sentences": len(sentences),
                "answered": sum(1 for s in sentences if s["answered"]),
                "instructional_level": placement,
                "table_data": _speaking_table(sentences),
            },
        }

    # =====================================================================
    # COMPREHENSION
    # =====================================================================
    def comprehension_submit(self, id_token: str, child_id: str, grade: str,
                             story_answers: List[Dict[str, Any]]) -> Dict[str, Any]:
        uid, _ = verify_paid_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = comprehension_engine()

        domain_responses: List[ComprehensionResponse] = []
        for story_answer in story_answers:
            for qa in story_answer.get("answers", []):
                domain_responses.append(ComprehensionResponse(
                    item_id=qa["question_id"],
                    question_id=qa["question_id"],
                    selected_index=qa["selected_index"],
                    response_time_seconds=qa.get("response_time_seconds", 0.0),
                ))

        result = engine.evaluate(child_id, grade_enum, domain_responses)

        tag_dicts = _tag_outputs_to_dicts(result.tags)
        per_item_dicts = _per_item_tags_to_dicts(result.per_item_tags)

        status = engine.status(result.score)
        story_breakdown = engine.story_breakdown(result.score)

        scored_items = [s.model_dump() for s in result.score.scored_items]

        comp_tag_map = {p["item_id"]: p.get("tags", []) for p in per_item_dicts}
        for item in scored_items:
            item["detail"]["tags"] = comp_tag_map.get(item.get("item_id", ""), [])

        # C3: Use human-readable descriptions instead of raw tag ids.
        strengths = [
            t.description for t in result.tags if t.polarity.value == "strength"
        ]
        focus_areas = [
            t.description for t in result.tags if t.polarity.value == "growth_edge"
        ]

        # C4: Fallback copy for sparse reports.
        if not strengths and not focus_areas:
            strengths = ["There wasn't quite enough here to say something specific yet. That's normal, and worth trying again in a few months."]
        elif focus_areas and not strengths:
            strengths = ["Your child is working on these skills and making progress."]

        percentage = result.score.percentage
        if percentage >= 90:
            placement = "Above Grade Level"
            next_step = "Consider more advanced reading materials"
        elif percentage >= 75:
            placement = "At Grade Level"
            next_step = "Continue with current grade level materials"
        else:
            placement = "Below Grade Level"
            next_step = "Practice with guided reading and comprehension activities"

        test_id = self._scores.save(
            uid, child_id, TestType.COMPREHENSION.storage_key,
            {
                "grade": grade,
                "results": sanitize_data(story_breakdown),
                # C8: a question count is a whole number, not 11.0.
                "total_questions": int(result.score.max_points),
                "correct_answers": result.score.correct_answers,
                "score": result.score.correct_answers,
                "max_score": int(result.score.max_points),
                "percentage": result.score.percentage,
                "level": result.score.level,
                "status": status,
                "recommendation": result.recommendation,
                "dear_parent_tags": tag_dicts,
                "per_question_tags": per_item_dicts,
                "signals": result.signals,
                "timestamp": self._utc_now(),
                "scored_items": sanitize_data(scored_items),
            },
        )

        return {
            "success": True,
            "user_id": uid,
            "child_id": child_id,
            "grade": grade,
            "test_id": test_id,
            "total_questions": int(result.score.max_points),
            "correct_answers": result.score.correct_answers,
            "score": result.score.correct_answers,
            "max_score": int(result.score.max_points),
            "percentage": result.score.percentage,
            "level": result.score.level,
            "status": status,
            "recommendation": result.recommendation,
            "results": story_breakdown,
            "parent_summary": {
                "overall_score": f"{result.score.correct_answers}/{int(result.score.max_points)}",
                "percentage": result.score.percentage,
                "level": result.score.level,
                "strengths": strengths,
                "focus_areas": focus_areas,
                "grade_placement": placement,
                "next_step": next_step,
                "recommendation": result.recommendation,
                "note": "Assessment is instructional and not a clinical diagnosis.",
            },
            "dear_parent_tags": tag_dicts,
            "per_question_tags": per_item_dicts,
            "signals": result.signals,
            "scored_items": scored_items,
            "timestamp": self._utc_now(),
        }

    def comprehension_complete_result(self, id_token: str, child_id: str,
                                      grade: Optional[str] = None) -> Dict[str, Any]:
        uid, _ = verify_paid_child(id_token, child_id)
        latest = self._scores.get_latest(uid, child_id, TestType.COMPREHENSION.storage_key, grade)
        if not latest:
            raise ResultNotFoundError("comprehension", child_id, grade)

        percentage = latest.get("percentage", 0)
        if percentage >= 90:
            placement = "Above Grade Level"
            next_step = "Consider more advanced reading materials"
        elif percentage >= 75:
            placement = "At Grade Level"
            next_step = "Continue with current grade level materials"
        else:
            placement = "Below Grade Level"
            next_step = "Practice with guided reading and comprehension activities"

        story_breakdown = latest.get("results", [])
        per_question_tags = latest.get("per_question_tags", [])
        dear_parent_tags = latest.get("dear_parent_tags", [])

        per_question_map = {
            p.get("item_id", ""): p.get("tags", [])
            for p in per_question_tags
        }

        scored_items = latest.get("scored_items", [])

        def _error_type_for(item: Dict[str, Any]) -> Optional[str]:
            if item.get("is_correct"):
                return None
            tags = per_question_map.get(item.get("item_id", ""), [])
            for tag in tags:
                if tag.endswith("_error"):
                    return tag.replace("_error", " error")
            return "Incorrect"

        table_data = [
            {
                "question": s.get("label", ""),
                "story_id": s.get("detail", {}).get("story_id", ""),
                "story_title": s.get("detail", {}).get("story_title", ""),
                "selected_index": s.get("detail", {}).get("selected_index"),
                "correct_index": s.get("detail", {}).get("correct_index"),
                "correct": s.get("is_correct", False),
                "error_type": _error_type_for(s),
                # C5: the scorer has always held this; the view dropped it.
                "time": s.get("detail", {}).get("response_time_seconds", 0.0),
                "icon": "Correct" if s.get("is_correct") else "Incorrect",
            }
            for s in scored_items
        ]

        strengths = [
            t.get("description", "") for t in dear_parent_tags
            if t.get("polarity") == "strength"
        ]
        focus_areas = [
            t.get("description", "") for t in dear_parent_tags
            if t.get("polarity") == "growth_edge"
        ]

        # C4: If no tags fired, show warm fallback copy instead of blank lists.
        # C7: this used to fire on a child with nine tagged errors, because no
        # growth-edge tag existed to carry them. With the _emerging partners in
        # place it should now only appear on a genuinely empty submission.
        if not strengths and not focus_areas:
            strengths = ["There wasn't quite enough here to say something specific yet. That's normal, and worth trying again in a few months."]
        elif focus_areas and not strengths:
            strengths = ["Your child is working on these skills and making progress."]

        return {
            "user_id": uid,
            "child_id": child_id,
            "grade": latest.get("grade"),
            "test_timestamp": latest.get("timestamp"),
            "summary": {
                "total_questions": int(latest.get("max_score", 8) or 0),
                "correct_answers": latest.get("correct_answers", 0),
                "percentage": percentage,
                "level": latest.get("level", "Below grade level"),
                "status": latest.get("status", "Below"),
            },
            "parent_summary": {
                "overall_score": f"{latest.get('correct_answers', 0)}/{int(latest.get('max_score', 8))}",
                "percentage": percentage,
                "level": latest.get("level", "Below grade level"),
                "strengths": strengths,
                "focus_areas": focus_areas,
                "grade_placement": placement,
                "next_step": next_step,
                "recommendation": latest.get("recommendation", ""),
                "note": "Assessment is instructional and not a clinical diagnosis.",
            },
            "story_breakdown": story_breakdown,
            "dear_parent_tags": dear_parent_tags,
            "per_question_tags": per_question_tags,
            "teacher_admin_detail": {
                "test_level": latest.get("grade", grade),
                "questions": len(scored_items),
                "correct": sum(1 for s in scored_items if s.get("is_correct")),
                "instructional_level": latest.get("level", ""),
                "table_data": table_data,
            },
        }
