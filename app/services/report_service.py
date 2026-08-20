"""Report service: aggregates all assessment data and generates a holistic report.

This service:
  1. Fetches the latest results for each assessment type (logic, spelling,
     speaking, comprehension) for a child in a specific grade.
  2. Aggregates scores, tags, per-item tags, and signals into a structured
     context object.
  3. Calls the AI provider to synthesise a parent-friendly report.
  4. Validates the AI output — every cited tag must exist in the actual data.
  5. Persists the report to Firebase.
  6. Returns the complete report.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.core.security import verify_child
from app.domain.enums import TestType
from app.infrastructure.repositories import ScoreRepository, sanitize_data
from app.services.ai_provider import AIProvider, get_ai_provider

logger = logging.getLogger(__name__)


class ReportService:
    """Aggregates assessment data and generates holistic reports."""

    def __init__(
        self,
        scores: Optional[ScoreRepository] = None,
        ai: Optional[AIProvider] = None,
    ) -> None:
        self._scores = scores or ScoreRepository()
        self._ai = ai or get_ai_provider()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate_final_report(
        self,
        id_token: str,
        child_id: str,
        grade: str,
    ) -> Dict[str, Any]:
        """Generate a holistic report from all assessment results.

        Parameters
        ----------
        id_token
            Firebase ID token for authentication.
        child_id
            The child whose report is being generated.
        grade
            Grade level to filter results by.

        Returns
        -------
        dict
            The complete report containing:
            - ``domain_summary`` — raw scores per assessment (no AI)
            - ``ai_report`` — AI-synthesised narrative with strengths,
              growth areas, cross-domain patterns, and recommendations
            - ``all_tags`` — aggregated tags grouped by polarity
            - ``metadata`` — child info, grade, timestamp
        """
        uid, child_data = verify_child(id_token, child_id)

        # 1. Fetch latest results for each assessment type
        logic_data = self._scores.get_latest(
            uid, child_id, TestType.LOGIC.storage_key, grade
        )
        spelling_data = self._scores.get_latest(
            uid, child_id, TestType.SPELLING.storage_key, grade
        )
        speaking_data = self._scores.get_latest(
            uid, child_id, TestType.SPEAKING.storage_key, grade
        )
        comprehension_data = self._scores.get_latest(
            uid, child_id, TestType.COMPREHENSION.storage_key, grade
        )

        # 2. Build the structured context for the AI
        context = self._build_context(
            child_data, grade,
            logic_data, spelling_data, speaking_data, comprehension_data,
        )

        # 3. Build the domain summary (pure data, no AI)
        domain_summary = self._build_domain_summary(
            logic_data, spelling_data, speaking_data, comprehension_data,
        )

        # 4. Collect all known tag IDs for validation
        known_tags = self._collect_all_tag_ids(context)

        # 5. Call AI to synthesise the report
        ai_report = self._ai.synthesize_report(context)

        # 6. Validate — remove any evidence_tags that don't exist in the data
        ai_report = self._validate_report(ai_report, known_tags)

        # 7. Build top-5 tags and per-test importance
        top_5_tags = self._build_top_5_tags(context)
        test_importance = self._build_test_importance(context, domain_summary)

        # 8. Assemble the final report
        report = {
            "success": True,
            "child_id": child_id,
            "child_name": child_data.get("name", ""),
            "grade": grade,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "domain_summary": domain_summary,
            "top_5_tags": top_5_tags,
            "test_importance": test_importance,
            "all_tags": {
                "strengths": [
                    t for t in context.get("all_strength_tags", [])
                ],
                "growth_edges": [
                    t for t in context.get("all_growth_edge_tags", [])
                ],
                "unanswered": [
                    t for t in context.get("all_unanswered_tags", [])
                ],
            },
            "ai_report": ai_report,
            "assessments_included": [
                k for k in ("logic", "spelling", "speaking", "comprehension")
                if context["assessments"].get(k) is not None
            ],
            "assessments_missing": [
                k for k in ("logic", "spelling", "speaking", "comprehension")
                if context["assessments"].get(k) is None
            ],
        }

        # 9. Persist the report
        self._scores.save(
            uid, child_id, "final_reports",
            {
                "grade": grade,
                "report": sanitize_data(report),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return report

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------
    def _build_context(
        self,
        child_data: Dict[str, Any],
        grade: str,
        logic_data: Optional[Dict[str, Any]],
        spelling_data: Optional[Dict[str, Any]],
        speaking_data: Optional[Dict[str, Any]],
        comprehension_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build the structured context dict that will be sent to the AI."""
        context: Dict[str, Any] = {
            "child": {
                "name": child_data.get("name", ""),
                "age": child_data.get("age", 0),
                "grade": grade,
            },
            "assessments": {},
            "all_strength_tags": [],
            "all_growth_edge_tags": [],
            "all_unanswered_tags": [],
        }

        if logic_data:
            logic_ctx = self._build_logic_context(logic_data)
            context["assessments"]["logic"] = logic_ctx
            self._collect_tags(logic_ctx, context)

        if spelling_data:
            spelling_ctx = self._build_spelling_context(spelling_data)
            context["assessments"]["spelling"] = spelling_ctx
            self._collect_tags(spelling_ctx, context)

        if speaking_data:
            speaking_ctx = self._build_speaking_context(speaking_data)
            context["assessments"]["speaking"] = speaking_ctx
            self._collect_tags(speaking_ctx, context)

        if comprehension_data:
            comp_ctx = self._build_comprehension_context(comprehension_data)
            context["assessments"]["comprehension"] = comp_ctx
            self._collect_tags(comp_ctx, context)

        return context

    def _build_logic_context(self, data: Dict[str, Any]) -> Dict[str, Any]:
        per_item = data.get("per_item_tags", [])
        unanswered = [p for p in per_item if not p.get("answered", False)]
        return {
            "test_type": "Logic Quest",
            "scores": {
                "percentage": data.get("percentage", 0),
                "correct_answers": data.get("correct_answers", 0),
                "total_items": data.get("total_items", 0),
                "level": data.get("level", ""),
            },
            "dear_parent_tags": data.get("dear_parent_tags", []),
            "per_item_tags": per_item,
            "unanswered_items": unanswered,
            "unanswered_count": len(unanswered),
            "signals": data.get("signals", {}),
            "scored_items": data.get("scored_items", []),
            "timestamp": data.get("timestamp", ""),
        }

    def _build_spelling_context(self, data: Dict[str, Any]) -> Dict[str, Any]:
        parent_summary = data.get("parent_summary", {})
        per_word = data.get("per_word_tags", [])
        unanswered = [p for p in per_word if not p.get("answered", False)]
        return {
            "test_type": "Spelling Assessment",
            "scores": {
                "overall_accuracy": parent_summary.get("overall_accuracy", 0),
                "phonics_score": parent_summary.get("phonics_score", 0),
                "sight_word_score": parent_summary.get("sight_word_score", 0),
                "confidence": parent_summary.get("confidence", "Medium"),
            },
            "dear_parent_tags": data.get("dear_parent_tags", []),
            "per_word_tags": per_word,
            "unanswered_items": unanswered,
            "unanswered_count": len(unanswered),
            "error_analysis": data.get("error_analysis", {}),
            "strengths": parent_summary.get("strengths", []),
            "focus_areas": parent_summary.get("focus_areas", []),
            "key_error_patterns": parent_summary.get("key_error_patterns", []),
            "timestamp": data.get("timestamp", ""),
        }

    def _build_speaking_context(self, data: Dict[str, Any]) -> Dict[str, Any]:
        per_sentence = data.get("per_sentence_tags", [])
        unanswered = [p for p in per_sentence if not p.get("answered", False)]
        return {
            "test_type": "Speaking Challenge",
            "scores": {
                "percentage": data.get("percentage", 0),
                "average_score": data.get("average_score", 0),
                "answered_count": data.get("answered_count", 0),
                "level": data.get("level", ""),
            },
            "dear_parent_tags": data.get("dear_parent_tags", []),
            "per_sentence_tags": per_sentence,
            "unanswered_items": unanswered,
            "unanswered_count": len(unanswered),
            "results": data.get("results", []),
            "timestamp": data.get("timestamp", ""),
        }

    def _build_comprehension_context(self, data: Dict[str, Any]) -> Dict[str, Any]:
        per_question = data.get("per_question_tags", [])
        unanswered = [p for p in per_question if not p.get("answered", False)]
        return {
            "test_type": "Comprehension Assessment",
            "scores": {
                "percentage": data.get("percentage", 0),
                "correct_answers": data.get("correct_answers", 0),
                "total_questions": data.get("total_questions", 0),
                "level": data.get("level", ""),
            },
            "dear_parent_tags": data.get("dear_parent_tags", []),
            "per_question_tags": per_question,
            "unanswered_items": unanswered,
            "unanswered_count": len(unanswered),
            "story_breakdown": data.get("results", []),
            "timestamp": data.get("timestamp", ""),
        }

    # ------------------------------------------------------------------
    # Tag collection
    # ------------------------------------------------------------------
    def _collect_tags(
        self,
        assessment_ctx: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        """Collect all tags from an assessment into the context's tag lists.

        Collects:
        - Test-level dear_parent_tags (strength / growth_edge)
        - Per-item tags from unanswered items (answered=False) as
          unanswered tags — these indicate items the child did not attempt.
        """
        # 1. Test-level tags
        tags = assessment_ctx.get("dear_parent_tags", [])
        for tag in tags:
            polarity = tag.get("polarity", "neutral")
            tag_info = {
                "tag": tag.get("tag", ""),
                "polarity": polarity,
                "confidence": tag.get("confidence", "medium"),
                "description": tag.get("description", ""),
                "evidence": tag.get("evidence", ""),
                "source_assessment": assessment_ctx.get("test_type", ""),
            }
            if polarity == "strength":
                context["all_strength_tags"].append(tag_info)
            elif polarity == "growth_edge":
                context["all_growth_edge_tags"].append(tag_info)

        # 2. Per-item tags from unanswered items
        for item_key in ("per_item_tags", "per_word_tags", "per_sentence_tags", "per_question_tags"):
            for item in assessment_ctx.get(item_key, []):
                if not item.get("answered", False):
                    for tag_id in item.get("tags", []):
                        tag_info = {
                            "tag": tag_id,
                            "polarity": "unanswered",
                            "confidence": "medium",
                            "description": f"Tag from unanswered item {item.get('item_id', 'unknown')}",
                            "evidence": "Child did not attempt this item.",
                            "source_assessment": assessment_ctx.get("test_type", ""),
                            "item_id": item.get("item_id", ""),
                        }
                        context["all_unanswered_tags"].append(tag_info)

    def _collect_all_tag_ids(self, context: Dict[str, Any]) -> Set[str]:
        """Collect all tag IDs that exist in the data for validation."""
        known: Set[str] = set()
        for tag in context.get("all_strength_tags", []):
            known.add(tag["tag"])
        for tag in context.get("all_growth_edge_tags", []):
            known.add(tag["tag"])
        for tag in context.get("all_unanswered_tags", []):
            known.add(tag["tag"])
        # Also collect per-item tags from all items (answered + unanswered)
        for assessment in context.get("assessments", {}).values():
            if not assessment:
                continue
            for key in ("per_item_tags", "per_word_tags", "per_sentence_tags", "per_question_tags"):
                for item in assessment.get(key, []):
                    for tag_id in item.get("tags", []):
                        known.add(tag_id)
        return known

    # ------------------------------------------------------------------
    # Domain summary (pure data, no AI)
    # ------------------------------------------------------------------
    def _build_domain_summary(
        self,
        logic_data: Optional[Dict[str, Any]],
        spelling_data: Optional[Dict[str, Any]],
        speaking_data: Optional[Dict[str, Any]],
        comprehension_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}

        if logic_data:
            summary["logic"] = {
                "percentage": logic_data.get("percentage", 0),
                "correct_answers": logic_data.get("correct_answers", 0),
                "total_items": logic_data.get("total_items", 0),
                "level": logic_data.get("level", ""),
                "tag_count": len(logic_data.get("dear_parent_tags", [])),
            }

        if spelling_data:
            ps = spelling_data.get("parent_summary", {})
            summary["spelling"] = {
                "overall_accuracy": ps.get("overall_accuracy", 0),
                "phonics_score": ps.get("phonics_score", 0),
                "sight_word_score": ps.get("sight_word_score", 0),
                "confidence": ps.get("confidence", "Medium"),
                "tag_count": len(spelling_data.get("dear_parent_tags", [])),
            }

        if speaking_data:
            summary["speaking"] = {
                "percentage": speaking_data.get("percentage", 0),
                "average_score": speaking_data.get("average_score", 0),
                "answered_count": speaking_data.get("answered_count", 0),
                "level": speaking_data.get("level", ""),
                "tag_count": len(speaking_data.get("dear_parent_tags", [])),
            }

        if comprehension_data:
            summary["comprehension"] = {
                "percentage": comprehension_data.get("percentage", 0),
                "correct_answers": comprehension_data.get("correct_answers", 0),
                "total_questions": comprehension_data.get("total_questions", 0),
                "level": comprehension_data.get("level", ""),
                "tag_count": len(comprehension_data.get("dear_parent_tags", [])),
            }

        return summary

    # ------------------------------------------------------------------
    # Top-5 tags — most important tags with one-sentence summaries
    # ------------------------------------------------------------------
    _CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
    _POLARITY_RANK = {"growth_edge": 3, "strength": 2, "neutral": 1, "unanswered": 0}

    _TAG_SENTENCE_MAP: Dict[str, str] = {
        # Logic
        "pattern_detection_strong": "Child recognises and extends patterns with confidence.",
        "pattern_detection_emerging": "Child is beginning to recognise patterns but needs more practice with complex ones.",
        "relational_reasoning_present": "Child connects ideas and sees relationships between concepts.",
        "systematic_problem_solving": "Child breaks down multi-step problems in a structured way.",
        "cognitive_flexibility_intact": "Child adapts their thinking when rules or strategies change.",
        "flexible_strategy_use": "Child switches strategies when the first approach doesn't work.",
        "strategy_shift_difficulty": "Child finds it hard to change approach when a strategy stops working.",
        "reasoning_under_load_emerging": "Child can handle simple logic but struggles with multi-step or high-load problems.",
        "trial_and_error_strategy": "Child tends to guess rather than plan, trying options until one fits.",
        "impulsive_response": "Child answers too quickly without thinking through the problem.",
        "self_correction_present": "Child notices and corrects their own mistakes during the test.",
        "rule_maintenance_difficulty": "Child loses track of the rule partway through a sequence.",
        # Spelling
        "confident_attempt": "Child attempts challenging words without hesitation.",
        "phonetic_strategy_strong": "Child uses solid phonetic knowledge to spell unfamiliar words.",
        "phonetic_strategy_developing": "Child is building phonetic awareness but makes feature errors.",
        "sight_word_recognition_strong": "Child reliably recognises high-frequency sight words.",
        "sight_word_recognition_developing": "Child is still memorising sight words and makes errors.",
        "vowel_accuracy_strong": "Child spells vowels correctly across word types.",
        "vowel_accuracy_developing": "Child struggles with vowel sounds and patterns in spelling.",
        "beginning_consonant_strong": "Child consistently gets the starting sound of words right.",
        "beginning_consonant_developing": "Child sometimes misses the initial consonant sound.",
        "ending_consonant_strong": "Child hears and spells the final sound of words.",
        "ending_consonant_developing": "Child drops or confuses ending consonants.",
        "rushed_spelling": "Child answers too quickly in spelling, leading to avoidable errors.",
        # Speaking
        "pronunciation_strong": "Child pronounces words clearly and accurately.",
        "pronunciation_needs_work": "Child mispronounces some words and would benefit from targeted practice.",
        "fluency_strong": "Child reads smoothly with natural pace and few pauses.",
        "fluency_developing": "Child reads with frequent pauses and hesitations.",
        "prosody_strong": "Child reads with expression and natural intonation.",
        "prosody_developing": "Child reads in a flat tone without much expression.",
        "grammar_strong": "Child uses correct grammar and sentence structure when speaking.",
        "grammar_developing": "Child makes grammatical errors that can affect clarity.",
        "flat_delivery": "Child's speech lacks intonation, which may affect engagement.",
        "insufficient_evidence_speaking": "Not enough speaking data to draw firm conclusions.",
        # Comprehension
        "literal_comprehension_strong": "Child accurately recalls facts and details from stories.",
        "literal_comprehension_developing": "Child misses key details from stories and needs support with recall.",
        "inferential_comprehension_strong": "Child draws insightful inferences beyond what is directly stated.",
        "inferential_comprehension_developing": "Child finds it hard to read between the lines.",
        "vocabulary_comprehension_strong": "Child understands word meanings in context well.",
        "vocabulary_comprehension_developing": "Child struggles with vocabulary and context-dependent word meanings.",
        "comprehension_gap_literal_vs_inferential": "Child recalls facts well but struggles to infer deeper meaning.",
        "strong_all_around_comprehension": "Child shows well-rounded comprehension across all question types.",
        "comprehension_support_needed": "Child needs guided support to understand stories at grade level.",
    }

    def _build_top_5_tags(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Select the 5 most important tags and add a one-sentence summary.

        Ranking priority:
          1. Growth-edge tags (most actionable for parents) — ranked by confidence
          2. Strength tags — ranked by confidence
          3. Neutral / unanswered — ranked by confidence
        """
        all_tags: List[Dict[str, Any]] = []
        for key in ("all_growth_edge_tags", "all_strength_tags", "all_unanswered_tags"):
            for tag in context.get(key, []):
                tag["_rank"] = (
                    self._POLARITY_RANK.get(tag.get("polarity", ""), 0)
                    * 10
                    + self._CONFIDENCE_RANK.get(tag.get("confidence", "medium"), 2)
                )
                all_tags.append(tag)

        all_tags.sort(key=lambda t: t.pop("_rank", 0), reverse=True)

        top_5 = []
        seen = set()
        for tag in all_tags:
            tag_id = tag.get("tag", "")
            if tag_id in seen:
                continue
            seen.add(tag_id)
            sentence = self._TAG_SENTENCE_MAP.get(
                tag_id,
                tag.get("description", "") or f"Tag: {tag_id}",
            )
            top_5.append({
                "tag": tag_id,
                "polarity": tag.get("polarity", ""),
                "confidence": tag.get("confidence", "medium"),
                "source_assessment": tag.get("source_assessment", ""),
                "one_sentence": sentence,
            })
            if len(top_5) >= 5:
                break

        return top_5

    # ------------------------------------------------------------------
    # Per-test importance — why each test matters for this child
    # ------------------------------------------------------------------
    _TEST_PURPOSE: Dict[str, str] = {
        "logic": "Logic Quest measures pattern recognition, relational reasoning, and systematic problem-solving — the foundations of mathematical and scientific thinking.",
        "spelling": "Word Wizard assesses phonetic awareness, sight-word memory, and encoding skills — critical building blocks for writing and reading fluency.",
        "speaking": "Voice Challenge evaluates pronunciation, fluency, prosody, and grammar in spoken language — essential for communication confidence and reading aloud.",
        "comprehension": "Story Explorer tests literal recall, inferential reasoning, and vocabulary in context — the core of reading comprehension and academic learning.",
    }

    _TEST_IMPORTANCE_LOW: Dict[str, str] = {
        "logic": "This is a HIGH PRIORITY area — the child's logical reasoning scores indicate they need structured support with patterns and multi-step thinking.",
        "spelling": "This is a HIGH PRIORITY area — spelling scores suggest the child needs daily phonics practice and targeted work on weak features.",
        "speaking": "This is a HIGH PRIORITY area — speaking scores indicate the child needs regular read-aloud practice with feedback on clarity and pace.",
        "comprehension": "This is a HIGH PRIORITY area — comprehension scores suggest the child needs guided reading with discussion to build understanding.",
    }

    _TEST_IMPORTANCE_MID: Dict[str, str] = {
        "logic": "This is a DEVELOPING area — the child shows some reasoning skills but will benefit from more complex puzzles and pattern games.",
        "spelling": "This is a DEVELOPING area — the child has basic phonics skills but needs practice with harder patterns and sight words.",
        "speaking": "This is a DEVELOPING area — the child can speak clearly but needs work on fluency, expression, or pronunciation consistency.",
        "comprehension": "This is a DEVELOPING area — the child understands basic story details but needs help with inference and vocabulary.",
    }

    _TEST_IMPORTANCE_HIGH: Dict[str, str] = {
        "logic": "This is a STRENGTH area — the child demonstrates strong logical reasoning and is ready for advanced challenges.",
        "spelling": "This is a STRENGTH area — the child spells accurately across features and is ready for more advanced vocabulary.",
        "speaking": "This is a STRENGTH area — the child speaks fluently and clearly, and is ready for longer or more complex passages.",
        "comprehension": "This is a STRENGTH area — the child comprehends well across question types and is ready for harder texts.",
    }

    def _build_test_importance(
        self,
        context: Dict[str, Any],
        domain_summary: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """For each test the child has taken, explain why it matters and what the results mean."""
        result = []
        for test_key, summary in domain_summary.items():
            purpose = self._TEST_PURPOSE.get(test_key, "")

            if test_key == "spelling":
                pct = summary.get("overall_accuracy", 0)
            else:
                pct = summary.get("percentage", 0)

            if pct < 60:
                importance = self._TEST_IMPORTANCE_LOW.get(test_key, "")
            elif pct < 80:
                importance = self._TEST_IMPORTANCE_MID.get(test_key, "")
            else:
                importance = self._TEST_IMPORTANCE_HIGH.get(test_key, "")

            tag_count = summary.get("tag_count", 0)

            assessment_ctx = context.get("assessments", {}).get(test_key, {})
            dear_parent_tags = assessment_ctx.get("dear_parent_tags", []) if assessment_ctx else []
            tag_summaries = [
                {
                    "tag": t.get("tag", ""),
                    "polarity": t.get("polarity", ""),
                    "description": t.get("description", ""),
                }
                for t in dear_parent_tags
            ]

            result.append({
                "test": test_key,
                "test_name": assessment_ctx.get("test_type", test_key.title()) if assessment_ctx else test_key.title(),
                "why_it_matters": purpose,
                "child_status": importance,
                "score_summary": summary,
                "tag_count": tag_count,
                "dear_parent_tags": tag_summaries,
            })

        return result

    # ------------------------------------------------------------------
    # Validation — ensure AI only references tags that exist
    # ------------------------------------------------------------------
    def _validate_report(
        self,
        report: Dict[str, Any],
        known_tags: Set[str],
    ) -> Dict[str, Any]:
        """Remove any evidence_tags from the AI report that don't exist in data."""
        for section in ("strengths", "growth_areas", "cross_domain_patterns", "recommendations"):
            for item in report.get(section, []):
                original = item.get("evidence_tags", [])
                filtered = [t for t in original if t in known_tags]
                if len(filtered) < len(original):
                    removed = set(original) - set(filtered)
                    logger.warning(
                        "AI cited non-existent tags %s in section '%s' — removed",
                        removed, section,
                    )
                item["evidence_tags"] = filtered

        return report
