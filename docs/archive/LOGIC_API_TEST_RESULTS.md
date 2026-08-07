# Logic Test API - Test Results Documentation

**Date:** 2026-06-14 20:05:00
**Base URL:** http://localhost:8000
**Child ID:** f9fee450-a1ae-4d56-b0a7-e6edb6536074
**Grade:** Kindergarten

---

## Summary

| Test | Endpoint | Status | Response Time |
|------|----------|--------|---------------|
| Login | POST /login | ✅ PASS | 3.309s |
| Get Test | POST /logic/get_test/ | ✅ PASS | 3.686s |
| Submit Response | POST /logic/submit_response/ | ✅ PASS | 2.476s |
| Submit Test | POST /logic/submit_test/ | ✅ PASS | 3.255s |
| Complete Result | POST /logic/complete_result/ | ✅ PASS | 2.868s |
| Logic UI | GET /logic/ui | ✅ PASS | 2.241s |

---

## 1. Login Endpoint

**Endpoint:** `POST /login`

### Request
```json
{
  "email": "rajdandeepak@gmail.com",
  "password": "Test@123"
}
```

### Response
```json
{
  "success": true,
  "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6Ijc5OTRiNGYzMTU2MzJiMj..."
}
```

---

## 2. Get Logic Test Endpoint

**Endpoint:** `POST /logic/get_test/`

### Request
```json
{
  "idToken": "<Firebase ID Token>",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "Kindergarten"
}
```

### Response
```json
{
  "success": true,
  "test_id": "1efc6a47-7a49-4cb3-ae2a-edaeec72840c",
  "grade": "Kindergarten",
  "total_items": 10,
  "instructions": "Solve each logic puzzle carefully. Think about patterns, relationships, and rules. Take your time and do your best!",
  "items": [
    {
      "item_id": "k1_1",
      "item_number": "K1-1",
      "item_type": "pattern",
      "question_text": "Red, blue, red, blue, ___",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "Red",
          "image_url": null
        },
        {
          "index": 1,
          "text": "Blue",
          "image_url": null
        },
        {
          "index": 2,
          "text": "Green",
          "image_url": null
        },
        {
          "index": 3,
          "text": "Yellow",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_2",
      "item_number": "K1-2",
      "item_type": "pattern",
      "question_text": "Circle, circle, square, circle, circle, ___",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "Circle",
          "image_url": null
        },
        {
          "index": 1,
          "text": "Square",
          "image_url": null
        },
        {
          "index": 2,
          "text": "Triangle",
          "image_url": null
        },
        {
          "index": 3,
          "text": "Rectangle",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_3",
      "item_number": "K1-3",
      "item_type": "odd_one_out",
      "question_text": "Which one doesn't belong? Apple, banana, car",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "Apple",
          "image_url": null
        },
        {
          "index": 1,
          "text": "Banana",
          "image_url": null
        },
        {
          "index": 2,
          "text": "Car",
          "image_url": null
        },
        {
          "index": 3,
          "text": "None",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_4",
      "item_number": "K1-4",
      "item_type": "matching",
      "question_text": "Find the matching shape (star shape shown)",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "Circle",
          "image_url": null
        },
        {
          "index": 1,
          "text": "Star",
          "image_url": null
        },
        {
          "index": 2,
          "text": "Square",
          "image_url": null
        },
        {
          "index": 3,
          "text": "Triangle",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_5",
      "item_number": "K1-5",
      "item_type": "comparison",
      "question_text": "Which is bigger? Elephant or cat?",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "Elephant",
          "image_url": null
        },
        {
          "index": 1,
          "text": "Cat",
          "image_url": null
        },
        {
          "index": 2,
          "text": "Same size",
          "image_url": null
        },
        {
          "index": 3,
          "text": "Can't tell",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_6",
      "item_number": "K1-6",
      "item_type": "analogy",
      "question_text": "Bird is to sky as fish is to ___",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "Air",
          "image_url": null
        },
        {
          "index": 1,
          "text": "Water",
          "image_url": null
        },
        {
          "index": 2,
          "text": "Land",
          "image_url": null
        },
        {
          "index": 3,
          "text": "Clouds",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_7",
      "item_number": "K1-7",
      "item_type": "sequence",
      "question_text": "What comes next? 1, 2, 3, ___",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "1",
          "image_url": null
        },
        {
          "index": 1,
          "text": "4",
          "image_url": null
        },
        {
          "index": 2,
          "text": "5",
          "image_url": null
        },
        {
          "index": 3,
          "text": "2",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_8",
      "item_number": "K1-8",
      "item_type": "rule_application",
      "question_text": "All glims are red. This is a glim. So this is ___",
      "difficulty": "medium",
      "options": [
        {
          "index": 0,
          "text": "Red",
          "image_url": null
        },
        {
          "index": 1,
          "text": "Blue",
          "image_url": null
        },
        {
          "index": 2,
          "text": "Green",
          "image_url": null
        },
        {
          "index": 3,
          "text": "Yellow",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_9",
      "item_number": "K1-9",
      "item_type": "categorization",
      "question_text": "How many are animals? Dog, cat, apple, bird",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "1",
          "image_url": null
        },
        {
          "index": 1,
          "text": "2",
          "image_url": null
        },
        {
          "index": 2,
          "text": "3",
          "image_url": null
        },
        {
          "index": 3,
          "text": "4",
          "image_url": null
        }
      ]
    },
    {
      "item_id": "k1_10",
      "item_number": "K1-10",
      "item_type": "pattern",
      "question_text": "Clap, tap, clap, tap, ___",
      "difficulty": "easy",
      "options": [
        {
          "index": 0,
          "text": "Clap",
          "image_url": null
        },
        {
          "index": 1,
          "text": "Tap",
          "image_url": null
        },
        {
          "index": 2,
          "text": "Snap",
          "image_url": null
        },
        {
          "index": 3,
          "text": "Stomp",
          "image_url": null
        }
      ]
    }
  ]
}
```

