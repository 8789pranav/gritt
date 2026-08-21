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
from app.core.security import verify_child
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
        verify_child(id_token, child_id)
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
        verify_child(id_token, child_id)
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
        uid, _ = verify_child(id_token, child_id)
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
                "message": result.message,
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
            "dear_parent_tags": tag_dicts,
            "per_item_tags": per_item_dicts,
            "recommendation": result.recommendation,
            "message": result.message,
        }

    def logic_complete_result(self, id_token: str, child_id: str,
                              grade: Optional[str] = None) -> Dict[str, Any]:
        uid, _ = verify_child(id_token, child_id)
        latest = self._scores.get_latest(uid, child_id, TestType.LOGIC.storage_key, grade)
        if not latest:
            raise ResultNotFoundError("logic", child_id, grade)

        scored_items = latest.get("scored_items", [])
        per_item_tags = latest.get("per_item_tags", [])
        dear_parent_tags = latest.get("dear_parent_tags", [])

        per_item_map = {
            p.get("item_id", ""): p.get("tags", [])
            for p in per_item_tags
        }

        def _error_type_for(item: Dict[str, Any]) -> Optional[str]:
            if item.get("is_correct"):
                return None
            tags = per_item_map.get(item.get("item_id", ""), [])
            if "impulsive_response" in tags:
                return "Impulsive response"
            if "reasoning_under_load_emerging" in tags:
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
                "selected_index": s.get("detail", {}).get("selected_index"),
                "correct_index": s.get("detail", {}).get("correct_index"),
                "correct": s.get("is_correct", False),
                "error_type": _error_type_for(s),
                "time": s.get("detail", {}).get("time", 0.0),
                "icon": "Correct" if s.get("is_correct") else "Incorrect",
            }
            for s in scored_items
        ]

        strengths = [
            t.get("tag", "") for t in dear_parent_tags
            if t.get("polarity") == "strength"
        ]
        focus_areas = [
            t.get("tag", "") for t in dear_parent_tags
            if t.get("polarity") == "growth_edge"
        ]

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
        uid, _ = verify_child(id_token, child_id)
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

        result = engine.evaluate(child_id, grade_enum, domain_responses)

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
        uid, _ = verify_child(id_token, child_id)
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

        phonics_pct = (
            sum(r["points"] for r in phonics) / sum(r["max_points"] for r in phonics) * 100
        ) if phonics else 0
        sight_pct = (
            sum(r["points"] for r in sight) / sum(r["max_points"] for r in sight) * 100
        ) if sight else 0

        per_word_tag_map = {
            p.get("item_id", ""): p.get("tags", [])
            for p in latest.get("per_word_tags", [])
        }

        def _error_type_for(result: Dict[str, Any]) -> Optional[str]:
            if result.get("is_correct"):
                return None

            tags = per_word_tag_map.get(result.get("item_id", ""), [])
            if "unrelated_attempt" in tags:
                return "Unrelated attempt"
            if "unrelated_attempt_sightword" in tags:
                return "Sight word (unrelated)"
            if "rushed_attempt" in tags:
                return "Rushed attempt"

            if result.get("detail", {}).get("type") == WordType.SIGHT.value:
                return "Sight word"

            mistakes = result.get("detail", {}).get("mistakes", {})
            feature_key = next(
                (k for k in mistakes if k not in ("spelling", "unrelated_attempt")),
                None,
            )
            if feature_key:
                return feature_key.replace("_", " ").replace(" error", "")
            return None

        table_data = [
            {
                "word": r.get("label", ""),
                "attempt": r.get("detail", {}).get("user_input", ""),
                "correct": r.get("is_correct", False),
                "error_type": _error_type_for(r),
                "time": r.get("detail", {}).get("time", 0.0),
                "hints_used": r.get("detail", {}).get("hints_used", 0),
                "icon": "Correct" if r.get("is_correct") else "Incorrect",
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
            "per_word_tags": latest.get("per_word_tags", []),
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
                               audio_format: str = "mp3") -> Dict[str, Any]:
        verify_child(id_token, child_id)
        from app.infrastructure.hybrid_speech import HybridSpeechProvider

        speech = HybridSpeechProvider()

        result = await speech.analyze_with_audio(
            audio_base64, audio_format, original_sentence, grade
        )
        if not result["success"] or not result["analysis"]:
            from app.core.exceptions import AnalysisError

            raise AnalysisError(result.get("error", "Analysis failed"))

        analysis = result["analysis"]
        return {
            "original_sentence": original_sentence,
            "transcribed_text": result.get("transcribed_text", ""),
            "duration_seconds": result.get("duration", 0),
            "word_timestamps": result.get("word_timestamps", []),
            "analysis_method": "hybrid_wav2vec2_gpt4",
            "pronunciation": analysis.get("pronunciation", {}),
            "speaking_rate": analysis.get("speaking_rate", {}),
            "fluency": analysis.get("fluency", {}),
            "prosody": analysis.get("prosody", {}),
            "grammar": analysis.get("grammar", {}),
            "overall": analysis.get("overall", {}),
            "recommendation": analysis.get("overall", {}).get("recommendation", ""),
            "parent_tip": analysis.get("overall", {}).get("parent_tip", ""),
        }

    async def speaking_submit(self, id_token: str, child_id: str, grade: str,
                              sentence_id: Optional[str] = None,
                              original_sentence: Optional[str] = None,
                              audio_base64: Optional[str] = None,
                              audio_format: Optional[str] = "mp3",
                              submissions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        uid, _ = verify_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = speaking_engine()

        from app.infrastructure.hybrid_speech import HybridSpeechProvider

        speech = HybridSpeechProvider()

        all_sentences = engine.get_items(grade_enum)
        sentence_map = {s.sentence_id: s for s in all_sentences}

        submitted: Dict[str, Dict[str, Any]] = {}
        if submissions:
            for item in submissions:
                sid = item.get("sentence_id") if isinstance(item, dict) else item.sentence_id
                submitted[sid] = item
        elif sentence_id:
            submitted[sentence_id] = {
                "sentence_id": sentence_id,
                "original_sentence": original_sentence or "",
                "audio_base64": audio_base64 or "",
                "audio_format": audio_format or "mp3",
            }

        domain_responses: List[SpeakingResponse] = []
        analyses: Dict[str, Any] = {}
        results: List[Dict[str, Any]] = []
        total_score = 0.0
        answered_count = 0

        for sent in all_sentences:
            sid = sent.sentence_id
            item = submitted.get(sid)

            if item is None or not (
                item.get("audio_base64") if isinstance(item, dict) else getattr(item, "audio_base64", "")
            ):
                results.append({
                    "sentence_id": sid,
                    "original_sentence": sent.sentence,
                    "transcribed_text": "",
                    "duration_seconds": 0,
                    "pronunciation": {},
                    "speaking_rate": {},
                    "fluency": {},
                    "grammar": {},
                    "overall": {"score": 0, "status": "Not Attempted", "level": "Not Attempted"},
                    "recommendation": "Not attempted.",
                    "analysis_method": "",
                    "status": "Not Attempted",
                })
                domain_responses.append(SpeakingResponse(
                    item_id=sid,
                    sentence_id=sid,
                    original_sentence=sent.sentence,
                ))
                continue

            audio_b64 = item.get("audio_base64", "") if isinstance(item, dict) else getattr(item, "audio_base64", "")
            audio_fmt = item.get("audio_format", "mp3") if isinstance(item, dict) else getattr(item, "audio_format", "mp3")

            ai_result = await speech.analyze_with_audio(
                audio_b64, audio_fmt, sent.sentence, grade
            )

            if ai_result["success"] and ai_result["analysis"]:
                analysis = ai_result["analysis"]
                from app.engines.speaking.analyzer import SpeechAnalysis

                speech_analysis = SpeechAnalysis.from_provider_payload(analysis)
                analyses[sid] = speech_analysis

                overall = analysis.get("overall", {})
                overall_score = overall.get("score", 0)
                total_score += overall_score
                answered_count += 1

                results.append({
                    "sentence_id": sid,
                    "original_sentence": sent.sentence,
                    "transcribed_text": ai_result.get("transcribed_text", ""),
                    "duration_seconds": ai_result.get("duration", 0),
                    "pronunciation": analysis.get("pronunciation", {}),
                    "speaking_rate": analysis.get("speaking_rate", {}),
                    "fluency": analysis.get("fluency", {}),
                    "prosody": analysis.get("prosody", {}),
                    "grammar": analysis.get("grammar", {}),
                    "overall": overall,
                    "recommendation": overall.get("recommendation", "Keep practicing!"),
                    "analysis_method": "hybrid_wav2vec2_gpt4",
                    "status": "Answered",
                })
                domain_responses.append(SpeakingResponse(
                    item_id=sid,
                    sentence_id=sid,
                    original_sentence=sent.sentence,
                    audio_base64=audio_b64,
                    audio_format=audio_fmt,
                ))
            else:
                results.append({
                    "sentence_id": sid,
                    "original_sentence": sent.sentence,
                    "transcribed_text": ai_result.get("transcribed_text", ""),
                    "analysis": None,
                    "status": "Analysis Error",
                })
                domain_responses.append(SpeakingResponse(
                    item_id=sid,
                    sentence_id=sid,
                    original_sentence=sent.sentence,
                ))

        result = engine.evaluate_with_analyses(child_id, grade_enum, domain_responses, analyses)

        tag_dicts = _tag_outputs_to_dicts(result.tags)
        per_item_dicts = _per_item_tags_to_dicts(result.per_item_tags)

        speaking_tag_map = {p["item_id"]: p.get("tags", []) for p in per_item_dicts}
        for r in results:
            sid = r.get("sentence_id", "")
            r["tags"] = speaking_tag_map.get(sid, [])

        max_score = len(all_sentences) * 100
        user_score = round(total_score, 1)
        percentage = round((user_score / max_score) * 100, 1) if max_score else 0
        avg_score = round(total_score / len(all_sentences), 1) if all_sentences else 0

        if percentage >= 90:
            level = "Excellent Speaker"
        elif percentage >= 75:
            level = "Good Speaker"
        elif percentage >= 50:
            level = "Developing Speaker"
        else:
            level = "Needs Improvement"

        test_id = self._scores.save(
            uid, child_id, TestType.SPEAKING.storage_key,
            {
                "grade": grade,
                "results": sanitize_data(results),
                "total_marks": max_score,
                "user_score": user_score,
                "answered_count": answered_count,
                "average_score": avg_score,
                "percentage": percentage,
                "level": level,
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
            "results": results,
            "dear_parent_tags": tag_dicts,
            "per_sentence_tags": per_item_dicts,
            "message": (
                f"Submission completed: {answered_count} answered, "
                f"{len(results) - answered_count} not attempted."
            ),
        }

    def speaking_complete_result(self, id_token: str, child_id: str,
                                 grade: Optional[str] = None) -> Dict[str, Any]:
        uid, _ = verify_child(id_token, child_id)
        latest = self._scores.get_latest(uid, child_id, TestType.SPEAKING.storage_key, grade)
        if not latest:
            raise ResultNotFoundError("speaking", child_id, grade)

        percentage = latest.get("percentage", 0)
        if percentage >= 90:
            placement = "Above Grade Level"
        elif percentage >= 75:
            placement = "At Grade Level"
        else:
            placement = "Below Grade Level"

        all_results = latest.get("results", [])
        per_sentence_tags = latest.get("per_sentence_tags", [])
        dear_parent_tags = latest.get("dear_parent_tags", [])

        per_sentence_map = {
            p.get("item_id", ""): p.get("tags", [])
            for p in per_sentence_tags
        }

        def _error_type_for(result: Dict[str, Any]) -> Optional[str]:
            status = result.get("status", "")
            if status == "Not Attempted":
                return "Not attempted"
            if status == "Analysis Error":
                return "Analysis error"
            overall = result.get("overall", {})
            score = overall.get("score", 0)
            if score >= 75:
                return None
            tags = per_sentence_map.get(result.get("sentence_id", ""), [])
            for tag in tags:
                if tag.endswith("_needs_work"):
                    return tag.replace("_needs_work", " needs work")
            if score < 50:
                return "Below benchmark"
            return "Developing"

        table_data = [
            {
                "sentence": r.get("original_sentence", ""),
                "sentence_id": r.get("sentence_id", ""),
                "status": r.get("status", ""),
                "overall_score": r.get("overall", {}).get("score", 0),
                "level": r.get("overall", {}).get("level", ""),
                "error_type": _error_type_for(r),
                "icon": "Correct" if r.get("overall", {}).get("score", 0) >= 75 else "Incorrect",
            }
            for r in all_results
        ]

        strengths = [
            t.get("tag", "") for t in dear_parent_tags
            if t.get("polarity") == "strength"
        ]
        focus_areas = [
            t.get("tag", "") for t in dear_parent_tags
            if t.get("polarity") == "growth_edge"
        ]

        return {
            "user_id": uid,
            "child_id": child_id,
            "grade": latest.get("grade"),
            "total_marks": latest.get("total_marks", 100),
            "user_score": latest.get("user_score", 0),
            "answered_count": latest.get("answered_count", 0),
            "average_score": latest.get("average_score", 0),
            "percentage": percentage,
            "level": latest.get("level", "Developing Speaker"),
            "parent_summary": {
                "level": latest.get("level", "Developing Speaker"),
                "strengths": strengths,
                "focus_areas": focus_areas,
                "recommendation": "See detailed feedback for each sentence.",
                "grade_placement": placement,
                "note": "Assessment is instructional and not a clinical diagnosis.",
            },
            "dear_parent_tags": dear_parent_tags,
            "per_sentence_tags": per_sentence_tags,
            "teacher_admin_detail": {
                "test_level": latest.get("grade", grade),
                "sentences": len(all_results),
                "answered": latest.get("answered_count", 0),
                "instructional_level": placement,
                "table_data": table_data,
            },
            "all_results": all_results,
        }

    # =====================================================================
    # COMPREHENSION
    # =====================================================================
    def comprehension_submit(self, id_token: str, child_id: str, grade: str,
                             story_answers: List[Dict[str, Any]]) -> Dict[str, Any]:
        uid, _ = verify_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = comprehension_engine()

        domain_responses: List[ComprehensionResponse] = []
        for story_answer in story_answers:
            for qa in story_answer.get("answers", []):
                domain_responses.append(ComprehensionResponse(
                    item_id=qa["question_id"],
                    question_id=qa["question_id"],
                    selected_index=qa["selected_index"],
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

        test_id = self._scores.save(
            uid, child_id, TestType.COMPREHENSION.storage_key,
            {
                "grade": grade,
                "results": sanitize_data(story_breakdown),
                "total_questions": result.score.max_points,
                "correct_answers": result.score.correct_answers,
                "score": result.score.correct_answers,
                "max_score": result.score.max_points,
                "percentage": result.score.percentage,
                "level": result.score.level,
                "status": status,
                "recommendation": result.recommendation,
                "dear_parent_tags": tag_dicts,
                "per_question_tags": per_item_dicts,
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
            "dear_parent_tags": tag_dicts,
            "per_question_tags": per_item_dicts,
            "message": result.message,
        }

    def comprehension_complete_result(self, id_token: str, child_id: str,
                                      grade: Optional[str] = None) -> Dict[str, Any]:
        uid, _ = verify_child(id_token, child_id)
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
                "icon": "Correct" if s.get("is_correct") else "Incorrect",
            }
            for s in scored_items
        ]

        strengths = [
            t.get("tag", "") for t in dear_parent_tags
            if t.get("polarity") == "strength"
        ]
        focus_areas = [
            t.get("tag", "") for t in dear_parent_tags
            if t.get("polarity") == "growth_edge"
        ]

        return {
            "user_id": uid,
            "child_id": child_id,
            "grade": latest.get("grade"),
            "test_timestamp": latest.get("timestamp"),
            "summary": {
                "total_questions": latest.get("max_score", 8),
                "correct_answers": latest.get("correct_answers", 0),
                "percentage": percentage,
                "level": latest.get("level", "Developing Reader"),
                "status": latest.get("status", "Below"),
            },
            "parent_summary": {
                "overall_score": f"{latest.get('correct_answers', 0)}/{latest.get('max_score', 8)}",
                "percentage": percentage,
                "level": latest.get("level", "Developing Reader"),
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
