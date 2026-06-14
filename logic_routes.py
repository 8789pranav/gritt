"""
FastAPI endpoints for Cognitive Logic Assessment (K-4)
Integrates with existing comprehension and speaking APIs
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid

from logic_assessment import (
    LogicItem,
    StudentResponse,
    LogicTestResult,
    GradeLevel,
    CognitiveTag,
    get_items_by_grade,
    aggregate_test_results,
    ALL_LOGIC_ITEMS,
)

# Create router
router = APIRouter(prefix="/logic", tags=["logic_assessment"])


# ============================================================================
# MODELS FOR API REQUESTS/RESPONSES
# ============================================================================

class GetLogicTestRequest(BaseModel):
    """Request to get logic assessment test items"""
    idToken: str
    child_id: str
    grade: str


class LogicTestResponse(BaseModel):
    """Response with logic test items"""
    test_id: str
    grade: str
    total_items: int
    instructions: str
    items: List[dict]


class SubmitLogicResponseRequest(BaseModel):
    """Submit a response to a logic item"""
    idToken: str
    child_id: str
    item_id: str
    selected_answer_index: int
    response_time_seconds: int
    attempts: int = 1
    self_corrected: bool = False
    explanation_provided: Optional[str] = None


class SubmitLogicTestRequest(BaseModel):
    """Submit all responses for a logic test"""
    idToken: str
    child_id: str
    grade: str
    responses: List[dict]  # List of {item_id, selected_answer_index, response_time_seconds, ...}


class CompleteLogicResultRequest(BaseModel):
    """Request complete logic test results"""
    idToken: str
    child_id: str
    grade: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/get_test/")
async def get_logic_test(request: GetLogicTestRequest):
    """
    Get a logic assessment test with all items for a specific grade level
    
    **Endpoint:** `POST /logic/get_test/`
    
    **Parameters:**
    - `idToken`: Firebase ID token
    - `child_id`: UUID of the child
    - `grade`: Grade level (K-1, 1-2, 2-3, 3-4)
    
    **Returns:**
    - `test_id`: Unique test identifier
    - `grade`: Grade level
    - `total_items`: Number of items (10 per grade)
    - `instructions`: Test instructions
    - `items`: Array of logic items with options
    """
    try:
        # Map grade string to enum
        grade_map = {
            "K-1": GradeLevel.KINDERGARTEN_1,
            "1-2": GradeLevel.GRADE_1_2,
            "2-3": GradeLevel.GRADE_2_3,
            "3-4": GradeLevel.GRADE_3_4,
            "Kindergarten": GradeLevel.KINDERGARTEN_1,
            "First": GradeLevel.GRADE_1_2,
            "Second": GradeLevel.GRADE_2_3,
            "Third": GradeLevel.GRADE_3_4,
        }
        
        grade_level = grade_map.get(request.grade)
        if not grade_level:
            raise ValueError(f"Invalid grade: {request.grade}")
        
        # Get items for grade
        items = get_items_by_grade(grade_level)
        
        # Format response
        formatted_items = []
        for item in items:
            formatted_items.append({
                "item_id": item.item_id,
                "item_number": item.item_number,
                "item_type": item.item_type,
                "question_text": item.question_text,
                "difficulty": item.difficulty,
                "options": [
                    {"index": opt.index, "text": opt.text, "image_url": opt.image_url}
                    for opt in item.options
                ],
            })
        
        test_id = str(uuid.uuid4())
        
        return {
            "success": True,
            "test_id": test_id,
            "grade": request.grade,
            "total_items": len(items),
            "instructions": (
                "Solve each logic puzzle carefully. Think about patterns, relationships, "
                "and rules. Take your time and do your best!"
            ),
            "items": formatted_items,
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit_response/")
async def submit_single_response(request: SubmitLogicResponseRequest):
    """
    Submit a single response to a logic item (incremental scoring)
    
    **Endpoint:** `POST /logic/submit_response/`
    
    **Parameters:**
    - `idToken`: Firebase ID token
    - `child_id`: UUID of the child
    - `item_id`: ID of the logic item
    - `selected_answer_index`: Selected option index (0-3)
    - `response_time_seconds`: Time taken to respond
    - `attempts`: Number of attempts
    - `self_corrected`: Whether student self-corrected
    - `explanation_provided`: Optional explanation text
    
    **Returns:**
    - `success`: Whether submission succeeded
    - `is_correct`: Whether answer is correct
    - `item_id`: The item ID
    - `tags_earned`: Cognitive tags earned
    - `feedback`: Encouraging feedback
    """
    try:
        # Find the item
        item = None
        for i in ALL_LOGIC_ITEMS:
            if i.item_id == request.item_id:
                item = i
                break
        
        if not item:
            raise ValueError(f"Item not found: {request.item_id}")
        
        # Create response object
        response = StudentResponse(
            student_id=request.child_id,
            item_id=request.item_id,
            selected_answer_index=request.selected_answer_index,
            response_time_seconds=request.response_time_seconds,
            attempts=request.attempts,
            self_corrected=request.self_corrected,
            explanation_provided=request.explanation_provided,
        )
        
        # Score the response
        from logic_assessment import score_response
        response = score_response(response, item)
        
        # Generate feedback
        feedback = ""
        if response.is_correct:
            feedback = "Correct! You found the right answer."
            if response.response_time_seconds < item.expected_latency_seconds:
                feedback += " And you were quick!"
        else:
            feedback = "Not quite right. Try again or review the pattern."
        
        return {
            "success": True,
            "is_correct": response.is_correct,
            "item_id": request.item_id,
            "tags_earned": [str(tag.value) for tag in response.tags_earned],
            "feedback": feedback,
            "correct_answer_index": item.correct_answer_index,
            "correct_answer": item.options[item.correct_answer_index].text,
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit_test/")
async def submit_logic_test(request: SubmitLogicTestRequest):
    """
    Submit all responses for a complete logic test
    
    **Endpoint:** `POST /logic/submit_test/`
    
    **Parameters:**
    - `idToken`: Firebase ID token
    - `child_id`: UUID of the child
    - `grade`: Grade level
    - `test_id`: Test ID from get_test
    - `responses`: Array of responses with {item_id, selected_answer_index, response_time_seconds}
    
    **Returns:**
    - `success`: True if submitted
    - `test_id`: Test identifier
    - `total_items`: Total items in test
    - `correct_answers`: Number of correct answers
    - `score`: Score count
    - `percentage`: Score percentage
    - `tags`: Cognitive tags earned
    """
    try:
        # Map grade
        grade_map = {
            "K-1": GradeLevel.KINDERGARTEN_1,
            "1-2": GradeLevel.GRADE_1_2,
            "2-3": GradeLevel.GRADE_2_3,
            "3-4": GradeLevel.GRADE_3_4,
            "Kindergarten": GradeLevel.KINDERGARTEN_1,
            "First": GradeLevel.GRADE_1_2,
            "Second": GradeLevel.GRADE_2_3,
            "Third": GradeLevel.GRADE_3_4,
        }
        grade_level = grade_map.get(request.grade)
        
        # Convert response dicts to StudentResponse objects
        responses = []
        for resp in request.responses:
            responses.append(
                StudentResponse(
                    student_id=request.child_id,
                    item_id=resp["item_id"],
                    selected_answer_index=resp["selected_answer_index"],
                    response_time_seconds=resp["response_time_seconds"],
                    attempts=resp.get("attempts", 1),
                    self_corrected=resp.get("self_corrected", False),
                    explanation_provided=resp.get("explanation_provided"),
                )
            )
        
        # Aggregate results
        result = aggregate_test_results(responses, grade_level)
        
        return {
            "success": True,
            "test_id": result.test_id,
            "student_id": result.student_id,
            "grade": request.grade,
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
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/complete_result/")
async def get_complete_logic_result(request: CompleteLogicResultRequest):
    """
    Get complete detailed results for a logic test
    
    **Endpoint:** `POST /logic/complete_result/`
    
    **Parameters:**
    - `idToken`: Firebase ID token
    - `child_id`: UUID of the child
    - `test_id`: Test ID
    - `grade`: Grade level
    
    **Returns:**
    - Comprehensive results with cognitive profile
    - Item-by-item breakdown
    - Parent-friendly summary
    - Recommendations
    """
    try:
        # For now, return template result
        # In production, fetch from database
        
        return {
            "success": True,
            "student_id": request.child_id,
            "test_id": request.test_id,
            "grade": request.grade,
            "test_timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_items": 10,
                "correct_answers": 7,
                "percentage": 70.0,
                "cognitive_tags": [
                    "pattern_detection_strong",
                    "systematic_problem_solving",
                ],
            },
            "parent_summary": {
                "overall_score": "7/10",
                "percentage": 70.0,
                "performance_level": "Good Logical Thinker",
                "grade_placement": "At Grade Level",
                "next_step": "Practice multi-step logic puzzles and pattern recognition",
                "strengths": [
                    "Strong pattern detection abilities",
                    "Good systematic problem-solving",
                ],
                "areas_to_develop": [
                    "Cognitive flexibility under time pressure",
                    "Strategy shifting when first approach fails",
                ],
                "recommendation": "Your child shows solid logical reasoning skills. Continue with puzzles and pattern activities.",
                "note": "This assessment is instructional and not a clinical diagnosis.",
            },
            "actions": [
                {"label": "Retry Test", "type": "button", "action": "retry_test"},
                {"label": "View Items", "type": "button", "action": "view_items"},
                {"label": "Download Report", "type": "button", "action": "download_pdf"},
            ],
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_performance_level(percentage: float) -> str:
    """Determine performance level from percentage"""
    if percentage >= 90:
        return "Exceptional Logical Thinker"
    elif percentage >= 80:
        return "Advanced Logical Thinker"
    elif percentage >= 70:
        return "Good Logical Thinker"
    elif percentage >= 60:
        return "Developing Logical Thinker"
    else:
        return "Emerging Logical Thinker"


# Export router for use in main.py
def setup_logic_routes(app):
    """Add logic assessment routes to FastAPI app"""
    app.include_router(router)
