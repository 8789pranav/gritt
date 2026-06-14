# Cognitive Logic Assessment API

This document describes the current Cognitive Logic Assessment endpoints, their request payloads, and the response structure returned by the FastAPI app.

## Base URL

- Local: http://localhost:8000
- Deployed: use your deployed API base URL

## Authentication

All logic endpoints require:
- `idToken`: Firebase ID token from the existing login flow
- `child_id`: the child UUID that belongs to the authenticated user

If the token is invalid or the child does not belong to the user, the API returns HTTP 401 or 404.

---

## 1) Get Logic Test

### Endpoint
POST /logic/get_test/

### Request body
```json
{
  "idToken": "firebase_id_token",
  "child_id": "child-uuid",
  "grade": "Kindergarten"
}
```

Supported grade examples:
- Kindergarten
- First
- Second
- Third

### Response body
```json
{
  "success": true,
  "test_id": "uuid",
  "grade": "Kindergarten",
  "total_items": 10,
  "instructions": "Solve each logic puzzle carefully...",
  "items": [
    {
      "item_id": "k1_1",
      "item_number": "K1-1",
      "item_type": "pattern",
      "question_text": "Red, blue, red, blue, ___",
      "difficulty": "easy",
      "options": [
        { "index": 0, "text": "Red", "image_url": null },
        { "index": 1, "text": "Blue", "image_url": null }
      ]
    }
  ]
}
```

### Notes
- Returns a fresh test payload for the requested grade.
- `items` contains the logic item bank for that grade.

---

## 2) Submit One Logic Response

### Endpoint
POST /logic/submit_response/

### Request body
```json
{
  "idToken": "firebase_id_token",
  "child_id": "child-uuid",
  "item_id": "k1_1",
  "selected_answer_index": 0,
  "response_time_seconds": 4,
  "attempts": 1,
  "self_corrected": false,
  "explanation_provided": "Test response"
}
```

### Response body
```json
{
  "success": true,
  "item_id": "k1_1",
  "is_correct": false,
  "tags_earned": [],
  "feedback": "Not quite right. Try again or review the pattern.",
  "correct_answer_index": 1,
  "correct_answer": "Blue"
}
```

### Notes
- This endpoint performs immediate scoring for one item.
- `tags_earned` is currently returned as a list of cognitive tag strings when available.

---

## 3) Submit Full Logic Test

### Endpoint
POST /logic/submit_test/

### Request body
```json
{
  "idToken": "firebase_id_token",
  "child_id": "child-uuid",
  "grade": "Kindergarten",
  "test_id": "uuid-from-get_test",
  "responses": [
    {
      "item_id": "k1_1",
      "selected_answer_index": 0,
      "response_time_seconds": 4
    }
  ]
}
```

### Response body
```json
{
  "success": true,
  "test_id": "uuid",
  "student_id": "child-uuid",
  "grade": "Kindergarten",
  "total_items": 1,
  "correct_answers": 0,
  "score": 0,
  "percentage": 0.0,
  "level": "Emerging Logical Thinker",
  "cognitive_tags": [],
  "tag_breakdown": {},
  "reasoning_under_load_detected": false,
  "trial_and_error_detected": false,
  "strategy_shift_difficulty_detected": false,
  "message": "Test completed: 0/1 correct (0.0%)",
  "score_id": "firebase-score-id"
}
```

### Notes
- The result is also saved under the child’s Firebase score history.
- `score_id` is the Firebase push key for that saved result.

---

## 4) Get Complete Logic Result

### Endpoint
POST /logic/complete_result/

### Request body
```json
{
  "idToken": "firebase_id_token",
  "child_id": "child-uuid",
  "test_id": "uuid-from-get_test",
  "grade": "Kindergarten"
}
```

### Response body
```json
{
  "success": true,
  "student_id": "child-uuid",
  "test_id": "uuid",
  "grade": "Kindergarten",
  "test_timestamp": "2026-06-06T13:25:11.226572",
  "summary": {
    "total_items": 10,
    "correct_answers": 7,
    "percentage": 70.0,
    "cognitive_tags": [
      "pattern_detection_strong",
      "systematic_problem_solving"
    ]
  },
  "parent_summary": {
    "overall_score": "7/10",
    "percentage": 70.0,
    "performance_level": "Good Logical Thinker",
    "grade_placement": "At Grade Level",
    "next_step": "Practice multi-step logic puzzles and pattern recognition",
    "strengths": [
      "Strong pattern detection abilities",
      "Good systematic problem-solving"
    ],
    "areas_to_develop": [
      "Cognitive flexibility under time pressure",
      "Strategy shifting when first approach fails"
    ],
    "recommendation": "Your child shows solid logical reasoning skills. Continue with puzzles and pattern activities.",
    "note": "This assessment is instructional and not a clinical diagnosis."
  },
  "actions": [
    { "label": "Retry Test", "type": "button", "action": "retry_test" },
    { "label": "View Items", "type": "button", "action": "view_items" }
  ]
}
```

### Notes
- This is a presentation-style result payload for parents and UI consumers.
- The current implementation returns a static summary structure for this endpoint.

---

## 5) Logic UI Page

### Endpoint
GET /logic/ui

### Response
Returns the HTML page stored in the project as the logic assessment UI.

---

## Common HTTP Status Codes

- 200: success
- 401: invalid Firebase token
- 404: child not found for the authenticated user
- 400: invalid grade or malformed request
- 500: unexpected server error

---

## Example Test Flow

1. POST /login/ to get an `idToken`
2. POST /get_children/ to get a `child_id`
3. POST /logic/get_test/ with `idToken`, `child_id`, `grade`
4. POST /logic/submit_response/ for each item if needed
5. POST /logic/submit_test/ to save the final test result
6. POST /logic/complete_result/ to get the parent-facing summary
