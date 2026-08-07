# Logic API Testing Guide

## Overview

This guide provides comprehensive testing for all Logic Assessment API endpoints. The test suite includes functional tests, multi-grade tests, and edge case validation.

## Test Files

### 1. `test_logic_comprehensive.py`
**Comprehensive Logic API Test Suite**

Tests the complete workflow of the Logic Assessment API:
- ✅ User authentication
- ✅ Get logic test items
- ✅ Submit single response
- ✅ Submit complete test
- ✅ Get complete result with parent summary

**Usage:**
```bash
python test_logic_comprehensive.py
```

**What it tests:**
- Full end-to-end workflow
- Response validation
- Score calculation
- Cognitive tag generation
- Parent-friendly summaries

---

### 2. `test_logic_all_grades.py`
**Multi-Grade Logic API Test**

Tests all supported grade levels:
- Kindergarten
- First
- Second
- Third
- K-1, 1-2, 2-3, 3-4 (alternative formats)

**Usage:**
```bash
python test_logic_all_grades.py
```

**What it tests:**
- Grade-specific item retrieval
- Item type distribution per grade
- Score calculation across grades
- Result generation for all levels

---

### 3. `test_logic_edge_cases.py`
**Edge Cases & Error Handling Test**

Tests error handling and edge cases:
- ❌ Invalid authentication tokens
- ❌ Invalid grade levels
- ❌ Invalid child IDs
- ❌ Invalid item IDs
- ❌ Out-of-range answer indices
- ❌ Negative response times
- ❌ Empty response lists
- ❌ Duplicate item responses
- ❌ Missing required fields

**Usage:**
```bash
python test_logic_edge_cases.py
```

**What it tests:**
- API error responses
- Input validation
- Security (token verification)
- Data integrity

---

### 4. `run_all_logic_tests.py`
**Master Test Runner**

Runs all test suites and generates comprehensive report.

**Usage:**
```bash
python run_all_logic_tests.py
```

**Features:**
- Runs all test suites sequentially
- Generates summary report
- Saves detailed JSON report
- Provides pass/fail statistics
- Measures execution time

---

## Configuration

All test scripts use the following configuration (edit at the top of each file):

```python
BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"
GRADE = "Kindergarten"
```

### How to Update Configuration

1. **Change Base URL** (for deployed API):
   ```python
   BASE_URL = "https://your-api-domain.com"
   ```

2. **Change Test Credentials**:
   ```python
   EMAIL = "your-email@example.com"
   PASSWORD = "YourPassword123"
   ```

3. **Change Child ID**:
   ```python
   CHILD_ID = "your-child-uuid-here"
   ```

---

## API Endpoints Tested

### 1. POST `/logic/get_test/`
**Get Logic Assessment Test**

**Request:**
```json
{
  "idToken": "firebase-id-token",
  "child_id": "child-uuid",
  "grade": "Kindergarten"
}
```

**Response:**
```json
{
  "success": true,
  "test_id": "test-uuid",
  "grade": "Kindergarten",
  "total_items": 10,
  "instructions": "Solve each logic puzzle...",
  "items": [...]
}
```

---

### 2. POST `/logic/submit_response/`
**Submit Single Item Response**

**Request:**
```json
{
  "idToken": "firebase-id-token",
  "child_id": "child-uuid",
  "item_id": "item-uuid",
  "selected_answer_index": 2,
  "response_time_seconds": 15,
  "attempts": 1,
  "self_corrected": false,
  "explanation_provided": null
}
```

**Response:**
```json
{
  "success": true,
  "is_correct": true,
  "item_id": "item-uuid",
  "tags_earned": ["pattern_detection_strong"],
  "feedback": "Correct! You found the right answer.",
  "correct_answer_index": 2,
  "correct_answer": "Option text"
}
```

---

### 3. POST `/logic/submit_test/`
**Submit Complete Test**

**Request:**
```json
{
  "idToken": "firebase-id-token",
  "child_id": "child-uuid",
  "grade": "Kindergarten",
  "responses": [
    {
      "item_id": "item-1",
      "selected_answer_index": 0,
      "response_time_seconds": 10,
      "attempts": 1,
      "self_corrected": false
    },
    ...
  ]
}
```

**Response:**
```json
{
  "success": true,
  "test_id": "test-uuid",
  "student_id": "child-uuid",
  "grade": "Kindergarten",
  "total_items": 10,
  "correct_answers": 7,
  "score": 7,
  "percentage": 70.0,
  "level": "Good Logical Thinker",
  "cognitive_tags": [...],
  "tag_breakdown": {...},
  "reasoning_under_load_detected": false,
  "trial_and_error_detected": false,
  "strategy_shift_difficulty_detected": false,
  "message": "Test completed: 7/10 correct (70.0%)"
}
```

---

### 4. POST `/logic/complete_result/`
**Get Complete Result with Parent Summary**

**Request:**
```json
{
  "idToken": "firebase-id-token",
  "child_id": "child-uuid",
  "grade": "Kindergarten"
}
```

