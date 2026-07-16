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
    """Core cognitive domain tags — matches spec §2"""
    PATTERN_DETECTION_STRONG = "pattern_detection_strong"
    PATTERN_DETECTION_EMERGING = "pattern_detection_emerging"
    RELATIONAL_REASONING_PRESENT = "relational_reasoning_present"
    SYSTEMATIC_PROBLEM_SOLVING = "systematic_problem_solving"
    COGNITIVE_FLEXIBILITY_INTACT = "cognitive_flexibility_intact"
    FLEXIBLE_STRATEGY_USE = "flexible_strategy_use"
    STRATEGY_SHIFT_DIFFICULTY = "strategy_shift_difficulty"
    REASONING_UNDER_LOAD_EMERGING = "reasoning_under_load_emerging"
    TRIAL_AND_ERROR_STRATEGY = "trial_and_error_strategy"
    IMPULSIVE_RESPONSE = "impulsive_response"
    SELF_CORRECTION_PRESENT = "self_correction_present"
    RULE_MAINTENANCE_DIFFICULTY = "rule_maintenance_difficulty"


class GradeLevel(str, Enum):
    """Grade levels"""
    KINDERGARTEN_1 = "K-1"
    GRADE_1_2 = "1-2"
    GRADE_2_3 = "2-3"
    GRADE_3_4 = "3-4"


class UniversalSignal(BaseModel):
    """Universal signals captured for each item (spec §3)"""
    accuracy: str  # "correct", "incorrect", "partial"
    latency: int  # seconds
    attempts: int
    self_correction: bool
    post_shift_accuracy: Optional[str] = None  # "correct", "incorrect" — sort tasks only
    rule_inference: Optional[bool] = None  # grade 3-4 sort only
    explanation_quality: str = "none"  # "none", "limited", "clear"


class LogicOption(BaseModel):
    """Option/answer choice for a logic item"""
    index: int
    text: str
    image_url: Optional[str] = None


class SortRound(BaseModel):
    """A single round in a sort task"""
    round_number: int
    sort_rule: str  # "colour", "shape"
    num_bins: int
    rule_shown: bool = True  # False for grade 3-4 inference round


class SortTaskConfig(BaseModel):
    """Configuration for sort-task items (spec §4)"""
    cards: List[Dict[str, str]]  # e.g. [{"shape": "star", "colour": "red"}]
    rounds: List[SortRound]


class LogicItem(BaseModel):
    """Individual logic assessment item"""
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    grade_level: GradeLevel
    item_number: str  # e.g., "K1-1", "1-2-1"
    item_type: str  # "pattern", "analogy", "odd_one_out", "sort_task", etc.
    question_text: str
    options: List[LogicOption]
    correct_answer_index: int
    expected_latency_seconds: int = 30

    # Scoring tags
    primary_tag: CognitiveTag
    conditional_tags: Dict[str, CognitiveTag] = {}  # e.g., {"wrong_slow": "reasoning_under_load_emerging"}

    # Sort task config (only for item_type == "sort_task")
    sort_config: Optional[SortTaskConfig] = None

    # Metadata
    difficulty: str = "medium"  # "easy", "medium", "hard"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SortRoundResult(BaseModel):
    """Result for a single round of a sort task"""
    round_number: int
    accuracy: str  # "correct", "incorrect", "partial"
    latency: int  # seconds
    placements: List[Dict[str, str]] = []  # [{"card": "red star", "bin": "red"}]


class StudentResponse(BaseModel):
    """Student's response to a logic item"""
    student_id: str
    item_id: str
    selected_answer_index: int = 0  # 0 for sort tasks where answer is placement-based
    response_time_seconds: int
    attempts: int = 1
    self_corrected: bool = False
    explanation_provided: Optional[str] = None

    # Sort task specific (null for non-sort items)
    sort_rounds: Optional[List[SortRoundResult]] = None
    post_shift_accuracy: Optional[str] = None  # "correct"/"incorrect" after rule change
    rule_inferred: Optional[bool] = None  # grade 3-4 sort only

    # Computed during scoring
    is_correct: Optional[bool] = None
    tags_earned: List[CognitiveTag] = []


