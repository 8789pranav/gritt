"""
Cognitive Logic Assessment System (K-4)
Full Item Bank + Tag Mapping with Scoring & Aggregation
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
import uuid
import json


class CognitiveTag(str, Enum):
    """Core cognitive domain tags"""
    PATTERN_DETECTION_STRONG = "pattern_detection_strong"
    PATTERN_DETECTION_EMERGING = "pattern_detection_emerging"
    RELATIONAL_REASONING_PRESENT = "relational_reasoning_present"
    SYSTEMATIC_PROBLEM_SOLVING = "systematic_problem_solving"
    FLEXIBLE_STRATEGY_USE = "flexible_strategy_use"
    TRIAL_AND_ERROR_STRATEGY = "trial_and_error_strategy"
    COGNITIVE_FLEXIBILITY_INTACT = "cognitive_flexibility_intact"
    STRATEGY_SHIFT_DIFFICULTY = "strategy_shift_difficulty"
    REASONING_UNDER_LOAD_EMERGING = "reasoning_under_load_emerging"


class GradeLevel(str, Enum):
    """Grade levels"""
    KINDERGARTEN_1 = "K-1"
    GRADE_1_2 = "1-2"
    GRADE_2_3 = "2-3"
    GRADE_3_4 = "3-4"


class UniversalSignal(BaseModel):
    """Universal signals captured for each item"""
    accuracy: str  # "correct", "incorrect", "partial"
    latency: int  # seconds
    attempts: int
    self_correction: bool
    explanation_quality: str  # "none", "limited", "clear"


class LogicOption(BaseModel):
    """Option/answer choice for a logic item"""
    index: int
    text: str
    image_url: Optional[str] = None


class LogicItem(BaseModel):
    """Individual logic assessment item"""
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    grade_level: GradeLevel
    item_number: str  # e.g., "K1-1", "1-2-1"
    item_type: str  # "pattern", "analogy", "odd_one_out", etc.
    question_text: str
    options: List[LogicOption]
    correct_answer_index: int
    expected_latency_seconds: int = 30
    
    # Scoring tags
    primary_tag: CognitiveTag
    conditional_tags: Dict[str, CognitiveTag] = {}  # e.g., {"partial": "reasoning_under_load_emerging"}
    
    # Metadata
    difficulty: str = "medium"  # "easy", "medium", "hard"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StudentResponse(BaseModel):
    """Student's response to a logic item"""
    student_id: str
    item_id: str
    selected_answer_index: int
    response_time_seconds: int
    attempts: int = 1
    self_corrected: bool = False
    explanation_provided: Optional[str] = None
    
    # Computed during scoring
    is_correct: Optional[bool] = None
    tags_earned: List[CognitiveTag] = []


class LogicTestResult(BaseModel):
    """Complete logic assessment results"""
    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    test_id: str
    student_id: str
    grade_level: GradeLevel
    
    # Responses
    responses: List[StudentResponse]
    
    # Scoring
    total_correct: int = 0
    total_items: int = 0
    score_percentage: float = 0.0
    
    # Tag aggregation
    tag_counts: Dict[str, int] = {}
    final_tags: List[CognitiveTag] = []
    
    # Analysis
    reasoning_under_load_detected: bool = False
    trial_and_error_detected: bool = False
    strategy_shift_difficulty_detected: bool = False
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# LOGIC ITEM BANK - K-1 GRADE (10 Items)
# ============================================================================