**Response:**
```json
{
  "success": true,
  "student_id": "child-uuid",
  "test_id": "test-uuid",
  "grade": "Kindergarten",
  "test_timestamp": "2024-01-01T12:00:00",
  "summary": {
    "total_items": 10,
    "correct_answers": 7,
    "percentage": 70.0,
    "level": "Good Logical Thinker",
    "cognitive_tags": [...],
    "tag_breakdown": {...}
  },
  "parent_summary": {
    "overall_score": "7/10",
    "percentage": 70.0,
    "performance_level": "Good Logical Thinker",
    "grade_placement": "At Grade Level",
    "next_step": "Practice multi-step logic puzzles...",
    "strengths": [...],
    "areas_to_develop": [...],
    "recommendation": "Your child shows solid logical reasoning...",
    "note": "This assessment is instructional..."
  },
  "behavioral_signals": {
    "reasoning_under_load": false,
    "trial_and_error": false,
    "strategy_shift_difficulty": false
  },
  "actions": [...]
}
```

---

## Prerequisites

### 1. Install Dependencies
```bash
pip install requests
```

### 2. Start the API Server
```bash
python main.py
```

The server should be running on `http://localhost:8000`

### 3. Verify Authentication
Ensure you have:
- Valid Firebase credentials
- Test user account created
- Child profile created with the specified ID

---

## Running Tests

### Quick Start (Run All Tests)
```bash
python run_all_logic_tests.py
```

### Individual Test Suites

**1. Comprehensive Test:**
```bash
python test_logic_comprehensive.py
```

**2. All Grades Test:**
```bash
python test_logic_all_grades.py
```

**3. Edge Cases Test:**
```bash
python test_logic_edge_cases.py
```

---

## Understanding Test Output

### Success Indicators
- ✅ Green checkmarks indicate passed tests
- 📊 Statistics show test metrics
- 🎉 Celebration message when all tests pass

### Failure Indicators
- ❌ Red X marks indicate failed tests
- ⚠️ Warning symbols show unexpected behavior
- Error messages provide debugging information

### Test Metrics
- **Status Code**: HTTP response status
- **Duration**: Time taken for each test
- **Score**: Correct/Total items
- **Percentage**: Score percentage
- **Tags**: Cognitive tags earned

---

## Troubleshooting

### Common Issues

**1. Connection Refused**
```
Error: Connection refused
```
**Solution:** Ensure the API server is running on the correct port.

**2. Authentication Failed**
```
Status: 401 Unauthorized
```
**Solution:** Check email/password credentials and Firebase configuration.

**3. Child Not Found**
```
Status: 404 Not Found
```
**Solution:** Verify the child ID exists in the database.

**4. Invalid Grade**
```
Status: 400 Bad Request
```
**Solution:** Use valid grade values: Kindergarten, First, Second, Third, K-1, 1-2, 2-3, 3-4

---

## Test Report

After running `run_all_logic_tests.py`, a JSON report is generated:

**File:** `logic_test_report_YYYYMMDD_HHMMSS.json`

**Contents:**
```json
{
  "timestamp": "2024-01-01T12:00:00",
  "total_suites": 3,
  "passed": 3,
  "failed": 0,
  "total_duration": 45.67,
  "results": [...]
}
```

---

## Best Practices

### 1. Test Regularly
Run tests after any API changes to ensure backward compatibility.

### 2. Review Failed Tests
Investigate failures immediately to identify root causes.

### 3. Update Test Data
Keep test credentials and IDs current with your test environment.

### 4. Monitor Performance
Track test duration to identify performance regressions.

### 5. Validate Edge Cases
Ensure error handling works correctly for invalid inputs.

---

## API Grade Levels

| Grade String | Description | Items |
|-------------|-------------|-------|
| Kindergarten | K-1st Grade | 10 |
| First | 1st-2nd Grade | 10 |
| Second | 2nd-3rd Grade | 10 |
| Third | 3rd-4th Grade | 10 |
| K-1 | Alternative format | 10 |
| 1-2 | Alternative format | 10 |
| 2-3 | Alternative format | 10 |
| 3-4 | Alternative format | 10 |

---

## Cognitive Tags

The API generates cognitive tags based on performance:

### Positive Tags
- `pattern_detection_strong`
- `relational_reasoning_present`
- `systematic_problem_solving`
- `cognitive_flexibility_intact`
- `flexible_strategy_use`

### Emerging Tags
- `pattern_detection_emerging`
- `reasoning_under_load_emerging`
- `trial_and_error_strategy`
- `strategy_shift_difficulty`

---

## Performance Levels

| Percentage | Level |
|-----------|-------|
| 90%+ | Exceptional Logical Thinker |
| 80-89% | Advanced Logical Thinker |
| 70-79% | Good Logical Thinker |
| 60-69% | Developing Logical Thinker |
| <60% | Emerging Logical Thinker |

---

## Support

For issues or questions:
1. Check API logs for detailed error messages
2. Review Firebase authentication status
3. Verify database connectivity
4. Check test configuration values

---

## License

This testing suite is part of the Logic Assessment API project.

---

**Last Updated:** 2024
**Version:** 1.0.0