class TagOutput(BaseModel):
    """A single tag output with confidence and evidence (spec §6 Step 4)"""
    tag: CognitiveTag
    confidence: str  # "high", "medium", "low"
    evidence: str


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
    tag_outputs: List[TagOutput] = []  # {tag, confidence, evidence} per spec

    # Analysis
    reasoning_under_load_detected: bool = False
    trial_and_error_detected: bool = False
    strategy_shift_difficulty_detected: bool = False
    rule_maintenance_difficulty_detected: bool = False
    impulsive_response_detected: bool = False
    self_correction_detected: bool = False
    cognitive_flexibility_intact: bool = False
    flexible_strategy_use_detected: bool = False

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
        item_type="comparison",
        question_text="Which is bigger? Elephant or cat",
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
        item_id="k1_5",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-5",
        item_type="analogy",
        question_text="Bird goes with sky. Fish goes with ___",
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
        item_id="k1_6",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-6",
        item_type="pattern",
        question_text="1, 2, 3, ___",
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
        item_id="k1_7",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-7",
        item_type="rule_application",
        question_text="All flims are red. This is a flim. So it is ___",
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
        item_id="k1_8",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-8",
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
        item_id="k1_9",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-9",
        item_type="two_attribute_selection",
        question_text="Find the RED HEART",
        options=[
            LogicOption(index=0, text="Red star"),
            LogicOption(index=1, text="Blue star"),
            LogicOption(index=2, text="Red heart"),
            LogicOption(index=3, text="Blue heart"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        conditional_tags={"wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="medium",
    ),
    LogicItem(
        item_id="k1_10",
        grade_level=GradeLevel.KINDERGARTEN_1,
        item_number="K1-10",
        item_type="two_step",
        question_text=(
            "Look at these numbers: 2, 5, 3, 7. "
            "Which of these are bigger than 4?"
        ),
        options=[
            LogicOption(index=0, text="5, 7"),
            LogicOption(index=1, text="2, 3"),
            LogicOption(index=2, text="5, 3"),
            LogicOption(index=3, text="All of them"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=60,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={
            "wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        },
        difficulty="hard",
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
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        difficulty="easy",
    ),
    LogicItem(
        item_id="1_2_2",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-2",
        item_type="pattern",
        question_text="5, 10, 15, ___",
        options=[
            LogicOption(index=0, text="10"),
            LogicOption(index=1, text="20"),
            LogicOption(index=2, text="25"),
            LogicOption(index=3, text="30"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_3",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-3",
        item_type="odd_one_out",
        question_text="Which doesn't belong, and why? Dog, cat, table, bird",
        options=[
            LogicOption(index=0, text="Table (it's furniture)"),
            LogicOption(index=1, text="Bird (it flies)"),
            LogicOption(index=2, text="Dog (it barks)"),
            LogicOption(index=3, text="All belong"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_4",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-4",
        item_type="analogy",
        question_text="Big is to small as tall is to ___",
        options=[
            LogicOption(index=0, text="Short"),
            LogicOption(index=1, text="Long"),
            LogicOption(index=2, text="Wide"),
            LogicOption(index=3, text="High"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_5",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-5",
        item_type="rule_application",
        question_text="All squares have 4 sides. This shape has 4 sides. Definitely a square?",
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
        item_id="1_2_6",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-6",
        item_type="two_step",
        question_text=(
            "You have five cards, each with a number: "
            "Card A = 9, Card B = 4, Card C = 11, Card D = 6, Card E = 14. "
            "Which cards have a number bigger than 8?"
        ),
        options=[
            LogicOption(index=0, text="Card A, Card C, Card E"),
            LogicOption(index=1, text="Card B, Card D"),
            LogicOption(index=2, text="Card A, Card C"),
            LogicOption(index=3, text="All of them"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=50,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={
            "wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        },
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_7",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-7",
        item_type="multi_step_quantity",
        question_text="4 apples. Eat 1, pick 2 more. How many?",
        options=[
            LogicOption(index=0, text="3"),
            LogicOption(index=1, text="4"),
            LogicOption(index=2, text="5"),
            LogicOption(index=3, text="6"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_8",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-8",
        item_type="sequencing",
        question_text="Put in order, smallest to biggest: cat, ant, horse",
        options=[
            LogicOption(index=0, text="Ant, cat, horse"),
            LogicOption(index=1, text="Cat, ant, horse"),
            LogicOption(index=2, text="Horse, cat, ant"),
            LogicOption(index=3, text="Ant, horse, cat"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_9",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-9",
        item_type="two_attribute_selection",
        question_text=(
            "Find the number that is BOTH bigger than 10 AND smaller than 20."
        ),
        options=[
            LogicOption(index=0, text="8"),
            LogicOption(index=1, text="15"),
            LogicOption(index=2, text="22"),
            LogicOption(index=3, text="25"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        conditional_tags={
            "answer_0": CognitiveTag.RULE_MAINTENANCE_DIFFICULTY,
            "answer_3": CognitiveTag.RULE_MAINTENANCE_DIFFICULTY,
            "answer_2": CognitiveTag.RULE_MAINTENANCE_DIFFICULTY,
            "wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        },
        difficulty="medium",
    ),
    LogicItem(
        item_id="1_2_10",
        grade_level=GradeLevel.GRADE_1_2,
        item_number="1-2-10",
        item_type="two_step",
        question_text=(
            "Look at these numbers: 4, 9, 10, 6, 14. "
            "Which of these are bigger than 8?"
        ),
        options=[
            LogicOption(index=0, text="9, 10, 14"),
            LogicOption(index=1, text="4, 6"),
            LogicOption(index=2, text="9, 10"),
            LogicOption(index=3, text="All of them"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=70,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={
            "wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        },
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
        item_type="pattern",
        question_text="3, 6, 9, 12, ___",
        options=[
            LogicOption(index=0, text="13"),
            LogicOption(index=1, text="14"),
            LogicOption(index=2, text="15"),
            LogicOption(index=3, text="16"),
        ],
        correct_answer_index=2,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_2",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-2",
        item_type="pattern",
        question_text="2, 5, 2, 5, 2, ___",
        options=[
            LogicOption(index=0, text="2"),
            LogicOption(index=1, text="5"),
            LogicOption(index=2, text="7"),
            LogicOption(index=3, text="10"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=25,
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_3",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-3",
        item_type="odd_one_out",
        question_text="Which doesn't belong, and why? Rose, daisy, oak, tulip",
        options=[
            LogicOption(index=0, text="Oak (a tree)"),
            LogicOption(index=1, text="Rose (has thorns)"),
            LogicOption(index=2, text="Daisy (white petals)"),
            LogicOption(index=3, text="Tulip (spring flower)"),
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
        item_type="analogy",
        question_text="Hot is to cold as up is to ___",
        options=[
            LogicOption(index=0, text="Down"),
            LogicOption(index=1, text="Top"),
            LogicOption(index=2, text="Over"),
            LogicOption(index=3, text="High"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=30,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_5",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-5",
        item_type="syllogism",
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
        item_id="2_3_6",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-6",
        item_type="transitive_reasoning",
        question_text="A is taller than B, B is taller than C. Who is tallest?",
        options=[
            LogicOption(index=0, text="A"),
            LogicOption(index=1, text="B"),
            LogicOption(index=2, text="C"),
            LogicOption(index=3, text="Can't tell"),
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
        question_text="5 apples & 3 oranges. Take away 2 apples. Apples left?",
        options=[
            LogicOption(index=0, text="3"),
            LogicOption(index=1, text="4"),
            LogicOption(index=2, text="5"),
            LogicOption(index=3, text="6"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={"wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="hard",
    ),
    LogicItem(
        item_id="2_3_8",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-8",
        item_type="two_attribute_selection",
        question_text="Find the one that is a STAR, AND gold",
        options=[
            LogicOption(index=0, text="Terracotta star"),
            LogicOption(index=1, text="Gold star"),
            LogicOption(index=2, text="Gold heart"),
            LogicOption(index=3, text="Teal moon"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        conditional_tags={"wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="hard",
    ),
    LogicItem(
        item_id="2_3_9",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-9",
        item_type="sequencing",
        question_text="Put the steps in order: plant seed, water, flower grows, pick",
        options=[
            LogicOption(index=0, text="Plant seed, water, flower grows, pick"),
            LogicOption(index=1, text="Water, plant seed, pick, flower grows"),
            LogicOption(index=2, text="Flower grows, pick, plant seed, water"),
            LogicOption(index=3, text="Pick, flower grows, water, plant seed"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="2_3_10",
        grade_level=GradeLevel.GRADE_2_3,
        item_number="2-3-10",
        item_type="two_step",
        question_text=(
            "Look at these numbers: 12, 25, 8, 30, 17. "
            "Which of these are bigger than 15?"
        ),
        options=[
            LogicOption(index=0, text="25, 30, 17"),
            LogicOption(index=1, text="12, 8"),
            LogicOption(index=2, text="25, 30"),
            LogicOption(index=3, text="All of them"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=90,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={
            "wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        },
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
        item_type="pattern",
        question_text="2, 4, 8, 16, ___",
        options=[
            LogicOption(index=0, text="24"),
            LogicOption(index=1, text="32"),
            LogicOption(index=2, text="20"),
            LogicOption(index=3, text="18"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=35,
        primary_tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_2",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-2",
        item_type="pattern_rule_id",
        question_text="2, 5, 8, 11, ___ (rule and next number?)",
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
        item_type="odd_one_out",
        question_text="Which doesn't belong? Optimistic, pessimistic, realistic, happiness",
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
        item_type="analogy",
        question_text="Justice is to law as truth is to ___",
        options=[
            LogicOption(index=0, text="Proof"),
            LogicOption(index=1, text="Science"),
            LogicOption(index=2, text="Method"),
            LogicOption(index=3, text="Laboratory"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=50,
        primary_tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_5",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-5",
        item_type="conditional_logic",
        question_text="If it rains, the game is cancelled. It rained. The game was ___",
        options=[
            LogicOption(index=0, text="Definitely cancelled"),
            LogicOption(index=1, text="Probably cancelled"),
            LogicOption(index=2, text="Might happen"),
            LogicOption(index=3, text="Always happens"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_6",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-6",
        item_type="order_of_operations",
        question_text="10 − (3 + 2) × 2 = ___",
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
        item_id="3_4_7",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-7",
        item_type="multi_step_quantity",
        question_text="12 sweets, 3 friends share equally, each eats 1. Each has?",
        options=[
            LogicOption(index=0, text="2"),
            LogicOption(index=1, text="3"),
            LogicOption(index=2, text="4"),
            LogicOption(index=3, text="1"),
        ],
        correct_answer_index=1,
        expected_latency_seconds=45,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={"wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_8",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-8",
        item_type="negation_two_attribute",
        question_text="Find the shape that is NOT a star and NOT red",
        options=[
            LogicOption(index=0, text="Teal heart"),
            LogicOption(index=1, text="Gold star"),
            LogicOption(index=2, text="Terracotta star"),
            LogicOption(index=3, text="Red moon"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        conditional_tags={"wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING},
        difficulty="hard",
    ),
    LogicItem(
        item_id="3_4_9",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-9",
        item_type="sequencing",
        question_text="Put in logical order: buy ticket, board train, departs, arrive",
        options=[
            LogicOption(index=0, text="Buy ticket, board train, departs, arrive"),
            LogicOption(index=1, text="Board train, buy ticket, arrive, departs"),
            LogicOption(index=2, text="Departs, arrive, buy ticket, board train"),
            LogicOption(index=3, text="Arrive, departs, board train, buy ticket"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=40,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        difficulty="medium",
    ),
    LogicItem(
        item_id="3_4_10",
        grade_level=GradeLevel.GRADE_3_4,
        item_number="3-4-10",
        item_type="two_step",
        question_text=(
            "Look at these numbers: 9, 24, 31, 40, 15. "
            "Which of these are bigger than 20?"
        ),
        options=[
            LogicOption(index=0, text="24, 31, 40"),
            LogicOption(index=1, text="9, 15"),
            LogicOption(index=2, text="24, 31"),
            LogicOption(index=3, text="All of them"),
        ],
        correct_answer_index=0,
        expected_latency_seconds=90,
        primary_tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
        conditional_tags={
            "wrong_slow": CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
        },
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
    """Score a single response and assign cognitive tags (spec §3 signals)."""
    response.is_correct = response.selected_answer_index == item.correct_answer_index
    response.tags_earned = []

    if response.is_correct:
        response.tags_earned.append(item.primary_tag)
    else:
        # Check answer-index-specific conditional tags first
        answer_key = f"answer_{response.selected_answer_index}"
        if answer_key in item.conditional_tags:
            response.tags_earned.append(item.conditional_tags[answer_key])
        elif "wrong_slow" in item.conditional_tags:
            response.tags_earned.append(item.conditional_tags["wrong_slow"])

    # Sort task: check post-shift accuracy and shift difficulty
    if item.item_type == "sort_task":
        if response.post_shift_accuracy == "correct":
            # Avoid duplicate if primary_tag already added it
            if CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT not in response.tags_earned:
                response.tags_earned.append(CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT)
        elif response.post_shift_accuracy == "incorrect":
            response.tags_earned.append(CognitiveTag.STRATEGY_SHIFT_DIFFICULTY)

        # Grade 3-4 rule inference
        if response.rule_inferred is True:
            response.tags_earned.append(CognitiveTag.FLEXIBLE_STRATEGY_USE)

    # Self-correction: only counts when corrected TO the right answer (spec §6 Step 3)
    if response.self_corrected and response.is_correct:
        response.tags_earned.append(CognitiveTag.SELF_CORRECTION_PRESENT)

    return response


def aggregate_test_results(
    responses: List[StudentResponse], 
    grade_level: GradeLevel
) -> LogicTestResult:
    """Aggregate responses into final test result with cognitive profile (spec §6)."""
    
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
    
    # ── Step 1: Count by skill ──────────────────────────────────────────
    pattern_score = 0
    relational_score = 0
    systematic_score = 0
    load_fails = 0
    rule_maintenance_fails = 0
    shift_result = "no_sort"
    multiple_attempts_count = 0
    fast_and_wrong_count = 0
    self_corrected_to_right_count = 0
    rule_inferred = False

    latency_mult = 1.5
    fast_ratio = 0.5

    for response in responses:
        item = items_dict.get(response.item_id)
        if not item:
            continue

        is_correct = response.is_correct
        expected_time = item.expected_latency_seconds
        actual_time = response.response_time_seconds

        # Count correct by skill group
        if is_correct:
            if item.primary_tag == CognitiveTag.PATTERN_DETECTION_EMERGING:
                pattern_score += 1
            elif item.primary_tag == CognitiveTag.RELATIONAL_REASONING_PRESENT:
                relational_score += 1
            elif item.primary_tag == CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING:
                systematic_score += 1

        # Load fails: 2+ attribute / multi-step items wrong or slow
        if item.item_type in ("two_attribute_selection", "negation_two_attribute",
                              "multi_step_quantity", "two_step"):
            if not is_correct or actual_time > expected_time * latency_mult:
                load_fails += 1

        # Sort task: determine shift result
        if item.item_type == "sort_task":
            if response.post_shift_accuracy == "correct":
                shift_result = "shifted_ok"
            elif response.post_shift_accuracy == "incorrect":
                shift_result = "stuck"
            if response.rule_inferred is True:
                rule_inferred = True

        # Multiple attempts
        if response.attempts >= 2:
            multiple_attempts_count += 1

        # Fast and wrong
        if actual_time < expected_time * fast_ratio and not is_correct:
            fast_and_wrong_count += 1

        # Self-corrected to right
        if response.self_corrected and is_correct:
            self_corrected_to_right_count += 1

    # ── Step 2: Output strengths (corroborated) ─────────────────────────
    final_tags: List[CognitiveTag] = []
    tag_outputs: List[TagOutput] = []

    # pattern_detection_strong IF pattern_score >= 3 (incl. >=1 hard)
    pattern_hard_count = sum(
        1 for r in responses
        if r.is_correct
        and items_dict.get(r.item_id)
        and items_dict[r.item_id].primary_tag == CognitiveTag.PATTERN_DETECTION_EMERGING
        and items_dict[r.item_id].difficulty == "hard"
    )
    if pattern_score >= 3 and pattern_hard_count >= 1:
        final_tags.append(CognitiveTag.PATTERN_DETECTION_STRONG)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.PATTERN_DETECTION_STRONG,
            confidence="high",
            evidence=f"pattern_score={pattern_score} (incl. {pattern_hard_count} hard)",
        ))
    elif pattern_score >= 2:
        final_tags.append(CognitiveTag.PATTERN_DETECTION_EMERGING)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.PATTERN_DETECTION_EMERGING,
            confidence="high",
            evidence=f"pattern_score={pattern_score}",
        ))

    # relational_reasoning_present IF relational_score >= 3
    if relational_score >= 3:
        final_tags.append(CognitiveTag.RELATIONAL_REASONING_PRESENT)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.RELATIONAL_REASONING_PRESENT,
            confidence="high",
            evidence=f"relational_score={relational_score}",
        ))

    # systematic_problem_solving IF systematic_score >= 3
    if systematic_score >= 3:
        final_tags.append(CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING,
            confidence="high",
            evidence=f"systematic_score={systematic_score}",
        ))

    # cognitive_flexibility_intact IF shift_result == shifted_ok
    cognitive_flexibility_intact = shift_result == "shifted_ok"
    if cognitive_flexibility_intact:
        final_tags.append(CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.COGNITIVE_FLEXIBILITY_INTACT,
            confidence="medium",
            evidence="sort task post-shift accuracy: correct",
        ))

    # flexible_strategy_use IF inferred new rule in 3-4-10
    flexible_strategy_use = rule_inferred
    if flexible_strategy_use:
        final_tags.append(CognitiveTag.FLEXIBLE_STRATEGY_USE)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.FLEXIBLE_STRATEGY_USE,
            confidence="medium",
            evidence="child inferred hidden rule in grade 3-4 sort task",
        ))

    # ── Step 3: Output growth edges ─────────────────────────────────────
    reasoning_under_load = load_fails >= 2
    if reasoning_under_load:
        final_tags.append(CognitiveTag.REASONING_UNDER_LOAD_EMERGING)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.REASONING_UNDER_LOAD_EMERGING,
            confidence="high",
            evidence=f"load_fails={load_fails}",
        ))

    strategy_shift_difficulty = shift_result == "stuck"
    if strategy_shift_difficulty:
        final_tags.append(CognitiveTag.STRATEGY_SHIFT_DIFFICULTY)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.STRATEGY_SHIFT_DIFFICULTY,
            confidence="medium",
            evidence="sort task post-shift accuracy: incorrect (stuck in old rule)",
        ))

    rule_maintenance_difficulty = rule_maintenance_fails >= 2
    if rule_maintenance_difficulty:
        final_tags.append(CognitiveTag.RULE_MAINTENANCE_DIFFICULTY)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.RULE_MAINTENANCE_DIFFICULTY,
            confidence="low",
            evidence=f"rule_maintenance_fails={rule_maintenance_fails}",
        ))

    trial_and_error = multiple_attempts_count >= 2
    if trial_and_error:
        final_tags.append(CognitiveTag.TRIAL_AND_ERROR_STRATEGY)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.TRIAL_AND_ERROR_STRATEGY,
            confidence="high",
            evidence=f"multiple_attempts={multiple_attempts_count}",
        ))

    impulsive_response = fast_and_wrong_count >= 2
    if impulsive_response:
        final_tags.append(CognitiveTag.IMPULSIVE_RESPONSE)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.IMPULSIVE_RESPONSE,
            confidence="high",
            evidence=f"fast_and_wrong={fast_and_wrong_count}",
        ))

    self_correction = self_corrected_to_right_count >= 1
    if self_correction:
        final_tags.append(CognitiveTag.SELF_CORRECTION_PRESENT)
        tag_outputs.append(TagOutput(
            tag=CognitiveTag.SELF_CORRECTION_PRESENT,
            confidence="high",
            evidence=f"self_corrected_to_right={self_corrected_to_right_count}",
        ))

    # Build tag_counts for backward compatibility
    tag_counts: Dict[str, int] = {}
    for response in responses:
        for tag in response.tags_earned:
            tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1

    # Create result
    result = LogicTestResult(
        test_id=test_id,
        student_id=student_id,
        grade_level=grade_level,
        responses=responses,
        total_correct=total_correct,
        total_items=total_items,
        score_percentage=score_percentage,
        tag_counts=tag_counts,
        final_tags=final_tags,
        tag_outputs=tag_outputs,
        reasoning_under_load_detected=reasoning_under_load,
        trial_and_error_detected=trial_and_error,
        strategy_shift_difficulty_detected=strategy_shift_difficulty,
        rule_maintenance_difficulty_detected=rule_maintenance_difficulty,
        impulsive_response_detected=impulsive_response,
        self_correction_detected=self_correction,
        cognitive_flexibility_intact=cognitive_flexibility_intact,
        flexible_strategy_use_detected=flexible_strategy_use,
    )
    
    return result
