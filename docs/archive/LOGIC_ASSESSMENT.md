# Cognitive Logic Assessment System (K-4)

## Overview

A comprehensive Python-based cognitive assessment system for measuring logical reasoning, pattern recognition, and problem-solving skills in kindergarten through 4th grade students.

### What's Included

1. **Complete Item Bank** - 40 logic assessment items across 4 grade levels
2. **Cognitive Tagging System** - 8 cognitive domain tags for detailed profiling
3. **Scoring & Aggregation** - Automatic scoring with cognitive profile generation
4. **FastAPI Endpoints** - RESTful API for test delivery and result retrieval
5. **Web Interface** - Interactive HTML-based test interface
6. **Data Models** - Pydantic models for type-safe data handling

---

## Core Components

### 1. Logic Assessment Module (`logic_assessment.py`)

Core Python module containing:
- **40 Logic Items** - Pre-built assessments across 4 grade levels
  - K-1 (10 items): Pattern detection, basic reasoning
  - Grade 1-2 (10 items): Multi-step logic, flexibility
  - Grade 2-3 (10 items): Complex patterns, systematic solving
  - Grade 3-4 (10 items): Abstract reasoning, conditional logic

- **Cognitive Tags** (8 total):
  - `pattern_detection_strong` - Strong pattern recognition ability
  - `pattern_detection_emerging` - Developing pattern skills
  - `relational_reasoning_present` - Can identify relationships
  - `systematic_problem_solving` - Structured approach to problems
  - `flexible_strategy_use` - Can generate multiple strategies
  - `cognitive_flexibility_intact` - Can shift approaches
  - `trial_and_error_strategy` - Uses trial-and-error frequently
  - `reasoning_under_load_emerging` - Struggles under pressure/complexity

- **Scoring System**:
  - Automatic correct/incorrect detection
  - Conditional tagging based on performance patterns
  - Aggregation with configurable thresholds
  - Weakness pattern detection

### 2. FastAPI Routes (`logic_routes.py`)

Four main endpoints:

#### GET TEST
```
POST /logic/get_test/
```
Returns 10 assessment items for a grade level
- Input: Grade level (K-1, 1-2, 2-3, 3-4)
- Output: Test ID, items with options

#### SUBMIT RESPONSE
```
POST /logic/submit_response/
```
Score a single item response (incremental)
- Input: Item ID, selected answer, response time
- Output: Correctness, tags earned, feedback

#### SUBMIT TEST
```
POST /logic/submit_test/
```
Submit all responses at once
- Input: All responses for test
- Output: Score, percentage, cognitive tags, analysis

#### COMPLETE RESULT
```
POST /logic/complete_result/
```
Retrieve detailed test results
- Input: Test ID
- Output: Full cognitive profile, recommendations

---

## Installation

1. **Install Python module**:
```bash
# Dependencies already in requirements.txt
pip install -r requirements.txt
```

2. **Add to FastAPI app** (`main.py`):
```python
from logic_routes import setup_logic_routes

# In your FastAPI app initialization
setup_logic_routes(app)

# Now routes available at /logic/*
```

---

## Usage Examples

### Python (Direct API)

```python
from logic_assessment import (
    StudentResponse, 
    aggregate_test_results, 
    GradeLevel, 
    get_items_by_grade
)

# Get items for Grade 1-2
items = get_items_by_grade(GradeLevel.GRADE_1_2)

# Create responses
responses = [
    StudentResponse(
        student_id="child_123",
        item_id="1_2_1",
        selected_answer_index=2,
        response_time_seconds=25,
        attempts=1,
    ),
    # ... more responses
]

# Score and aggregate
result = aggregate_test_results(responses, GradeLevel.GRADE_1_2)

print(f"Score: {result.total_correct}/{result.total_items}")
print(f"Cognitive Tags: {result.final_tags}")
print(f"Weaknesses: {result.reasoning_under_load_detected}")
```

### REST API (cURL)

```bash
# Get test
curl -X POST http://localhost:8000/logic/get_test/ \
  -H "Content-Type: application/json" \
  -d '{
    "idToken": "eyJ...",
    "child_id": "child_123",
    "grade": "1-2"
  }'

# Submit test
curl -X POST http://localhost:8000/logic/submit_test/ \
  -H "Content-Type: application/json" \
  -d '{
    "idToken": "eyJ...",
    "child_id": "child_123",
    "grade": "1-2",
    "test_id": "test_abc123",
    "responses": [
      {
        "item_id": "1_2_1",
        "selected_answer_index": 2,
        "response_time_seconds": 25,
        "attempts": 1
      }
    ]
  }'
```

### Web Interface

Simply open `logic_test_web.html` in a browser:
1. Select grade level (K-1, 1-2, 2-3, 3-4)
2. Answer 10 logic questions
3. View cognitive profile and recommendations

---

## Cognitive Tags Explained

| Tag | Meaning | What It Indicates |
|-----|---------|-------------------|
| **pattern_detection_strong** | Excellence in patterns | Child easily identifies sequences and rules |
| **pattern_detection_emerging** | Developing pattern skills | Child is learning to recognize patterns |
| **relational_reasoning_present** | Strong reasoning | Child understands relationships and analogies |
| **systematic_problem_solving** | Methodical approach | Child uses structured, step-by-step logic |
| **flexible_strategy_use** | Creative problem-solving | Child invents new approaches to problems |
| **cognitive_flexibility_intact** | Adapts strategies | Child switches methods when needed |
| **trial_and_error_strategy** | Exploratory approach | Child relies heavily on guessing/trying |
| **reasoning_under_load_emerging** | Struggles with complexity | Child struggles when problems get harder |

---

## Aggregation Logic

The system applies a 3-step scoring process:

### Step 1: Count Signals
- Track which tags appear and how often
- Count pattern detection, reasoning, and flexibility tags

### Step 2: Apply Thresholds
```
IF pattern_score >= 3 → pattern_detection_strong
IF reasoning_score >= 3 → relational_reasoning_present
IF flexibility_score >= 2 → cognitive_flexibility_intact
```

### Step 3: Detect Weakness Patterns
```
IF reasoning_under_load_tags >= 2 → reasoning_under_load_emerging
IF trial_and_error_tags >= 2 → trial_and_error_strategy
IF flexibility_failures >= 1 → strategy_shift_difficulty
```

### Output
Final JSON with cognitive profile:
```json
{
  "logic_domain_tags": [
    "pattern_detection_strong",
    "relational_reasoning_present",
    "systematic_problem_solving",
    "reasoning_under_load_emerging"
  ]
}
```

---

## Item Bank Structure

### K-1 Grade (10 Items)
Focus: Basic pattern detection and relationships
- K1-1: Pattern AB recognition
- K1-2: Shape patterns
- K1-3: Odd one out
- K1-4: Matching
- K1-5: Size comparison
- K1-6: Simple analogy
- K1-7: Counting pattern
- K1-8: Rule application
- K1-9: Categorization
- K1-10: Pattern continuation

### Grade 1-2 (10 Items)
Focus: Multi-step logic and flexibility
- 1-2-1 through 1-2-10: Increasing complexity
- Introduces matrix reasoning
- Tests cognitive flexibility

### Grade 2-3 (10 Items - CORE BAND)
Focus: Systematic problem solving
- 2-3-1 through 2-3-10: Advanced patterns
- Skip patterns, alternating sequences
- Multi-step quantity problems

### Grade 3-4 (10 Items)
Focus: Abstract reasoning
- 3-4-1 through 3-4-10: Exponential patterns
- Conditional logic
- Dual classification

---

## Files in This System

| File | Purpose |
|------|---------|
| `logic_assessment.py` | Core Python module with items, models, and scoring |
| `logic_routes.py` | FastAPI endpoints |
| `logic_test_web.html` | Interactive web interface |
| `LOGIC_ASSESSMENT.md` | This documentation |

---

## Integration with Existing APIs

This system follows the same pattern as existing comprehension and speaking APIs:

```python
# All three assessment types follow the same structure:
/comprehension/get_stories/
/logic/get_test/           # ← Parallel structure
/speaking/get_prompts/

/comprehension/submit/
/logic/submit_test/        # ← Parallel structure
/speaking/submit/

/comprehension/complete_result/
/logic/complete_result/    # ← Parallel structure
/speaking/complete_result/
```

---

## Performance Levels

Based on percentage scores:

| Score Range | Level | Interpretation |
|------------|-------|-----------------|
| 90-100% | Exceptional Logical Thinker | Excellent reasoning, ready for advanced |
| 80-89% | Advanced Logical Thinker | Strong skills, progressing well |
| 70-79% | Good Logical Thinker | At grade level, solid foundations |
| 60-69% | Developing Logical Thinker | Progressing, needs reinforcement |
| 0-59% | Emerging Logical Thinker | Early stages, foundational work needed |

---

## Universal Signals (Captured for Each Item)

Every response captures 5 universal metrics:

1. **Accuracy** - Correct/incorrect/partial
2. **Latency** - Response time in seconds
3. **Attempts** - Number of tries before finalizing
4. **Self Correction** - Whether student self-corrected
5. **Explanation Quality** - None/limited/clear explanation

These feed into tag assignment logic.

---

## Recommendations Engine

Based on cognitive profile, system generates recommendations:

**For Strong Pattern Detection:**
- "Your child excels at finding patterns. Try Sudoku or logic puzzles!"

**For Reasoning Under Load:**
- "Your child struggles when problems get complex. Practice multi-step problems slowly."

**For Trial and Error:**
- "Your child explores by trying options. Encourage planning before attempting."

**For Strategy Flexibility:**
- "Your child adapts well to new approaches. Great problem-solver!"

---

## Future Enhancements

1. **Adaptive Testing** - Difficulty adjusts based on performance
2. **Item Difficulty Calibration** - Track item difficulty across student population
3. **Longitudinal Tracking** - Track progress over multiple test sessions
4. **Explanations Scoring** - Analyze quality of student explanations
5. **Computer Vision** - Accept hand-drawn pattern answers
6. **Multilingual Support** - Items in multiple languages
7. **Parent Dashboard** - Real-time progress tracking
8. **Teacher Analytics** - Class-level performance insights

---

## Troubleshooting

### Items not loading?
- Check that `ALL_LOGIC_ITEMS` is properly defined in `logic_assessment.py`
- Verify grade level enum matches (K-1, 1-2, 2-3, 3-4)

### Scoring incorrect?
- Ensure `correct_answer_index` matches option index (0-3)
- Verify aggregation thresholds in `aggregate_test_results()`

### Tags not appearing?
- Check that tags are in `CognitiveTag` enum
- Verify scoring logic in `score_response()` function
- Check threshold values in aggregation step

---

## References

### Cognitive Assessment Theory
- Bloom's Taxonomy (Knowledge levels)
- Piaget's Concrete Operations (K-4 stage)
- Sternberg's Triarchic Theory (Reasoning types)

### Assessment Best Practices
- Reliability: Consistent item quality across all items
- Validity: Items truly measure cognitive constructs
- Fairness: Accessible to students with diverse backgrounds
- Actionability: Results lead to specific recommendations

---

## Support

For issues or questions about the logic assessment system:
1. Check this documentation
2. Review logic_assessment.py comments
3. Refer to API response examples in logic_routes.py
4. Test with logic_test_web.html

---

**Version:** 1.0  
**Last Updated:** June 2026  
**Status:** Production Ready
