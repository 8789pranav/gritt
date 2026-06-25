"""
Logic assessment service helpers for the main application.

This module contains the implementation of the logic assessment flows.
The API route definitions remain in main.py so auth and child validation live in the main app.
"""

from datetime import datetime
import uuid
from typing import List, Optional

from logic_assessment import (
    LogicItem,
    StudentResponse,
    GradeLevel,
    get_items_by_grade,
    aggregate_test_results,
    ALL_LOGIC_ITEMS,
    score_response,
)

GRADE_MAP = {
    "K-1": GradeLevel.KINDERGARTEN_1,
    "1-2": GradeLevel.GRADE_1_2,
    "2-3": GradeLevel.GRADE_2_3,
    "3-4": GradeLevel.GRADE_3_4,
    "Kindergarten": GradeLevel.KINDERGARTEN_1,
    "First": GradeLevel.GRADE_1_2,
    "Second": GradeLevel.GRADE_2_3,
    "Third": GradeLevel.GRADE_3_4,
}


def get_grade_level(grade: str) -> GradeLevel:
    grade_level = GRADE_MAP.get(grade)
    if not grade_level:
        raise ValueError(f"Invalid grade: {grade}")
    return grade_level


def format_logic_items(items: List[LogicItem]) -> List[dict]:
    return [
        {
            "item_id": item.item_id,
            "item_number": item.item_number,
            "item_type": item.item_type,
            "question_text": item.question_text,
            "difficulty": item.difficulty,
            "options": [
                {"index": opt.index, "text": opt.text, "image_url": opt.image_url}
                for opt in item.options
            ],
        }
        for item in items
    ]


def get_logic_test_payload(grade: str) -> dict:
    grade_level = get_grade_level(grade)
    items = get_items_by_grade(grade_level)

    return {
        "test_id": str(uuid.uuid4()),
        "grade": grade,
        "total_items": len(items),
        "instructions": (
            "Solve each logic puzzle carefully. Think about patterns, relationships, "
            "and rules. Take your time and do your best!"
        ),
        "items": format_logic_items(items),
    }


def score_logic_item_response(
    student_id: str,
    item_id: str,
    selected_answer_index: int,
    response_time_seconds: int,
    attempts: int = 1,
    self_corrected: bool = False,
    explanation_provided: Optional[str] = None,
) -> dict:
    item = next((item for item in ALL_LOGIC_ITEMS if item.item_id == item_id), None)
    if not item:
        raise ValueError(f"Item not found: {item_id}")

    response = StudentResponse(
        student_id=student_id,
        item_id=item_id,
        selected_answer_index=selected_answer_index,
        response_time_seconds=response_time_seconds,
        attempts=attempts,
        self_corrected=self_corrected,
        explanation_provided=explanation_provided,
    )
    scored_response = score_response(response, item)

    feedback = "Correct! You found the right answer."
    if not scored_response.is_correct:
        feedback = "Not quite right. Try again or review the pattern."
    elif scored_response.is_correct and response_time_seconds < item.expected_latency_seconds:
        feedback = "Correct! You found the right answer. And you were quick!"

    return {
        "item_id": item_id,
        "is_correct": scored_response.is_correct,
        "tags_earned": [str(tag.value) for tag in scored_response.tags_earned],
        "feedback": feedback,
        "correct_answer_index": item.correct_answer_index,
        "correct_answer": item.options[item.correct_answer_index].text,
    }


def aggregate_logic_test_results(student_id: str, grade: str, responses: List[dict]) -> dict:
    grade_level = get_grade_level(grade)
    response_objects = []
    for resp in responses:
        response_objects.append(
            StudentResponse(
                student_id=student_id,
                item_id=resp["item_id"],
                selected_answer_index=resp["selected_answer_index"],
                response_time_seconds=resp["response_time_seconds"],
                attempts=resp.get("attempts", 1),
                self_corrected=resp.get("self_corrected", False),
                explanation_provided=resp.get("explanation_provided"),
            )
        )

    result = aggregate_test_results(response_objects, grade_level)
    return {
        "test_id": result.test_id,
        "student_id": result.student_id,
        "grade": grade,
        "total_items": result.total_items,
        "correct_answers": result.total_correct,
        "score": result.total_correct,
        "percentage": result.score_percentage,
        "level": _get_performance_level(result.score_percentage),
        "cognitive_tags": [str(tag.value) for tag in result.final_tags],
        "tag_breakdown": result.tag_counts,
        "reasoning_under_load_detected": result.reasoning_under_load_detected,
        "trial_and_error_detected": result.trial_and_error_detected,
        "strategy_shift_difficulty_detected": result.strategy_shift_difficulty_detected,
        "message": f"Test completed: {result.total_correct}/{result.total_items} correct ({result.score_percentage:.1f}%)",
    }