### Notes
- Returns 10 test items for the grade level
- Each item includes item_id, question_text, options, and difficulty level

---

## 3. Submit Single Response Endpoint

**Endpoint:** `POST /logic/submit_response/`

### Request
```json
{
  "idToken": "<Firebase ID Token>",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "item_id": "k1_1",
  "selected_answer_index": 0,
  "response_time_seconds": 5,
  "attempts": 1,
  "self_corrected": false,
  "explanation_provided": "Test response"
}
```

### Response
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
- Scores individual item response
- Returns is_correct, tags_earned, and feedback

---

## 4. Submit Full Test Endpoint

**Endpoint:** `POST /logic/submit_test/`

### Request
```json
{
  "idToken": "<Firebase ID Token>",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "Kindergarten",
  "responses": [
    {
      "item_id": "<item_id>",
      "selected_answer_index": 0,
      "response_time_seconds": 5,
      "attempts": 1,
      "self_corrected": false,
      "explanation_provided": "Test response"
    }
  ]
}
```

### Response
```json
{
  "success": true,
  "test_id": "1a91c0af-ca0d-436a-a36b-5e2ffe3156fa",
  "student_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "Kindergarten",
  "total_items": 10,
  "correct_answers": 2,
  "score": 2,
  "percentage": 20.0,
  "level": "Emerging Logical Thinker",
  "cognitive_tags": [],
  "tag_breakdown": {
    "CognitiveTag.RELATIONAL_REASONING_PRESENT": 1,
    "CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING": 1
  },
  "reasoning_under_load_detected": false,
  "trial_and_error_detected": false,
  "strategy_shift_difficulty_detected": false,
  "message": "Test completed: 2/10 correct (20.0%)",
  "score_id": "-Ov5YdXbUDBR2BFyvpCI"
}
```

### Notes
- Submits all responses at once
- Returns overall score, percentage, level, and cognitive tags

---

## 5. Complete Result Endpoint

**Endpoint:** `POST /logic/complete_result/`

### Request
```json
{
  "idToken": "<Firebase ID Token>",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "Kindergarten"
}
```

### Response
```json
{
  "success": true,
  "student_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "test_id": "",
  "grade": "Kindergarten",
  "test_timestamp": "2026-06-14T14:34:55.096789",
  "summary": {
    "total_items": 10,
    "correct_answers": 2,
    "percentage": 20.0,
    "level": "Emerging Logical Thinker",
    "cognitive_tags": [],
    "tag_breakdown": {
      "CognitiveTag_RELATIONAL_REASONING_PRESENT": 1,
      "CognitiveTag_SYSTEMATIC_PROBLEM_SOLVING": 1
    }
  },
  "parent_summary": {
    "overall_score": "2/10",
    "percentage": 20.0,
    "performance_level": "Emerging Logical Thinker",
    "grade_placement": "Below Grade Level",
    "next_step": "Focus on basic pattern recognition and logical reasoning exercises",
    "strengths": [
      "Completed the logic assessment"
    ],
    "areas_to_develop": [
      "Continue practicing logic puzzles"
    ],
    "recommendation": "Starting the logical reasoning journey. Use hands-on manipulatives and visual pattern activities.",
    "note": "This assessment is instructional and not a clinical diagnosis."
  },
  "behavioral_signals": {
    "reasoning_under_load": false,
    "trial_and_error": false,
    "strategy_shift_difficulty": false
  },
  "actions": [
    {
      "label": "Retry Test",
      "type": "button",
      "action": "retry_test"
    },
    {
      "label": "View Items",
      "type": "button",
      "action": "view_items"
    },
    {
      "label": "Download Report",
      "type": "button",
      "action": "download_pdf"
    }
  ]
}
```

### Notes
- Returns comprehensive result with parent summary
- Includes strengths, areas to develop, and recommendations

---

## 6. Logic UI Endpoint

**Endpoint:** `GET /logic/ui`

### Response
- **Status:** 200 OK
- **Content Type:** text/html
- **Page Size:** N/A bytes

### Notes
- Returns the Logic Assessment web UI HTML page
- Can be accessed directly in browser at: http://localhost:8000/logic/ui

---

## Error Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Invalid request or grade |
| 401 | Invalid Firebase token |
| 404 | Child not found |
| 500 | Server error |

---

## API Flow

1. **Login** → Get `idToken`
2. **Get Test** → Get test items with `item_id`s
3. **Submit Response** (optional) → Score individual items
4. **Submit Test** → Submit all responses
5. **Complete Result** → Get detailed parent-friendly summary

---

## Notes

- All endpoints require valid Firebase authentication
- The `idToken` must be refreshed periodically (expires after 1 hour)
- Child must belong to the authenticated user
- Grade values: Kindergarten, First, Second, Third