LOGIC_ITEMS_K1 = [
    LogicItem(
        item_id="k1_1",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-1",
        item_type="pattern",
        question_text="Red, blue, red, blue, ___",
        options=[
            LogicOption(index=0, text="Red"),
            LogicOption(index=1, text="Blue"),
            LogicOption(index=2, text="Green"),
            LogicOption(index=3, text="Yellow"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=20,
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        conditional_tags={
            "partial": CognitiveTag.TRIAL_AND_ERROR_STRATEGY,
            "multiple_attempts": CognitiveTag.TRIAL_AND_ERROR_STRATEGY,
        },
        difficulty="easy",
    ),
    LogicItem(
        item_id="k1_2",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-2",
        item_type="pattern",
        question_text="Circle, circle, square, circle, circle, ___",
        options=[
            LogicOption(index=0, text="Circle"),
            LogicOption(index=1, text="Square"),
            LogicOption(index=2, text="Triangle"),
            LogicOption(index=3, text="Rectangle"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=25,
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        difficulty="easy",
    ),
    LogicItem(
        item_id="k1_3",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-3",
        item_type="odd_one_out",
        question_text="Which one doesn't belong? Apple, banana, car",
        options=[
            LogicOption(index=0, text="Apple"),
            LogicOption(index=1, text="Banana"),
            LogicOption(index=2, text="Car"),
            LogicOption(index=3, text="None"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=20,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="easy",
    ),
    LogicItem(
        item_id="k1_4",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-4",
        item_type="matching",
        question_text="Find the matching shape (star shape shown)",
        options=[
            LogicOption(index=0, text="Circle"),
            LogicOption(index=1, text="Star"),
            LogicOption(index=2, text="Square"),
            LogicOption(index=3, text="Triangle"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=15,
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        difficulty="easy",
    ),
    LogicItem(
        item_id="k1_5",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-5",
        item_type="comparison",
        question_text="Which is bigger? Elephant or cat?",
        options=[
            LogicOption(index=0, text="Elephant"),
            LogicOption(index=1, text="Cat"),
            LogicOption(index=2, text="Same size"),
            LogicOption(index=3, text="Can't tell"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=20,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="easy",
    ),
    LogicItem(
        item_id="k1_6",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-6",
        item_type="analogy",
        question_text="Bird is to sky as fish is to ___",
        options=[
            LogicOption(index=0, text="Air"),
            LogicOption(index=1, text="Water"),
            LogicOption(index=2, text="Land"),
            LogicOption(index=3, text="Clouds"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=25,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="easy",
    ),
    LogicItem(
        item_id="k1_7",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-7",
        item_type="sequence",
        question_text="What comes next? 1, 2, 3, ___",
        options=[
            LogicOption(index=0, text="1"),
            LogicOption(index=1, text="4"),
            LogicOption(index=2, text="5"),
            LogicOption(index=3, text="2"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=20,
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        difficulty="easy",
    ),
    LogicItem(
        item_id="k1_8",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-8",
        item_type="rule_application",
        question_text="All glims are red. This is a glim. So this is ___",
        options=[
            LogicOption(index=0, text="Red"),
            LogicOption(index=1, text="Blue"),
            LogicOption(index=2, text="Green"),
            LogicOption(index=3, text="Yellow"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="k1_9",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-9",
        item_type="categorization",
        question_text="How many are animals? Dog, cat, apple, bird",
        options=[
            LogicOption(index=0, text="1"),
            LogicOption(index=1, text="2"),
            LogicOption(index=2, text="3"),
            LogicOption(index=3, text="4"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=25,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="easy",
    ),
    LogicItem(
        item_id="k1_10",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-10",
        item_type="pattern",
        question_text="Clap, tap, clap, tap, ___",
        options=[
            LogicOption(index=0, text="Clap"),
            LogicOption(index=1, text="Tap"),
            LogicOption(index=2, text="Snap"),
            LogicOption(index=3, text="Stomp"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=20,
        primary_tag=CognitiveTag.PATTERN_DETECTION_STRONG,
        difficulty="easy",
    ),
]

# ============================================================================
# LOGIC ITEM BANK - Grade 1-2 (10 Items)
# ============================================================================

LOGIC_ITEMS_1_2 = [
    LogicItem(
        item_id="1_2_1",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-1",
        item_type="pattern",
        question_text="Triangle, square, triangle, square, ___",
        options=[
            LogicOption(index=0, text="Circle"),
            LogicOption(index=1, text="Triangle"),
            LogicOption(index=2, text="Square"),
            LogicOption(index=3, text="Diamond"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=25,
        primary_tag=CognitiveTag.PATTERN_DETECTION_STRONG,
        difficulty="easy",
    ),
    LogicItem(
        item_id="1_2_2",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-2",
        item_type="sequence",
        question_text="What comes next? 5, 10, 15, ___",
        options=[
            LogicOption(index=0, text="10"),
            LogicOption(index=1, text="20"),
            LogicOption(index=2, text="25"),
            LogicOption(index=3, text="30"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.PATTERN_DETECTION_STRONG,
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_3",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-3",
        item_type="odd_one_out",
        question_text="Which doesn't belong? Dog, cat, table, bird. Why?",
        options=[
            LogicOption(index=0, text="Table (it's furniture)"),
            LogicOption(index=1, text="Bird (it flies)"),
            LogicOption(index=2, text="Dog (it barks)"),
            LogicOption(index=3, text="All belong"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        conditional_tags={"no_explanation": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_4",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-4",
        item_type="matrix",
        question_text="2x2 matrix: what goes in the empty square?",
        options=[
            LogicOption(index=0, text="A"),
            LogicOption(index=1, text="B"),
            LogicOption(index=2, text="C"),
            LogicOption(index=3, text="D"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.PATTERN_DETECTION_STRONG,
        conditional_tags={"partial": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_5",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-5",
        item_type="analogy",
        question_text="Hand is to finger as foot is to ___",
        options=[
            LogicOption(index=0, text="Toe"),
            LogicOption(index=1, text="Shoe"),
            LogicOption(index=2, text="Ankle"),
            LogicOption(index=3, text="Step"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_6",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-6",
        item_type="rule_application",
        question_text="All squares have 4 sides. This shape has 4 sides. Is it a square?",
        options=[
            LogicOption(index=0, text="Yes"),
            LogicOption(index=1, text="No"),
            LogicOption(index=2, text="Maybe"),
            LogicOption(index=3, text="Can't tell"),
        ],
        correct_answer_index=3,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_7",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-7",
        item_type="quantity",
        question_text="If 2 apples + 3 apples, how many apples?",
        options=[
            LogicOption(index=0, text="2"),
            LogicOption(index=1, text="3"),
            LogicOption(index=2, text="5"),
            LogicOption(index=3, text="6"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=25,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={"incorrect": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="easy",
    ),
    LogicItem(
        item_id="1_2_8",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-8",
        item_type="category_shift",
        question_text="Sort by: First by color, then by size. Are you successful?",
        options=[
            LogicOption(index=0, text="Yes, easily"),
            LogicOption(index=1, text="Yes, but difficult"),
            LogicOption(index=2, text="No, got confused"),
            LogicOption(index=3, text="Partially"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=45,
        primary_tag=CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT,
        conditional_tags={
            "index_2": CognitiveTag.STRATEGY_SHIFT_DIFFICULTY,
        },
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_9",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-9",
        item_type="two_step",
        question_text="First: pick the big one. Then: pick the red one from those. Can you do it?",
        options=[
            LogicOption(index=0, text="Yes, easily"),
            LogicOption(index=1, text="Yes, with help"),
            LogicOption(index=2, text="No, I got lost"),
            LogicOption(index=3, text="Yes, but slowly"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=50,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={"index_2": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_10",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-10",
        item_type="pattern_creation",
        question_text="Create your own pattern with these shapes. Can you explain it?",
        options=[
            LogicOption(index=0, text="Yes, clear pattern"),
            LogicOption(index=1, text="Yes, but vague"),
            LogicOption(index=2, text="Pattern unclear"),
            LogicOption(index=3, text="No pattern"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=60,
        primary_tag=CognitiveTag.FLEXIBLE_STRATEGY_USE,
        difficulty="hard",
    ),
]

# ============================================================================
# LOGIC ITEM BANK - Grade 2-3 (10 Items - CORE BAND)
# ============================================================================

LOGIC_ITEMS_2_3 = [
    LogicItem(
        item_id="2_3_1",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-1",
        item_type="skip_pattern",
        question_text="What comes next? 3, 6, 9, 12, ___",
        options=[
            LogicOption(index=0, text="13"),
            LogicOption(index=1, text="14"),
            LogicOption(index=2, text="15"),
            LogicOption(index=3, text="16"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.PATTERN_DETECTION_STRONG,
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_2",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-2",
        item_type="alternating_pattern",
        question_text="Pattern: 2, 5, 2, 5, 2, 5, ___",
        options=[
            LogicOption(index=0, text="2"),
            LogicOption(index=1, text="5"),
            LogicOption(index=2, text="7"),
            LogicOption(index=3, text="10"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=25,
        primary_tag=CognitiveTag.PATTERN_DETECTION_STRONG,
        conditional_tags={"repeated_error": CognitiveTag.TRIAL_AND_ERROR_STRATEGY},
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_3",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-3",
        item_type="odd_one_out_explain",
        question_text="Odd one out: Lion, tiger, giraffe, car. Explain why.",
        options=[
            LogicOption(index=0, text="Car (not an animal)"),
            LogicOption(index=1, text="Giraffe (different color)"),
            LogicOption(index=2, text="Lion (smaller)"),
            LogicOption(index=3, text="Tiger (eats meat)"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_4",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-4",
        item_type="matrix_2rule",
        question_text="3x3 matrix with 2 rules - what's missing?",
        options=[
            LogicOption(index=0, text="A"),
            LogicOption(index=1, text="B"),
            LogicOption(index=2, text="C"),
            LogicOption(index=3, text="D"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=50,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={"partial": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="hard",
    ),
    LogicItem(
        item_id="2_3_5",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-5",
        item_type="analogy_complex",
        question_text="Bat is to baseball as club is to ___",
        options=[
            LogicOption(index=0, text="Golf"),
            LogicOption(index=1, text="Party"),
            LogicOption(index=2, text="Card"),
            LogicOption(index=3, text="Group"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_6",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-6",
        item_type="rule_logic",
        question_text="If A = B and B = C, then A = C. True or false?",
        options=[
            LogicOption(index=0, text="True"),
            LogicOption(index=1, text="False"),
            LogicOption(index=2, text="Maybe"),
            LogicOption(index=3, text="Need more info"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="hard",
    ),
    LogicItem(
        item_id="2_3_7",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-7",
        item_type="multi_step_quantity",
        question_text="5 apples + 3 oranges - 2 apples. How many apples left?",
        options=[
            LogicOption(index=0, text="3"),
            LogicOption(index=1, text="4"),
            LogicOption(index=2, text="5"),
            LogicOption(index=3, text="6"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={"breakdown": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="hard",
    ),
    LogicItem(
        item_id="2_3_8",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-8",
        item_type="category_shift_complex",
        question_text="Sort by color, then size, then shape. Success?",
        options=[
            LogicOption(index=0, text="Yes, all correct"),
            LogicOption(index=1, text="Yes, minor errors"),
            LogicOption(index=2, text="Partially, confused at step 2"),
            LogicOption(index=3, text="No, gave up"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=60,
        primary_tag=CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT,
        conditional_tags={"index_2_3": CognitiveTag.STRATEGY_SHIFT_DIFFICULTY},
        difficulty="hard",
    ),
    LogicItem(
        item_id="2_3_9",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-9",
        item_type="two_step_rule",
        question_text="All cats are mammals. Fluffy is a cat. Is Fluffy a mammal?",
        options=[
            LogicOption(index=0, text="Yes"),
            LogicOption(index=1, text="No"),
            LogicOption(index=2, text="Not sure"),
            LogicOption(index=3, text="Need more info"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_10",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-10",
        item_type="pattern_generation",
        question_text="Generate pattern with numbers: Start 2, rule +3. Sequence?",
        options=[
            LogicOption(index=0, text="2, 5, 8, 11"),
            LogicOption(index=1, text="2, 4, 6, 8"),
            LogicOption(index=2, text="2, 3, 4, 5"),
            LogicOption(index=3, text="2, 6, 10, 14"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=45,
        primary_tag=CognitiveTag.FLEXIBLE_STRATEGY_USE,
        difficulty="hard",
    ),
]

# ============================================================================
# LOGIC ITEM BANK - Grade 3-4 (10 Items)
# ============================================================================

LOGIC_ITEMS_3_4 = [
    LogicItem(
        item_id="3_4_1",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-1",
        item_type="exponential_pattern",
        question_text="What comes next? 2, 4, 8, 16, ___",
        options=[
            LogicOption(index=0, text="24"),
            LogicOption(index=1, text="32"),
            LogicOption(index=2, text="20"),
            LogicOption(index=3, text="18"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.PATTERN_DETECTION_STRONG,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_2",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-2",
        item_type="linear_shift_pattern",
        question_text="Pattern: 2, 5, 8, 11, ___. What's the rule and next number?",
        options=[
            LogicOption(index=0, text="Add 2; next is 13"),
            LogicOption(index=1, text="Add 3; next is 14"),
            LogicOption(index=2, text="Add 4; next is 15"),
            LogicOption(index=3, text="Multiply by 2; next is 22"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_3",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-3",
        item_type="abstract_odd_one_out",
        question_text="Odd one: Optimistic, pessimistic, realistic, happiness",
        options=[
            LogicOption(index=0, text="Optimistic"),
            LogicOption(index=1, text="Pessimistic"),
            LogicOption(index=2, text="Realistic"),
            LogicOption(index=3, text="Happiness"),
        ],
        correct_answer_index=3,
        expected_latency_seconds=45,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_4",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-4",
        item_type="matrix_multiattribute",
        question_text="4x4 matrix with multiple attributes. What's missing?",
        options=[
            LogicOption(index=0, text="A"),
            LogicOption(index=1, text="B"),
            LogicOption(index=2, text="C"),
            LogicOption(index=3, text="D"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=60,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={"partial": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_5",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-5",
        item_type="abstract_analogy",
        question_text="Justice is to law as ??? is to science",
        options=[
            LogicOption(index=0, text="Proof"),
            LogicOption(index=1, text="Truth"),
            LogicOption(index=2, text="Method"),
            LogicOption(index=3, text="Laboratory"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=50,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_6",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-6",
        item_type="conditional_logic",
        question_text="If it rains, the game is canceled. It rained. The game was ___?",
        options=[
            LogicOption(index=0, text="Definitely canceled"),
            LogicOption(index=1, text="Probably canceled"),
            LogicOption(index=2, text="Might happen"),
            LogicOption(index=3, text="Always happens"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        conditional_tags={"incorrect": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_7",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-7",
        item_type="multi_step_complex",
        question_text="10 - (3 + 2) × 2 = ?",
        options=[
            LogicOption(index=0, text="4"),
            LogicOption(index=1, text="14"),
            LogicOption(index=2, text="0"),
            LogicOption(index=3, text="6"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=45,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_8",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-8",
        item_type="strategy_shift",
        question_text="When first method fails, do you try another approach?",
        options=[
            LogicOption(index=0, text="Yes, immediately"),
            LogicOption(index=1, text="Yes, after thinking"),
            LogicOption(index=2, text="Sometimes"),
            LogicOption(index=3, text="No, I give up"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT,
        conditional_tags={"index_3": CognitiveTag.STRATEGY_SHIFT_DIFFICULTY},
        difficulty="medium",
    ),
    LogicItem(
        item_id="3_4_9",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-9",
        item_type="dual_classification",
        question_text="Rectangle: quadrilateral? Right angles?",
        options=[
            LogicOption(index=0, text="Both yes"),
            LogicOption(index=1, text="First yes, second no"),
            LogicOption(index=2, text="First no, second yes"),
            LogicOption(index=3, text="Both no"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_10",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-10",
        item_type="pattern_generation_complex",
        question_text="Create a 3-number pattern that doubles each time",
        options=[
            LogicOption(index=0, text="1, 2, 4 (doubles each)"),
            LogicOption(index=1, text="1, 3, 5 (adds 2)"),
            LogicOption(index=2, text="2, 4, 6 (adds 2)"),
            LogicOption(index=3, text="1, 1, 1 (same)"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=50,
        primary_tag=CognitiveTag.FLEXIBLE_STRATEGY_USE,
        difficulty="hard",
    ),
]


# ============================================================================
# All Items Combined
# ============================================================================

ALL_LOGIC_ITEMS = LOGIC_ITEMS_K1 + LOGIC_ITEMS_1_2 + LOGIC_ITEMS_2_3 + LOGIC_ITEMS_3_4


def get_items_by_grade(grade_level: GradeLevel) -> List[LogicItem]:
    """Get all logic items for a specific grade level"""
    return [item for item in ALL_LOGIC_ITEMS if item.grade_level == grade_level]


# ============================================================================
# SCORING & AGGREGATION LOGIC
# ============================================================================

def score_response(response: StudentResponse, item: LogicItem) -> StudentResponse:
    """Score a single response and assign cognitive tags"""
    response.is_correct = response.selected_answer_index == item.correct_answer_index
    response.tags_earned = []
    
    if response.is_correct:
        # Award primary tag
        response.tags_earned.append(item.primary_tag)
    else:
        # Check for conditional tags for incorrect responses
        if "incorrect" in item.conditional_tags:
            response.tags_earned.append(item.conditional_tags["incorrect"])
    
    # Award conditional tags based on attempts
    if response.attempts > 1 and "multiple_attempts" in item.conditional_tags:
        response.tags_earned.append(item.conditional_tags["multiple_attempts"])
    
    # Award tags for self-correction
    if response.self_corrected and "self_correction" in item.conditional_tags:
        response.tags_earned.append(item.conditional_tags["self_correction"])
    
    return response


def aggregate_test_results(
    responses: List[StudentResponse], 
    grade_level: GradeLevel
) -> LogicTestResult:
    """Aggregate responses into final test result with cognitive profile"""
    
    test_id = str(uuid.uuid4())
    student_id = responses[0].student_id if responses else "unknown"
    
    # Score responses
    items_dict = {item.item_id: item for item in ALL_LOGIC_ITEMS}
    for response in responses:
        if response.item_id in items_dict:
            score_response(response, items_dict[response.item_id])
    
    # Calculate basic scores
    total_correct = sum(1 for r in responses if r.is_correct)
    total_items = len(responses)
    score_percentage = (total_correct / total_items * 100) if total_items > 0 else 0
    
    # Aggregate tags (Step 1: Count signals)
    tag_counts = {}
    for response in responses:
        for tag in response.tags_earned:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    # Step 2: Apply thresholds
    final_tags = []
    
    # Pattern detection threshold
    pattern_count = (
        tag_counts.get(CognitiveTag.PATTERN_DETECTION_STRONG, 0) +
        tag_counts.get(CognitiveTag.PATTERN_DETECTION_EMERGING, 0)
    )
    if pattern_count >= 3:
        final_tags.append(CognitiveTag.PATTERN_DETECTION_STRONG)
    
    # Reasoning threshold
    reasoning_count = (
        tag_counts.get(CognitiveTag.RELATIONAL_REASONING_PRESENT, 0) +
        tag_counts.get(CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING, 0)
    )
    if reasoning_count >= 3:
        final_tags.append(CognitiveTag.RELATIONAL_REASONING_PRESENT)
    
    # Flexibility threshold
    flexibility_count = tag_counts.get(CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT, 0)
    if flexibility_count >= 2:
        final_tags.append(CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT)
    
    # Step 3: Detect weakness patterns
    reasoning_under_load = tag_counts.get(CognitiveTag.REASONING_UNDER_LOAD_EMERGING, 0) >= 2
    trial_and_error = tag_counts.get(CognitiveTag.TRIAL_AND_ERROR_STRATEGY, 0) >= 2
    strategy_shift_difficulty = tag_counts.get(CognitiveTag.STRATEGY_SHIFT_DIFFICULTY, 0) >= 1
    
    if reasoning_under_load:
        if CognitiveTag.REASONING_UNDER_LOAD_EMERGING not in final_tags:
            final_tags.append(CognitiveTag.REASONING_UNDER_LOAD_EMERGING)
    
    if trial_and_error:
        if CognitiveTag.TRIAL_AND_ERROR_STRATEGY not in final_tags:
            final_tags.append(CognitiveTag.TRIAL_AND_ERROR_STRATEGY)
    
    if strategy_shift_difficulty:
        if CognitiveTag.STRATEGY_SHIFT_DIFFICULTY not in final_tags:
            final_tags.append(CognitiveTag.STRATEGY_SHIFT_DIFFICULTY)
    
    # Create result
    result = LogicTestResult(
        test_id=test_id,
        student_id=student_id,
        grade_level=grade_level,
        responses=responses,
        total_correct=total_correct,
        total_items=total_items,
        score_percentage=score_percentage,
        tag_counts={str(k): v for k, v in tag_counts.items()},
        final_tags=final_tags,
        reasoning_under_load_detected=reasoning_under_load,
        trial_and_error_detected=trial_and_error,
        strategy_shift_difficulty_detected=strategy_shift_difficulty,
    )
    
    return result