def build_complete_logic_result(student_id: str, grade: str, score_data: dict) -> dict:
    """Build complete logic result from stored score data.
    
    Args:
        student_id: The child's ID
        grade: Grade level string
        score_data: The stored score data from Firebase (must not be None)
    """
    percentage = score_data.get("percentage", 0)
    level = _get_performance_level(percentage)
    cognitive_tags = score_data.get("cognitive_tags", [])
    tag_breakdown = score_data.get("tag_breakdown", {})

    # Build strengths from cognitive tags
    strength_map = {
        "pattern_detection_strong": "Strong pattern recognition and detection",
        "relational_reasoning_present": "Good relational reasoning abilities",
        "systematic_problem_solving": "Systematic and methodical problem-solving",
        "cognitive_flexibility_intact": "Flexible thinking and strategy adaptation",
        "flexible_strategy_use": "Creative and flexible approach to problems",
    }

    weakness_map = {
        "reasoning_under_load_emerging": "May struggle with reasoning under time pressure",
        "trial_and_error_strategy": "Tends to use trial-and-error rather than systematic approach",
        "strategy_shift_difficulty": "Difficulty shifting strategies when first approach fails",
        "pattern_detection_emerging": "Pattern recognition still developing",
    }

    strengths = [strength_map.get(tag, tag.replace("_", " ").title()) for tag in cognitive_tags if tag in strength_map]
    areas_to_develop = [weakness_map.get(tag, tag.replace("_", " ").title()) for tag in cognitive_tags if tag in weakness_map]

    if not strengths:
        strengths = ["Completed the logic assessment"]
    if not areas_to_develop:
        areas_to_develop = ["Continue practicing logic puzzles"]

    # Build recommendation based on level
    recommendation_map = {
        "Exceptional Logical Thinker": "Excellent logical reasoning! Challenge your child with advanced puzzles and abstract thinking exercises.",
        "Advanced Logical Thinker": "Strong logical skills! Introduce multi-step reasoning problems and competitive logic games.",
        "Good Logical Thinker": "Solid logical reasoning. Continue with puzzles and pattern activities to build on strengths.",
        "Developing Logical Thinker": "Building logical skills. Focus on pattern recognition exercises and guided problem-solving.",
        "Emerging Logical Thinker": "Starting the logical reasoning journey. Use hands-on manipulatives and visual pattern activities.",
    }

    total_items = score_data.get("total_items", 0)
    correct_answers = score_data.get("correct_answers", 0)

    return {
        "success": True,
        "student_id": student_id,
        "test_id": score_data.get("test_id", ""),
        "grade": grade,
        "test_timestamp": score_data.get("timestamp", datetime.utcnow().isoformat()),
        "summary": {
            "total_items": total_items,
            "correct_answers": correct_answers,
            "percentage": percentage,
            "level": level,
            "cognitive_tags": cognitive_tags,
            "tag_breakdown": tag_breakdown,
        },
        "parent_summary": {
            "overall_score": f"{correct_answers}/{total_items}",
            "percentage": percentage,
            "performance_level": level,
            "grade_placement": "Above Grade Level" if percentage >= 90 else ("At Grade Level" if percentage >= 70 else "Below Grade Level"),
            "next_step": "Practice multi-step logic puzzles and pattern recognition" if percentage >= 70 else "Focus on basic pattern recognition and logical reasoning exercises",
            "strengths": strengths,
            "areas_to_develop": areas_to_develop,
            "recommendation": recommendation_map.get(level, "Continue practicing logic puzzles."),
            "note": "This assessment is instructional and not a clinical diagnosis.",
        },
        "behavioral_signals": {
            "reasoning_under_load": score_data.get("reasoning_under_load_detected", False),
            "trial_and_error": score_data.get("trial_and_error_detected", False),
            "strategy_shift_difficulty": score_data.get("strategy_shift_difficulty_detected", False),
        },
        "actions": [
            {"label": "Retry Test", "type": "button", "action": "retry_test"},
            {"label": "View Items", "type": "button", "action": "view_items"},
            {"label": "Download Report", "type": "button", "action": "download_pdf"},
        ],
    }


def _get_performance_level(percentage: float) -> str:
    if percentage >= 90:
        return "Exceptional Logical Thinker"
    elif percentage >= 80:
        return "Advanced Logical Thinker"
    elif percentage >= 70:
        return "Good Logical Thinker"
    elif percentage >= 60:
        return "Developing Logical Thinker"
    return "Emerging Logical Thinker"
