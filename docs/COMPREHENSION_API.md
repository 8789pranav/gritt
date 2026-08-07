# Reading Comprehension API Documentation

**Base URL:** `http://localhost:8000` (Development) | `https://your-domain.com` (Production)

---

## Overview

The Reading Comprehension API provides endpoints for:
1. **Get Stories** - Fetch grade-appropriate stories with audio narration
2. **Submit Answers** - Submit MCQ answers and get scores
3. **Get Results** - Retrieve detailed test results

### Supported Grades
- `Kindergarten`
- `First`
- `Second`
- `Third`

---

## 1. Get Comprehension Stories

Fetches 2 stories with pre-generated audio and 4 questions each (8 total questions).

### Endpoint
```
POST /comprehension/get_stories/
```

### Request Headers
```
Content-Type: application/json
```

### Request Payload
```json
{
    "idToken": "eyJhbGciOiJSUzI1NiIs...",
    "child_id": "2715cf08-1b5e-46dc-8c3b-a2bab5ecdcec",
    "grade": "Kindergarten"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | string | Yes | Firebase ID token from login |
| `child_id` | string | Yes | UUID of the child taking the test |
| `grade` | string | Yes | One of: `Kindergarten`, `First`, `Second`, `Third` |

### Response (Success - 200)
```json
{
    "grade": "Kindergarten",
    "total_stories": 2,
    "total_questions": 8,
    "instructions": "Listen to each story carefully, then answer the questions. Each question has 4 options.",
    "stories": [
        {
            "story_id": "k_story_1",
            "title": "The Friendly Dog",
            "story_text": "Once upon a time... (full story text)",
            "story_audio_base64": "//uQxAAAAAANIAAAAAE...",
            "audio_source": "cached_openai",
            "duration_estimate": "60 seconds",
            "questions": [
                {
                    "id": "k1_q1",
                    "question": "What color was Max the dog?",
                    "options": ["White", "Brown", "Black", "Gray"]
                },
                {
                    "id": "k1_q2",
                    "question": "What did Tom throw for Max?",
                    "options": ["A stick", "A yellow ball", "A frisbee", "A bone"]
                },
                {
                    "id": "k1_q3",
                    "question": "What was the cat's name?",
                    "options": ["Fluffy", "Whiskers", "Mittens", "Tiger"]
                },
                {
                    "id": "k1_q4",
                    "question": "Where did Max like to sleep?",
                    "options": ["On the floor", "In his bed", "Near the window", "Outside"]
                }
            ],
            "total_questions": 4
        },
        {
            "story_id": "k_story_2",
            "title": "The Magic Garden",
            "story_text": "Once upon a time... (full story text)",
            "story_audio_base64": "//uQxAAAAAANIAAAAAE...",
            "audio_source": "cached_openai",
            "duration_estimate": "60 seconds",
            "questions": [
                {
                    "id": "k2_q1",
                    "question": "What color was Lily's watering can?",
                    "options": ["Red", "Blue", "Green", "Yellow"]
                },
                {
                    "id": "k2_q2",
                    "question": "What came to visit Lily's garden?",
                    "options": ["A bird", "A butterfly", "A bee", "A ladybug"]
                },
                {
                    "id": "k2_q3",
                    "question": "What did Lily do to help her plants grow?",
                    "options": ["She read to them", "She gave them water", "She played music", "She talked to them"]
                },
                {
                    "id": "k2_q4",
                    "question": "What color was NOT mentioned for the flowers?",
                    "options": ["Red", "Yellow", "Pink", "Orange"]
                }
            ],
            "total_questions": 4
        }
    ]
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `grade` | string | The grade level requested |
| `total_stories` | number | Always 2 |
| `total_questions` | number | Always 8 (4 per story) |
| `instructions` | string | Instructions for the child |
| `stories` | array | Array of story objects |
| `stories[].story_id` | string | Unique story identifier |
| `stories[].title` | string | Story title |
| `stories[].story_text` | string | Full story text (for display) |
| `stories[].story_audio_base64` | string | Base64 MP3 audio (~1-2MB) |
| `stories[].audio_source` | string | `cached_openai`, `openai_tts`, or `aws_polly` |
| `stories[].duration_estimate` | string | Estimated audio duration |
| `stories[].questions` | array | 4 MCQ questions |
| `stories[].questions[].id` | string | Question ID (e.g., `k1_q1`) |
| `stories[].questions[].question` | string | Question text |
| `stories[].questions[].options` | array | 4 answer options (strings) |

### Error Responses

**401 Unauthorized**
```json
{
    "detail": "Invalid token: Token expired or invalid"
}
```

**404 Not Found**
```json
{
    "detail": "Child not found"
}
```

**400 Bad Request**
```json
{
    "detail": "Invalid grade. Must be: Kindergarten, First, Second, or Third"
}
```

---

## 2. Submit Comprehension Test

Submit answers for all 8 questions and receive immediate scoring.

### Endpoint
```
POST /comprehension/submit/
```

### Request Headers
```
Content-Type: application/json
```

### Request Payload
```json
{
    "idToken": "eyJhbGciOiJSUzI1NiIs...",
    "child_id": "2715cf08-1b5e-46dc-8c3b-a2bab5ecdcec",
    "grade": "Kindergarten",
    "story_answers": [
        {
            "story_id": "k_story_1",
            "answers": [
                {"question_id": "k1_q1", "selected_index": 1},
                {"question_id": "k1_q2", "selected_index": 1},
                {"question_id": "k1_q3", "selected_index": 0},
                {"question_id": "k1_q4", "selected_index": 2}
            ]
        },
        {
            "story_id": "k_story_2",
            "answers": [
                {"question_id": "k2_q1", "selected_index": 1},
                {"question_id": "k2_q2", "selected_index": 1},
                {"question_id": "k2_q3", "selected_index": 1},
                {"question_id": "k2_q4", "selected_index": 3}
            ]
        }
    ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | string | Yes | Firebase ID token |
| `child_id` | string | Yes | Child UUID |
| `grade` | string | Yes | Grade level |
| `story_answers` | array | Yes | Array of story answer objects |
| `story_answers[].story_id` | string | Yes | Story ID from get_stories |
| `story_answers[].answers` | array | Yes | Array of question answers |
| `story_answers[].answers[].question_id` | string | Yes | Question ID |
| `story_answers[].answers[].selected_index` | number | Yes | Selected option index (0-3) |

### Response (Success - 200)
```json
{
    "success": true,
    "user_id": "OUE6yVj1m5MUQ3Tx7H9mXa6SbzA3",
    "child_id": "2715cf08-1b5e-46dc-8c3b-a2bab5ecdcec",
    "grade": "Kindergarten",
    "test_id": "-OrUU11fXulv1a5VjCWb",
    "total_questions": 8,
    "correct_answers": 7,
    "score": 7,
    "max_score": 8,
    "percentage": 87.5,
    "level": "Good Reader",
    "status": "At",
    "recommendation": "Good understanding of the stories. Continue practicing with varied reading materials.",
    "results": [
        {
            "story_id": "k_story_1",
            "story_title": "The Friendly Dog",
            "questions": [
                {
                    "question_id": "k1_q1",
                    "question": "What color was Max the dog?",
                    "selected_index": 1,
                    "selected_answer": "Brown",
                    "correct_index": 1,
                    "correct_answer": "Brown",
                    "is_correct": true
                },
                {
                    "question_id": "k1_q2",
                    "question": "What did Tom throw for Max?",
                    "selected_index": 1,
                    "selected_answer": "A yellow ball",
                    "correct_index": 1,
                    "correct_answer": "A yellow ball",
                    "is_correct": true
                }
            ]
        }
    ],
    "message": "Test completed: 7/8 correct (87.5%)"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always true on success |
| `user_id` | string | Firebase user ID |
| `child_id` | string | Child UUID |
| `grade` | string | Grade level tested |
| `test_id` | string | Firebase test ID (for retrieving results) |
| `total_questions` | number | Total questions (8) |
| `correct_answers` | number | Number correct |
| `score` | number | Same as correct_answers |
| `max_score` | number | Maximum possible (8) |
| `percentage` | number | Score percentage (0-100) |
| `level` | string | Reading level assessment |
| `status` | string | `Above`, `At`, or `Below` grade level |
| `recommendation` | string | Personalized recommendation |
| `results` | array | Detailed per-question results |
| `message` | string | Summary message |

### Scoring Levels

| Percentage | Level | Status |
|------------|-------|--------|
| 90-100% | Excellent Reader | Above |
| 75-89% | Good Reader | At |
| 50-74% | Developing Reader | Below |
| 0-49% | Needs Practice | Below |

---

## 3. Get Complete Results

Retrieve detailed results for the most recent comprehension test.

### Endpoint
```
POST /comprehension/complete_result/
```

### Request Headers
```
Content-Type: application/json
```

### Request Payload
```json
{
    "idToken": "eyJhbGciOiJSUzI1NiIs...",
    "child_id": "2715cf08-1b5e-46dc-8c3b-a2bab5ecdcec",
    "grade": "Kindergarten"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | string | Yes | Firebase ID token |
| `child_id` | string | Yes | Child UUID |
| `grade` | string | No | Filter by grade (optional) |

### Response (Success - 200)
```json
{
    "user_id": "OUE6yVj1m5MUQ3Tx7H9mXa6SbzA3",
    "child_id": "2715cf08-1b5e-46dc-8c3b-a2bab5ecdcec",
    "grade": "Kindergarten",
    "test_timestamp": "2026-04-30T17:42:27.574306",
    "summary": {
        "total_questions": 8,
        "correct_answers": 7,
        "percentage": 87.5,
        "level": "Good Reader",
        "status": "At"
    },
    "parent_summary": {
        "overall_score": "7/8",
        "percentage": 87.5,
        "level": "Good Reader",
        "grade_placement": "At Grade Level",
        "next_step": "Continue with current grade level materials",
        "recommendation": "Good understanding of the stories. Continue practicing with varied reading materials.",
        "note": "Assessment is instructional and not a clinical diagnosis."
    },
    "story_breakdown": [
        {
            "story_id": "k_story_1",
            "story_title": "The Friendly Dog",
            "correct": 4,
            "total": 4,
            "percentage": 100.0,
            "questions": [
                {
                    "question_id": "k1_q1",
                    "question": "What color was Max the dog?",
                    "selected_index": 1,
                    "selected_answer": "Brown",
                    "correct_index": 1,
                    "correct_answer": "Brown",
                    "is_correct": true
                },
                {
                    "question_id": "k1_q2",
                    "question": "What did Tom throw for Max?",
                    "selected_index": 1,
                    "selected_answer": "A yellow ball",
                    "correct_index": 1,
                    "correct_answer": "A yellow ball",
                    "is_correct": true
                },
                {
                    "question_id": "k1_q3",
                    "question": "What was the cat's name?",
                    "selected_index": 0,
                    "selected_answer": "Fluffy",
                    "correct_index": 0,
                    "correct_answer": "Fluffy",
                    "is_correct": true
                },
                {
                    "question_id": "k1_q4",
                    "question": "Where did Max like to sleep?",
                    "selected_index": 2,
                    "selected_answer": "Near the window",
                    "correct_index": 2,
                    "correct_answer": "Near the window",
                    "is_correct": true
                }
            ]
        },
        {
            "story_id": "k_story_2",
            "story_title": "The Magic Garden",
            "correct": 3,
            "total": 4,
            "percentage": 75.0,
            "questions": [
                {
                    "question_id": "k2_q1",
                    "question": "What color was Lily's watering can?",
                    "selected_index": 1,
                    "selected_answer": "Blue",
                    "correct_index": 1,
                    "correct_answer": "Blue",
                    "is_correct": true
                },
                {
                    "question_id": "k2_q2",
                    "question": "What came to visit Lily's garden?",
                    "selected_index": 1,
                    "selected_answer": "A butterfly",
                    "correct_index": 1,
                    "correct_answer": "A butterfly",
                    "is_correct": true
                },
                {
                    "question_id": "k2_q3",
                    "question": "What did Lily do to help her plants grow?",
                    "selected_index": 1,
                    "selected_answer": "She gave them water",
                    "correct_index": 1,
                    "correct_answer": "She gave them water",
                    "is_correct": true
                },
                {
                    "question_id": "k2_q4",
                    "question": "What color was NOT mentioned for the flowers?",
                    "selected_index": 0,
                    "selected_answer": "Red",
                    "correct_index": 3,
                    "correct_answer": "Orange",
                    "is_correct": false
                }
            ]
        }
    ],
    "actions": [
        {"label": "Retry Test", "type": "button", "action": "retry_test"},
        {"label": "View Stories", "type": "button", "action": "view_stories"},
        {"label": "Download Report (PDF)", "type": "button", "action": "download_pdf"}
    ]
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | Firebase user ID |
| `child_id` | string | Child UUID |
| `grade` | string | Grade tested |
| `test_timestamp` | string | ISO timestamp of test |
| `summary` | object | Quick summary stats |
| `summary.total_questions` | number | Total questions |
| `summary.correct_answers` | number | Correct count |
| `summary.percentage` | number | Score percentage |
| `summary.level` | string | Reading level |
| `summary.status` | string | Grade level status |
| `parent_summary` | object | Detailed parent-friendly summary |
| `parent_summary.overall_score` | string | "7/8" format |
| `parent_summary.grade_placement` | string | Grade level placement |
| `parent_summary.next_step` | string | Recommended next action |
| `parent_summary.recommendation` | string | Personalized advice |
| `parent_summary.note` | string | Disclaimer |
| `story_breakdown` | array | Per-story detailed results |
| `story_breakdown[].story_id` | string | Story ID |
| `story_breakdown[].story_title` | string | Story title |
| `story_breakdown[].correct` | number | Correct in this story |
| `story_breakdown[].total` | number | Total in this story (4) |
| `story_breakdown[].percentage` | number | Story score percentage |
| `story_breakdown[].questions` | array | Question-level details |
| `actions` | array | UI action buttons |

---

## Admin Endpoints

### 4. Pre-generate All Story Audio

Generates and caches audio for all stories in all grades.

### Endpoint
```
POST /admin/pregenerate_story_audio/
```

### Request Payload
```json
{
    "idToken": "eyJhbGciOiJSUzI1NiIs..."
}
```

### Response (Success - 200)
```json
{
    "success": true,
    "message": "Audio pre-generation completed",
    "summary": {
        "total_stories": 8,
        "successful": 8,
        "failed": 0,
        "total_time_seconds": 145.2
    },
    "details": [
        {
            "grade": "Kindergarten",
            "story_id": "k_story_1",
            "title": "The Friendly Dog",
            "status": "success",
            "audio_size_bytes": 1170720,
            "generation_time": 12.5
        }
    ]
}
```

---

### 5. Regenerate Story Audio

Force regenerate audio for specific story or all stories.

### Endpoint
```
POST /admin/regenerate_story_audio/
```

### Request Payload
```json
{
    "idToken": "eyJhbGciOiJSUzI1NiIs...",
    "grade": "Kindergarten",
    "story_id": "k_story_1"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | string | Yes | Firebase ID token |
| `grade` | string | No | Specific grade (omit for all) |
| `story_id` | string | No | Specific story (omit for all in grade) |

### Response (Success - 200)
```json
{
    "success": true,
    "regenerated": [
        {
            "grade": "Kindergarten",
            "story_id": "k_story_1",
            "title": "The Friendly Dog",
            "status": "success"
        }
    ]
}
```

---

## Authentication

All endpoints require a valid Firebase ID token obtained from the `/login` endpoint.

### Login Endpoint
```
POST /login
```

### Request Payload
```json
{
    "email": "user@example.com",
    "password": "yourpassword"
}
```

### Response
```json
{
    "id_token": "eyJhbGciOiJSUzI1NiIs...",
    "user_id": "firebase_user_id",
    "email": "user@example.com"
}
```

---

# Cognitive Logic Assessment (K–4)

## Full Item Bank + Tag Mapping Specification

---

## Core Tags (Logic Domain)

All grades map to this same tag set:

- `pattern_detection_strong`
- `relational_reasoning_present`
- `systematic_problem_solving`
- `flexible_strategy_use`
- `trial_and_error_strategy`
- `cognitive_flexibility_intact`
- `strategy_shift_difficulty`
- `reasoning_under_load_emerging`

---

## Universal Signals (used across all grades)

Each item must capture:

- **accuracy** (correct / incorrect / partial)
- **latency**
- **attempts**
- **self_correction**
- **explanation_quality** (none / limited / clear)

---

## K–1 LOGIC TEST (10 Items)

### K1-1 Pattern AB
- **Item:** Red, blue, red, blue, ___ → blue
- **Tags:**
  - correct → `pattern_detection_emerging`
  - incorrect + retries → `trial_and_error_strategy`

### K1-2 Shape Pattern
- **Item:** Circle, circle, square, circle, circle, ___ → square
- **Tags:** correct → `pattern_detection_emerging`

### K1-3 Odd One Out
- **Item:** Apple, banana, car → car
- **Tags:** correct → `relational_reasoning_present`

### K1-4 Matching
- **Item:** Find identical shape
- **Tags:** correct → `pattern_detection_emerging`

### K1-5 Size Comparison
- **Item:** Elephant vs cat → elephant
- **Tags:** correct → `relational_reasoning_present`

### K1-6 Analogy
- **Item:** Bird → sky, fish → water
- **Tags:** correct → `relational_reasoning_present`

### K1-7 Counting Pattern
- **Item:** 1, 2, 3 → 4
- **Tags:** correct → `pattern_detection_emerging`

### K1-8 Rule Application
- **Item:** All flims are red → this is red
- **Tags:** correct → `systematic_problem_solving`

### K1-9 Grouping
- **Item:** 3 animals + 1 object
- **Tags:** correct → `relational_reasoning_present`

### K1-10 Pattern Continuation
- **Item:** Clap, tap → tap
- **Tags:** correct → `pattern_detection_strong`

---

## Grade 1–2 LOGIC TEST

| Item | Tag | Notes |
|------|-----|-------|
| Pattern (Triangle, square → square) | `pattern_detection_strong` | - |
| Number Pattern (5, 10, 15 → 20) | `pattern_detection_strong` | - |
| Odd One Out + Why | `relational_reasoning_present` | Downgrade if no explanation |
| Matrix | `pattern_detection_strong` or `reasoning_under_load_emerging` | Partial response indicates emerging |
| Analogy | `relational_reasoning_present` | - |
| Rule | `systematic_problem_solving` | - |
| Quantity | `systematic_problem_solving` or `reasoning_under_load_emerging` | Incorrect = emerging |
| Category Shift | `cognitive_flexibility_intact` or `strategy_shift_difficulty` | Success = intact; fail second = difficulty |
| Two-Step | `systematic_problem_solving` or `reasoning_under_load_emerging` | Breakdown = emerging |
| Pattern Creation | `flexible_strategy_use` | Valid + explanation required |

---

## Grade 2–3 LOGIC TEST (CORE BAND)

| Item | Example | Primary Tag | Secondary Tag |
|------|---------|-------------|----------------|
| Skip Pattern | 3, 6, 9 → 15 | `pattern_detection_strong` | - |
| Alternating Pattern | 2, 5, 2, 5 → 5 | `pattern_detection_strong` | `trial_and_error_strategy` if repeated error |
| Odd One Out + Why | Varies | `relational_reasoning_present` | - |
| Matrix (2-rule) | Varies | `systematic_problem_solving` | `reasoning_under_load_emerging` if partial |
| Analogy | Varies | `relational_reasoning_present` | - |
| Rule | Varies | `systematic_problem_solving` | - |
| Multi-Step Quantity | Varies | `systematic_problem_solving` | `reasoning_under_load_emerging` if breakdown |
| Category Shift | Varies | `cognitive_flexibility_intact` or `strategy_shift_difficulty` | - |
| Two-Step Rule | Varies | `systematic_problem_solving` | - |
| Pattern Creation | Varies | `flexible_strategy_use` | - |

---

## Grade 3–4 LOGIC TEST

| Item | Example | Primary Tag | Secondary Tag |
|------|---------|-------------|----------------|
| Pattern (Exponential) | 2, 4, 8 → 32 | `pattern_detection_strong` | - |
| Pattern (Linear Shift) | 2, 5, 8 → 14 | `systematic_problem_solving` | - |
| Abstract Odd One | Varies | `relational_reasoning_present` | - |
| Matrix (Multi-attribute) | Varies | `systematic_problem_solving` | `reasoning_under_load_emerging` if partial |
| Analogy (Abstract) | Varies | `relational_reasoning_present` | - |
| Conditional Logic | Varies | `relational_reasoning_present` or `reasoning_under_load_emerging` | - |
| Multi-Step Quantity | Varies | `systematic_problem_solving` | - |
| Strategy Shift | Varies | `cognitive_flexibility_intact` or `strategy_shift_difficulty` | - |
| Dual Classification | Varies | `relational_reasoning_present` | + flexibility signals |
| Pattern Generation | Varies | `flexible_strategy_use` | - |

---

## Aggregation Logic (FINAL TAG DECISION)

### Step 1: Count Signals

```
pattern_score = count(pattern_detection)
reasoning_score = count(relational + systematic)
flexibility_score = count(flexibility signals)
```

### Step 2: Apply Thresholds

- IF pattern_score >= 3 → `pattern_detection_strong`
- IF reasoning_score >= 3 → `relational_reasoning_present`
- IF flexibility_score >= 2 → `cognitive_flexibility_intact`

### Step 3: Detect Weakness Patterns

- IF easy_correct AND hard_incorrect → `reasoning_under_load_emerging`
- IF repeated_attempts OR guessing → `trial_and_error_strategy`
- IF flexibility_fail → `strategy_shift_difficulty`

### Step 4: Output

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

## What This System Captures

### Strengths

- Pattern recognition
- Structured reasoning
- Abstraction
- Flexibility

### Constraints

- Breakdown under load
- Inability to shift strategy
- Guessing behavior

### Development Signals

- Emerging reasoning
- Inconsistent performance
- Explanation gaps
    "refresh_token": "AMf-vBxc...",
    "expires_in": "3600",
    "user_id": "OUE6yVj1m5MUQ3Tx7H9mXa6SbzA3"
}
```

---

## Audio Playback

The `story_audio_base64` field contains MP3 audio encoded in base64. To play it:

### JavaScript Example
```javascript
// Decode and play audio
const audioData = stories[0].story_audio_base64;
const audioBlob = new Blob(
    [Uint8Array.from(atob(audioData), c => c.charCodeAt(0))],
    { type: 'audio/mp3' }
);
const audioUrl = URL.createObjectURL(audioBlob);
const audio = new Audio(audioUrl);
audio.play();
```

### Flutter Example
```dart
import 'dart:convert';
import 'package:audioplayers/audioplayers.dart';

final audioPlayer = AudioPlayer();
final audioBytes = base64Decode(story['story_audio_base64']);
await audioPlayer.playBytes(audioBytes);
```

---

## Error Codes

| Status | Description |
|--------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid/expired token |
| 404 | Not Found - Child or test not found |
| 500 | Server Error |

---

## Rate Limits

- **Get Stories**: May take 5-30 seconds depending on cache
- **Submit**: Immediate response
- **Results**: Immediate response

---

## Data Storage (Firebase)

```
users/{user_id}/
├── children/{child_id}/
│   └── comprehension_tests/{test_id}/
│       ├── grade: "Kindergarten"
│       ├── results: [...]
│       ├── correct_answers: 7
│       ├── max_score: 8
│       ├── percentage: 87.5
│       ├── level: "Good Reader"
│       └── timestamp: "2026-04-30T17:42:27"

story_audio/{grade}/{story_id}/
├── audio_base64: "//uQxAAA..."
├── title: "The Friendly Dog"
├── voice: "nova"
└── generated_at: "2026-04-30T15:00:00"
```
