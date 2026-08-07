# Dear Parent Project — Complete API Documentation

> **Version**: 1.0.0  
> **Base URL (Production)**: `https://nvupmmyd66.us-east-1.awsapprunner.com`  
> **Base URL (Local)**: `http://localhost:8000`  
> **Framework**: FastAPI (Python 3.11)  
> **Last Updated**: August 2026

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Authentication](#2-authentication)
3. [User Management APIs](#3-user-management-apis)
4. [Spelling Assessment APIs](#4-spelling-assessment-apis)
5. [Logic Quest Assessment APIs](#5-logic-quest-assessment-apis)
6. [Speaking Assessment APIs](#6-speaking-assessment-apis)
7. [Reading Comprehension APIs](#7-reading-comprehension-apis)
8. [Feedback API](#8-feedback-api)
9. [Admin APIs](#9-admin-apis)
10. [Cognitive Tagging System](#10-cognitive-tagging-system)
11. [Logic Quest Question Bank](#11-logic-quest-question-bank)
12. [Data Models](#12-data-models)
13. [Firebase Database Schema](#13-firebase-database-schema)
14. [Deployment](#14-deployment)
15. [Security Notes](#15-security-notes)

---

## 1. Architecture Overview

### Tech Stack

| Component | Technology |
|---|---|
| Web Framework | FastAPI (Python 3.11) |
| Authentication | Firebase Auth (ID token verification) |
| Database | Firebase Realtime Database |
| Text-to-Speech | OpenAI TTS (`tts-1-hd`, voice: `nova`) with AWS Polly fallback (voice: `Joanna`) |
| Speech-to-Text | OpenAI Whisper |
| AI Analysis | OpenAI GPT-4o |
| Containerization | Docker (Python 3.11-slim) |
| Deployment | AWS ECR → AWS App Runner |
| Cognitive Tagging | Custom engine (`tagging_engine.py` + `dear_parent_tags_config.json`) |

### Project Structure

```
grittt/
├── main.py                      # FastAPI app — all endpoint definitions
├── logic_assessment.py          # Logic Quest data models, question bank, scoring
├── logic_service.py             # Logic Quest service layer (payload, scoring, results)
├── logic_routes.py              # Logic Quest router (alternative endpoint definitions)
├── tagging_engine.py            # Cognitive tag derivation engine
├── dear_parent_tags_config.json # Tag definitions, triggers, thresholds
├── all_logic_questions.json     # Logic questions in JSON format
├── Dockerfile                   # Docker build config
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables
├── test_apis.py                 # Local API tests (speaking)
├── test_deployed_api.py         # Deployed API tests
├── test_logic_new_questions.py  # Logic Quest question verification
├── test_logic_local.py          # Local logic scoring tests
├── test_logic_spec_verify.py    # Full spec verification (32 questions)
├── check_deploy.py              # AWS App Runner status checker
└── logic_test_web.html          # Web UI for logic assessment
```

### Assessment Domains

The platform covers **4 cognitive assessment domains** for children in Kindergarten through 3rd Grade:

1. **Spelling** — Phonics, sight words, nonsense words
2. **Logic Quest** — Pattern recognition, relational reasoning, systematic problem solving, cognitive flexibility, reasoning under load
3. **Speaking** — Pronunciation, fluency, grammar, speaking rate (via Whisper + GPT-4o)
4. **Reading Comprehension** — Story listening + multiple-choice questions

Each domain produces:
- **Raw scores** (correct/total, percentage, level)
- **Cognitive tags** (strengths and growth edges via the tagging engine)
- **Parent-friendly summary** (strengths, areas to develop, recommendations)
- **Per-item breakdown** (detailed results for each question/word/sentence)

---

## 2. Authentication

All protected endpoints require a **Firebase ID token** in the request body (not in headers).

### Token Verification

```python
# Standard verification
decoded_token = auth.verify_id_token(request.idToken)
user_id = decoded_token["uid"]

# Child-scoped verification (logic endpoints)
user_id, child_data = verify_child_and_token(request.idToken, request.child_id)
```

### Token Format

Tokens are obtained via the `/login` endpoint and are Firebase JWT ID tokens. They expire after 1 hour (3600 seconds). A refresh token is also returned for renewal.

---

## 3. User Management APIs

### 3.1 Register

```
POST /register/
```

Creates a new Firebase user account.

**Request:**
```json
{
  "email": "parent@example.com",
  "password": "securepassword123",
  "name": "John Doe"
}
```

**Response (200):**
```json
{
  "message": "User created successfully",
  "user_id": "firebase_uid_here"
}
```

**Errors:**
- `400`: Email already registered
- `500`: Registration failed

---

### 3.2 Login

```
POST /login
```

Authenticates a user and returns Firebase tokens.

**Request:**
```json
{
  "email": "parent@example.com",
  "password": "securepassword123"
}
```

**Response (200):**
```json
{
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "AMf-vBx...",
  "expires_in": "3600",
  "user_id": "firebase_localId_here"
}
```

**Errors:**
- `400`: Invalid credentials

---

### 3.3 Save User Data

```
POST /save-user-data/
```

Saves user profile data to Firebase Realtime Database.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "name": "John Doe",
  "email": "parent@example.com"
}
```

**Response (200):**
```json
{
  "message": "User data saved successfully",
  "user_id": "firebase_uid_here"
}
```

---

### 3.4 Get User Details

```
POST /user-details/
```

Retrieves stored user details. Verifies that provided details match stored data.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "email": "parent@example.com",
  "name": "John Doe",
  "age": "35"
}
```

**Response (200):**
```json
{
  "name": "John Doe",
  "email": "parent@example.com",
  "age": "35"
}
```

**Errors:**
- `400`: Provided details don't match stored data
- `404`: User data not found

---

### 3.5 Add Child

```
POST /add_child/
```

Creates a child profile under the authenticated user's account.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "name": "Emma",
  "age": 6,
  "grade": "Kindergarten"
}
```

**Grade values**: `"Kindergarten"`, `"First"`, `"Second"`, `"Third"`

**Response (200):**
```json
{
  "child_id": "uuid-generated-here",
  "message": "Child added successfully"
}
```

**Errors:**
- `400`: Invalid child data (name, age, or grade)
- `500`: Failed to add child

---

### 3.6 Get Children

```
POST /get_children/
```

Retrieves all children profiles for the authenticated user.

**Request:**
```json
{
  "idToken": "eyJhbGci..."
}
```

**Response (200):**
```json
{
  "children": [
    {
      "child_id": "uuid-1",
      "name": "Emma",
      "age": 6,
      "grade": "Kindergarten"
    },
    {
      "child_id": "uuid-2",
      "name": "Liam",
      "age": 8,
      "grade": "Second"
    }
  ]
}
```

---

### 3.7 Get All Child Details

```
POST /get_all_child_details/
```

Retrieves detailed information for all children of the authenticated user.

**Request:**
```json
{
  "idToken": "eyJhbGci..."
}
```

**Response (200):**
```json
{
  "children": [
    {
      "child_id": "uuid-1",
      "name": "Emma",
      "age": 6,
      "grade": "Kindergarten",
      "created_at": "2026-07-15T10:30:00"
    }
  ]
}
```

---

## 4. Spelling Assessment APIs

### 4.1 Get Spelling Words

```
POST /grade/
```

Returns the word list for a given grade. Words include regular (phonics), nonsense, and sight words.

**Request:**
```json
{
  "grade": "Kindergarten"
}
```

**Grade values**: `"Kindergarten"`, `"First"`, `"Second"`, `"Third"`

**Response (200):**
```json
{
  "words": [
    {
      "word": "cat",
      "sentence": "The cat is black.",
      "type": "regular"
    },
    {
      "word": "flop",
      "sentence": "He did a flop.",
      "type": "nonsense"
    },
    {
      "word": "the",
      "sentence": "I see the dog.",
      "type": "sight"
    }
  ]
}
```

---

### 4.2 Submit Spelling Test

```
POST /submit_words/
```

Submits child's spelling responses, scores them, computes cognitive tags, and saves to Firebase.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First",
  "words": [
    {
      "word": "cat",
      "user_input": "kat",
      "type": "regular",
      "time": 5,
      "hints_used": 0
    }
  ]
}
```

**Response (200):**
```json
{
  "user_id": "firebase_uid",
  "child_id": "uuid-here",
  "results": [
    {
      "word": "cat",
      "user_input": "kat",
      "type": "regular",
      "points": 2,
      "max_points": 3,
      "mistakes": {"beginning": "Expected 'c', got 'k'"},
      "time": 5,
      "hints_used": 0
    }
  ],
  "analysis": [
    {
      "word": "cat",
      "user_input": "kat",
      "beginning_explanation": "Mistake in beginning: Expected 'c', got 'k'."
    }
  ],
  "evaluation": {
    "status": "pass",
    "score": 85,
    "max_score": 100
  },
  "assessment_summary": {
    "Phonics": {
      "score": 30,
      "max_score": 40,
      "percentage": 75.0
    },
    "Sight Words": {
      "score": 8,
      "max_score": 10,
      "percentage": 80.0
    }
  },
  "error_analysis": {
    "beginning_consonant": 2,
    "short_vowel": 1
  },
  "instructional_recommendation": "Focus on beginning consonants and short vowel sounds.",
  "dear_parent_tags": [
    {
      "id": "phonics_strength",
      "confidence": "high",
      "polarity": "strength",
      "description": "Child shows solid phonics decoding skills."
    }
  ],
  "per_word_tags": [
    {
      "word": "cat",
      "tags": ["beginning_consonant_error"]
    }
  ]
}
```

---

### 4.3 Generate Word Audio

```
POST /generate_text_audio/
```

Generates TTS audio for a single word. Audio is cached in Firebase.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "text": "cat"
}
```

**Response (200):**
```json
{
  "base64_audio": "base64_encoded_mp3_audio"
}
```

---

### 4.4 Generate All Grade Audio

```
POST /generate_all_grade_audio/
```

Returns all words with TTS audio for a grade. Audio is cached in Firebase and generated on-demand if missing.

**Request:**
```json
{
  "grade": "First"
}
```

**Response (200):**
```json
{
  "grade": "First",
  "audio_files": [
    {
      "word": "cat",
      "sentence": "The cat is black.",
      "word_audio": "base64_mp3",
      "sentence_audio": "base64_mp3"
    }
  ]
}
```

---

### 4.5 Get Spelling Complete Result

```
POST /complete_result/
```

Retrieves the latest spelling test result with detailed parent summary and teacher/admin breakdown.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First"
}
```

**Response (200):**
```json
{
  "user_id": "firebase_uid",
  "child_id": "uuid-here",
  "grade": "First",
  "parent_summary": {
    "overall_accuracy": 85.0,
    "phonics_score": 75.0,
    "sight_word_score": 80.0,
    "confidence": "High",
    "key_error_patterns": ["Beginning consonant", "Short vowel"],
    "strengths": ["Consonant digraph", "Long vowel pattern"],
    "focus_areas": ["Beginning consonant"],
    "recommendation": "Focus on beginning consonants and short vowel sounds.",
    "note": "Note: Placement is instructional and not a clinical diagnosis.",
    "grade_band": {
      "band": "First",
      "placement": "At Grade Level",
      "next_step": "Continue with current grade level practice"
    },
    "actions": [
      {"label": "Start Practice Pack", "type": "button", "action": "start_pack"},
      {"label": "Review Missed Words", "type": "button", "action": "review_missed"},
      {"label": "Download Report (PDF)", "type": "button", "action": "download_pdf"}
    ]
  },
  "dear_parent_tags": [...],
  "per_word_tags": [...],
  "teacher_admin_detail": {
    "test_level": "First",
    "words": 20,
    "correct": 17,
    "instructional_level": "First",
    "table_data": [...],
    "actions": [
      {"label": "Export CSV", "type": "button", "action": "export_csv"},
      {"label": "Copy JSON", "type": "button", "action": "copy_json"},
      {"label": "Send to Tutor", "type": "button", "action": "send_tutor"}
    ]
  }
}
```

**Errors:**
- `404`: No test results found

---

## 5. Logic Quest Assessment APIs

### 5.1 Get Logic Test

```
POST /logic/get_test/
```

Returns all logic assessment items for a given grade level.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "Kindergarten"
}
```

**Grade values**: `"K-1"`, `"1-2"`, `"2-3"`, `"3-4"` (or `"Kindergarten"`, `"First"`, `"Second"`, `"Third"`)

**Response (200):**
```json
{
  "success": true,
  "test_id": "uuid-generated",
  "grade": "Kindergarten",
  "total_items": 8,
  "instructions": "Solve each logic puzzle carefully. Think about patterns, relationships, and rules. Take your time and do your best!",
  "items": [
    {
      "item_id": "logic_k_1",
      "item_number": "K-1",
      "item_type": "categorization",
      "question_text": "Which one does NOT belong? Dog, Cat, Fish, Chair",
      "difficulty": "easy",
      "options": [
        {"index": 0, "text": "Dog", "image_url": null},
        {"index": 1, "text": "Cat", "image_url": null},
        {"index": 2, "text": "Fish", "image_url": null},
        {"index": 3, "text": "Chair", "image_url": null}
      ]
    }
  ]
}
```

---

### 5.2 Get Logic Test With Audio

```
POST /logic/get_test_with_audio/
```

Same as `/logic/get_test/` but includes TTS audio for each question and option. Audio is cached in Firebase under `logic_audio/{grade}/{item_id}`.

**Request:** Same as `/logic/get_test/`

**Response (200):**
```json
{
  "success": true,
  "test_id": "uuid-generated",
  "grade": "Kindergarten",
  "total_items": 8,
  "instructions": "Listen to each question carefully, then choose your answer...",
  "items": [
    {
      "item_id": "logic_k_1",
      "item_number": "K-1",
      "item_type": "categorization",
      "question_text": "Which one does NOT belong? Dog, Cat, Fish, Chair",
      "difficulty": "easy",
      "question_audio_base64": "base64_mp3",
      "audio_source": "cached",
      "options": [
        {"index": 0, "text": "Dog", "image_url": null, "audio_base64": "base64_mp3"},
        {"index": 1, "text": "Cat", "image_url": null, "audio_base64": "base64_mp3"},
        {"index": 2, "text": "Fish", "image_url": null, "audio_base64": "base64_mp3"},
        {"index": 3, "text": "Chair", "image_url": null, "audio_base64": "base64_mp3"}
      ]
    }
  ]
}
```

---

### 5.3 Submit Single Response

```
POST /logic/submit_response/
```

Submits a single item response for incremental scoring.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "item_id": "logic_k_1",
  "selected_answer_index": 3,
  "response_time_seconds": 15,
  "attempts": 1,
  "self_corrected": false,
  "explanation_provided": null,
  "post_shift_accuracy": null,
  "rule_inferred": null
}
```

**Response (200):**
```json
{
  "success": true,
  "is_correct": true,
  "correct_answer_index": 3,
  "primary_tag": "pattern_detection_strong",
  "difficulty": "easy"
}
```

---

### 5.4 Submit Complete Test

```
POST /logic/submit_test/
```

Submits all responses for a complete logic test. Computes scores, cognitive tags, dear parent tags, and saves to Firebase.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "Kindergarten",
  "responses": [
    {
      "item_id": "logic_k_1",
      "selected_answer_index": 3,
      "response_time_seconds": 15,
      "attempts": 1,
      "self_corrected": false
    }
  ]
}
```

**Response (200):**
```json
{
  "success": true,
  "score": "8/8",
  "percentage": 100.0,
  "correct_answers": 8,
  "total_items": 8,
  "level": "Exceptional Logical Thinker",
  "cognitive_tags": [
    "pattern_detection_emerging",
    "relational_reasoning_present",
    "systematic_problem_solving"
  ],
  "tag_outputs": [
    {
      "tag": "pattern_detection_emerging",
      "confidence": "high",
      "evidence": "pattern_score=3"
    }
  ],
  "tag_breakdown": {
    "pattern_detection_strong": 3,
    "relational_reasoning_present": 2,
    "systematic_problem_solving": 2,
    "reasoning_under_load_emerging": 1
  },
  "reasoning_under_load_detected": false,
  "trial_and_error_detected": false,
  "strategy_shift_difficulty_detected": false,
  "impulsive_response_detected": false,
  "self_correction_detected": false,
  "cognitive_flexibility_intact": false,
  "flexible_strategy_use_detected": true,
  "dear_parent_tags": [
    {
      "id": "pattern_detection_emerging",
      "confidence": "high",
      "polarity": "strength",
      "description": "Child shows early pattern recognition but not yet consistent across hard items."
    }
  ],
  "per_item_tags": [
    {
      "item_id": "logic_k_1",
      "answered": true,
      "is_correct": true,
      "tags": []
    }
  ],
  "score_id": "firebase_push_key",
  "message": "Test completed successfully"
}
```

**Performance Levels:**

| Percentage | Level |
|---|---|
| ≥ 90% | Exceptional Logical Thinker |
| ≥ 80% | Advanced Logical Thinker |
| ≥ 70% | Good Logical Thinker |
| ≥ 60% | Developing Logical Thinker |
| < 60% | Emerging Logical Thinker |

---

### 5.5 Get Complete Logic Result

```
POST /logic/complete_result/
```

Retrieves the latest logic test result with parent-friendly summary, strengths, areas to develop, and behavioral signals.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "Kindergarten"
}
```

**Response (200):**
```json
{
  "success": true,
  "student_id": "uuid-here",
  "test_id": "firebase_key",
  "grade": "Kindergarten",
  "test_timestamp": "2026-08-07T22:30:00",
  "summary": {
    "total_items": 8,
    "correct_answers": 8,
    "percentage": 100.0,
    "level": "Exceptional Logical Thinker",
    "cognitive_tags": ["pattern_detection_emerging", "relational_reasoning_present", "systematic_problem_solving"],
    "tag_breakdown": {"pattern_detection_strong": 3, "relational_reasoning_present": 2}
  },
  "parent_summary": {
    "overall_score": "8/8",
    "percentage": 100.0,
    "performance_level": "Exceptional Logical Thinker",
    "grade_placement": "Above Grade Level",
    "next_step": "Practice multi-step logic puzzles and pattern recognition",
    "strengths": [
      "Strong pattern recognition and detection",
      "Good relational reasoning abilities",
      "Systematic and methodical problem-solving"
    ],
    "areas_to_develop": ["Continue practicing logic puzzles"],
    "recommendation": "Excellent logical reasoning! Challenge your child with advanced puzzles and abstract thinking exercises.",
    "note": "This assessment is instructional and not a clinical diagnosis."
  },
  "dear_parent_tags": [...],
  "per_item_tags": [...],
  "behavioral_signals": {
    "reasoning_under_load": false,
    "trial_and_error": false,
    "strategy_shift_difficulty": false
  },
  "actions": [
    {"label": "Retry Test", "type": "button", "action": "retry_test"},
    {"label": "View Items", "type": "button", "action": "view_items"},
    {"label": "Download Report", "type": "button", "action": "download_pdf"}
  ]
}
```

**Errors:**
- `404`: No logic test results found for child

---

### 5.6 Logic Test Web UI

```
GET /logic/ui
```

Serves a static HTML page for the logic assessment web UI. No authentication required.

**Response**: HTML file (`logic_test_web.html`)

---

## 6. Speaking Assessment APIs

### 6.1 Get Single Sentence

```
POST /speaking/get_sentence/
```

Returns a random sentence for the speaking test with TTS audio.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First"
}
```

**Response (200):**
```json
{
  "grade": "First",
  "sentence_id": "s1",
  "sentence": "The sun is bright today.",
  "word_count": 5,
  "difficulty": "easy",
  "audio_base64": "base64_mp3",
  "instructions": "Listen to the sentence, then record yourself saying it clearly."
}
```

---

### 6.2 Get All Sentences

```
POST /speaking/get_all_sentences/
```

Returns all sentences for a grade with cached TTS audio. Generates missing audio in parallel.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First"
}
```

**Response (200):**
```json
{
  "grade": "First",
  "total_sentences": 5,
  "sentences": [
    {
      "sentence_id": "s1",
      "sentence": "The sun is bright today.",
      "word_count": 5,
      "difficulty": "easy",
      "audio_base64": "base64_mp3"
    }
  ]
}
```

---

### 6.3 Analyze Speech

```
POST /speaking/analyze/
```

Analyzes a child's speech recording using Whisper (transcription) and GPT-4o (evaluation).

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First",
  "original_sentence": "The sun is bright today.",
  "audio_base64": "base64_encoded_audio",
  "audio_format": "mp3"
}
```

**Response (200):**
```json
{
  "original_sentence": "The sun is bright today.",
  "transcribed_text": "The sun is bright today.",
  "duration_seconds": 3.5,
  "word_timestamps": [
    {"word": "The", "start": 0.0, "end": 0.3},
    {"word": "sun", "start": 0.3, "end": 0.6}
  ],
  "analysis_method": "openai_gpt4",
  "pronunciation": {
    "score": 85,
    "errors": [{"word": "bright", "issue": "vowel sound", "correction": "..."}]
  },
  "speaking_rate": {
    "wpm": 120,
    "status": "normal"
  },
  "fluency": {
    "score": 80,
    "pauses": 2
  },
  "grammar": {
    "score": 90,
    "errors": []
  },
  "overall": {
    "score": 85,
    "status": "Good",
    "level": "Good Speaker",
    "recommendation": "Keep practicing!",
    "parent_tip": "Encourage your child to speak slowly and clearly."
  },
  "recommendation": "Keep practicing!",
  "parent_tip": "Encourage your child to speak slowly and clearly."
}
```

**Errors:**
- `500`: Transcription failed or speech analysis failed

---

### 6.4 Submit Speaking Test

```
POST /speaking/submit/
```

Submits all speaking responses for a grade. Transcribes and analyzes each recording, computes scores and cognitive tags, saves to Firebase.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First",
  "submissions": [
    {
      "sentence_id": "s1",
      "original_sentence": "The sun is bright today.",
      "audio_base64": "base64_audio",
      "audio_format": "mp3"
    }
  ]
}
```

**Response (200):**
```json
{
  "success": true,
  "user_id": "firebase_uid",
  "child_id": "uuid-here",
  "grade": "First",
  "test_id": "firebase_push_key",
  "total_marks": 500,
  "user_score": 420.0,
  "answered_count": 5,
  "average_score": 84.0,
  "percentage": 84.0,
  "level": "Good Speaker",
  "results": [
    {
      "sentence_id": "s1",
      "original_sentence": "The sun is bright today.",
      "transcribed_text": "The sun is bright today.",
      "duration_seconds": 3.5,
      "pronunciation": {...},
      "speaking_rate": {...},
      "fluency": {...},
      "grammar": {...},
      "overall": {"score": 85, "status": "Answered", "level": "Good Speaker"},
      "recommendation": "...",
      "analysis_method": "openai_gpt4",
      "status": "Answered"
    }
  ],
  "dear_parent_tags": [...],
  "per_sentence_tags": [...],
  "message": "Submission completed: 5 answered, 0 not attempted."
}
```

**Speaking Performance Levels:**

| Percentage | Level |
|---|---|
| ≥ 90% | Excellent Speaker |
| ≥ 75% | Good Speaker |
| ≥ 50% | Developing Speaker |
| < 50% | Needs Improvement |

---

### 6.5 Get Speaking Complete Result

```
POST /speaking/complete_result/
```

Retrieves the latest speaking test result with parent summary.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First"
}
```

**Response (200):**
```json
{
  "user_id": "firebase_uid",
  "child_id": "uuid-here",
  "grade": "First",
  "total_marks": 500,
  "user_score": 420.0,
  "answered_count": 5,
  "average_score": 84.0,
  "percentage": 84.0,
  "level": "Good Speaker",
  "parent_summary": {
    "level": "Good Speaker",
    "recommendation": "See detailed feedback for each sentence.",
    "grade_placement": "At Grade Level",
    "note": "Assessment is instructional and not a clinical diagnosis."
  },
  "dear_parent_tags": [...],
  "per_sentence_tags": [...],
  "all_results": [...]
}
```

**Errors:**
- `404`: No speaking test results found

---

## 7. Reading Comprehension APIs

### 7.1 Get Stories

```
POST /comprehension/get_stories/
```

Returns 2 stories with audio narration and questions for a given grade. Correct answers are NOT sent to the client.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First"
}
```

**Response (200):**
```json
{
  "grade": "First",
  "total_stories": 2,
  "total_questions": 8,
  "instructions": "Listen to each story carefully, then answer the questions. Each question has 4 options.",
  "stories": [
    {
      "story_id": "story1",
      "title": "The Lost Puppy",
      "story_text": "Once upon a time, there was a puppy named Max...",
      "story_audio_base64": "base64_mp3",
      "audio_source": "cached_openai",
      "duration_estimate": "60 seconds",
      "questions": [
        {
          "id": "q1",
          "question": "What happened to the puppy?",
          "options": ["He got lost", "He found a bone", "He went to sleep", "He met a cat"]
        }
      ],
      "total_questions": 4
    }
  ]
}
```

---

### 7.2 Submit Comprehension Test

```
POST /comprehension/submit/
```

Submits answers for the reading comprehension test. Scores, computes cognitive tags, and saves to Firebase.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First",
  "story_answers": [
    {
      "story_id": "story1",
      "answers": [
        {"question_id": "q1", "selected_index": 0}
      ]
    }
  ]
}
```

**Response (200):**
```json
{
  "success": true,
  "user_id": "firebase_uid",
  "child_id": "uuid-here",
  "grade": "First",
  "test_id": "firebase_push_key",
  "total_questions": 8,
  "correct_answers": 6,
  "score": 6,
  "max_score": 8,
  "percentage": 75.0,
  "level": "Good Reader",
  "status": "At",
  "recommendation": "Good understanding of the stories. Continue practicing with varied reading materials.",
  "results": [
    {
      "story_id": "story1",
      "story_title": "The Lost Puppy",
      "questions": [
        {
          "question_id": "q1",
          "question": "What happened to the puppy?",
          "selected_index": 0,
          "selected_answer": "He got lost",
          "correct_index": 0,
          "correct_answer": "He got lost",
          "is_correct": true
        }
      ]
    }
  ],
  "dear_parent_tags": [...],
  "per_question_tags": [...],
  "message": "Test completed: 6/8 correct (75.0%)"
}
```

**Comprehension Performance Levels:**

| Percentage | Level | Status |
|---|---|---|
| ≥ 90% | Excellent Reader | Above |
| ≥ 75% | Good Reader | At |
| ≥ 50% | Developing Reader | Below |
| < 50% | Needs Practice | Below |

---

### 7.3 Get Comprehension Complete Result

```
POST /comprehension/complete_result/
```

Retrieves the latest comprehension test result with story-level breakdown.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "grade": "First"
}
```

**Response (200):**
```json
{
  "user_id": "firebase_uid",
  "child_id": "uuid-here",
  "grade": "First",
  "test_timestamp": "2026-08-07T22:30:00",
  "summary": {
    "total_questions": 8,
    "correct_answers": 6,
    "percentage": 75.0,
    "level": "Good Reader",
    "status": "At"
  },
  "parent_summary": {
    "overall_score": "6/8",
    "percentage": 75.0,
    "level": "Good Reader",
    "grade_placement": "At Grade Level",
    "next_step": "Continue with current grade level materials",
    "recommendation": "Good understanding of the stories...",
    "note": "Assessment is instructional and not a clinical diagnosis."
  },
  "story_breakdown": [
    {
      "story_id": "story1",
      "story_title": "The Lost Puppy",
      "correct": 3,
      "total": 4,
      "percentage": 75.0,
      "questions": [...]
    }
  ],
  "dear_parent_tags": [...],
  "per_question_tags": [...],
  "actions": [
    {"label": "Retry Test", "type": "button", "action": "retry_test"},
    {"label": "View Stories", "type": "button", "action": "view_stories"},
    {"label": "Download Report (PDF)", "type": "button", "action": "download_pdf"}
  ]
}
```

**Errors:**
- `404`: No comprehension test results found

---

## 8. Feedback API

### 8.1 Submit Feedback

```
POST /feedback/
```

Submits parent feedback survey responses.

**Request:**
```json
{
  "idToken": "eyJhbGci...",
  "child_id": "uuid-here",
  "q1_grade": "First",
  "q2_prior_assessments": "Yes, school assessments",
  "q3_spelling_confidence": "Moderately confident",
  "q4_assessment_length": "Just right",
  "q5_difficulty_level": "Appropriate",
  "q6_engagement_level": "Very engaged",
  "q7_technical_issues": "No issues",
  "q8_results_clarity": "Very clear",
  "q9_recommendations_helpful": "Very helpful",
  "q10_information_amount": "Just right",
  "q11_overall_satisfaction": "Very satisfied",
  "q12_comments": "Great tool!"
}
```

**Response (200):**
```json
{
  "message": "Feedback saved successfully",
  "feedback_id": "uuid-generated",
  "saved_under": "parent_feedback",
  "email": "parent@example.com",
  "timestamp": "2026-08-07T22:30:00Z"
}
```

---

## 9. Admin APIs

All admin endpoints require a Firebase ID token from a user with `isAdmin: true` in the Firebase Realtime Database.

### 9.1 Make Admin

```
POST /admin/make-admin/
```

Promotes a user to admin by email address.

**Request:**
```json
{
  "idToken": "admin_idToken",
  "targetEmail": "newadmin@example.com"
}
```

**Response (200):**
```json
{
  "message": "User newadmin@example.com is now an admin",
  "updated": true,
  "targetUid": "firebase_uid"
}
```

**Errors:**
- `403`: Only admins can promote users
- `404`: Target user not found

---

### 9.2 Admin Stats

```
POST /admin/stats/
```

Returns total user count and user list with join dates.

**Request:**
```json
{
  "idToken": "admin_idToken"
}
```

**Response (200):**
```json
{
  "isAdmin": true,
  "totalUsers": 42,
  "users": [
    {"email": "parent@example.com", "joinedDate": "2026-07-15 10:30"}
  ]
}
```

If caller is not admin:
```json
{
  "isAdmin": false,
  "totalUsers": 0,
  "users": []
}
```

---

### 9.3 Get All Feedback

```
POST /admin/feedback/
```

Returns all parent feedback submissions.

**Request:**
```json
{
  "idToken": "admin_idToken"
}
```

**Response (200):**
```json
{
  "count": 15,
  "feedbacks": [
    {
      "user_id": "...",
      "email": "...",
      "child_id": "...",
      "answers": {
        "What grade is your child currently in?": "First",
        "Overall, how satisfied are you with this spelling assessment?": "Very satisfied"
      },
      "timestamp": "2026-08-07T22:30:00Z"
    }
  ]
}
```

---

### 9.4 Pre-generate Logic Audio

```
POST /admin/pregenerate_logic_audio/
```

Pre-generates TTS audio for all logic test items and caches in Firebase. Call once after deploying new items.

**Request:**
```json
{
  "idToken": "admin_idToken"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Logic audio pre-generation complete",
  "results": {
    "generated": ["K-1/logic_k_1", "K-1/logic_k_2"],
    "failed": [],
    "skipped": ["K-1/logic_k_3"]
  }
}
```

---

### 9.5 Pre-generate Speaking Audio

```
POST /admin/pregenerate_speaking_audio/
```

Pre-generates TTS audio for all speaking test sentences.

**Request:**
```json
{
  "idToken": "admin_idToken"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Speaking audio pre-generation complete",
  "results": {
    "generated": [...],
    "failed": [],
    "skipped": [...]
  }
}
```

---

### 9.6 Pre-generate Spelling Audio

```
POST /admin/pregenerate_spelling_audio/
```

Pre-generates TTS audio for all spelling words and sentences.

**Request:**
```json
{
  "idToken": "admin_idToken"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Spelling audio pre-generation complete",
  "results": {
    "generated": [...],
    "failed": [],
    "skipped": [...]
  }
}
```

---

### 9.7 Pre-generate Story Audio

```
POST /admin/pregenerate_story_audio/
```

Pre-generates TTS audio for all reading comprehension stories.

**Request:**
```json
{
  "idToken": "admin_idToken"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Audio pre-generation complete",
  "results": {
    "generated": [...],
    "failed": [],
    "skipped": [...]
  }
}
```

---

### 9.8 Regenerate Story Audio

```
POST /admin/regenerate_story_audio/
```

Regenerates audio for specific stories or all stories. Optionally filter by grade and story_id.

**Request:**
```json
{
  "idToken": "admin_idToken",
  "grade": "First",
  "story_id": "story1"
}
```

**Response (200):**
```json
{
  "success": true,
  "results": {
    "regenerated": ["First/story1"],
    "failed": []
  }
}
```

---

## 10. Cognitive Tagging System

### Overview

The Dear Parent tagging engine (`tagging_engine.py`) derives cognitive signals from raw assessment responses and evaluates trigger conditions (defined in `dear_parent_tags_config.json`) to emit cognitive tags.

### Architecture

```
Student Responses
       ↓
┌──────────────────┐
│ derive_*_signals │  ← Extracts signals (scores, counts, patterns)
└──────┬───────────┘
       ↓
┌──────────────────┐
│ _evaluate_trigger│  ← Checks trigger conditions from config
└──────┬───────────┘
       ↓
┌──────────────────┐
│   emit_tags      │  ← Produces final tag outputs
└──────────────────┘
       ↓
Cognitive Tags + Per-Item Tags
```

### Tagger Functions

| Assessment | Test Tagger | Per-Item Tagger |
|---|---|---|
| Logic Quest | `tag_logic_test()` | `tag_logic_per_item()` |
| Spelling | `tag_spelling_test()` | `tag_spelling_per_word()` |
| Speaking | `tag_speaking_test()` | `tag_speaking_per_sentence()` |
| Comprehension | `tag_comprehension_test()` | `tag_comprehension_per_question()` |

### Cognitive Tags

| Tag | Type | Description |
|---|---|---|
| `pattern_detection_strong` | Strength | Child quickly and consistently identifies recurring patterns |
| `pattern_detection_emerging` | Strength | Child shows early pattern recognition |
| `relational_reasoning_present` | Strength | Child connects ideas and understands relationships |
| `systematic_problem_solving` | Strength | Child uses structured, step-by-step approaches |
| `cognitive_flexibility_intact` | Strength | Child shifts strategy when rules change |
| `flexible_strategy_use` | Strength | Child adapts approach when strategy isn't working |
| `self_correction_present` | Strength | Child catches and fixes own mistakes |
| `reasoning_under_load_emerging` | Growth Edge | Child shows emerging ability to hold multiple ideas |
| `trial_and_error_strategy` | Growth Edge | Child uses trial-and-error rather than planning |
| `strategy_shift_difficulty` | Growth Edge | Child persists with one approach even when ineffective |
| `impulsive_response` | Growth Edge | Child answers quickly without sufficient reflection |
| `rule_maintenance_difficulty` | Growth Edge | Child finds it hard to apply rules consistently |

### Logic Quest Signal Derivation

The `derive_logic_signals()` function processes each response and calculates:

| Signal | Description |
|---|---|
| `pattern_score` | Correct answers on pattern-detection items |
| `pattern_hard_count` | Correct hard pattern items |
| `relational_score` | Correct answers on relational reasoning items |
| `systematic_score` | Correct answers on systematic problem-solving items |
| `flexibility_score` | Correct answers on flexible strategy items |
| `load_success_count` | Correct answers on reasoning-under-load items |
| `load_fails` | Wrong or slow answers on load items |
| `rule_maintenance_fails` | Two-step items where child couldn't apply first rule |
| `shift_result` | Sort task post-shift accuracy: `shifted_ok`, `stuck`, `no_sort` |
| `rule_inferred` | Whether child inferred hidden rule in grade 3-4 sort task |
| `multiple_attempts_count` | Items requiring multiple attempts |
| `fast_and_wrong_count` | Items answered quickly but incorrectly |
| `self_corrected_to_right_count` | Items where child self-corrected to correct answer |

### Logic Quest Trigger Conditions

| Tag | Trigger | Confidence |
|---|---|---|
| `pattern_detection_strong` | `pattern_score >= 3 AND pattern_hard_count >= 1` | high |
| `pattern_detection_emerging` | `pattern_score >= 2` | high |
| `relational_reasoning_present` | `relational_score >= 2` | high |
| `systematic_problem_solving` | `systematic_score >= 2` | high |
| `cognitive_flexibility_intact` | `shift_result == shifted_ok` | medium |
| `flexible_strategy_use` | `rule_inferred == true OR flexibility_score >= 2` | medium |
| `reasoning_under_load_emerging` | `load_fails >= 2 OR load_success_count >= 2` | high |
| `strategy_shift_difficulty` | `shift_result == stuck` | medium |
| `rule_maintenance_difficulty` | `rule_maintenance_fails >= 1` | medium |
| `trial_and_error_strategy` | `multiple_attempts_count >= 3` | medium |
| `impulsive_response` | `fast_and_wrong_count >= 2` | medium |
| `self_correction_present` | `self_corrected_to_right_count >= 1` | medium |

### Item Type Groups

| Group | Item Types |
|---|---|
| pattern | `pattern`, `pattern_rule_id`, `meta_categorization` |
| relational | `analogy`, `odd_one_out`, `categorization`, `comparison`, `double_analogy`, `syllogism` |
| multistep | `rule_application`, `conditional_logic`, `transitive_reasoning`, `multi_step_quantity`, `two_step`, `sequencing`, `order_of_operations`, `combining`, `rule_boundary`, `dual_rule_arithmetic`, `strategic_search` |
| flexibility | `strategy`, `dual_rule`, `dual_condition`, `meta_strategy` |
| load | `two_attribute_selection`, `negation_two_attribute`, `multi_step_quantity`, `two_step`, `comparison`, `transitive_reasoning` |

---

## 11. Logic Quest Question Bank

### Overview

32 questions total — 8 per grade (K through 3rd). Each question maps to exactly one cognitive tag.

### Kindergarten (Ages 5–6)

| # | Question | Correct | Cognitive Tag | Difficulty |
|---|---|---|---|---|
| K-1 | Which one does NOT belong? Dog, Cat, Fish, Chair | D) Chair | `pattern_detection_strong` | easy |
| K-2 | What comes next? Circle, Square, Circle, Square, Circle, ___ | B) Square | `pattern_detection_strong` | easy |
| K-3 | A hat goes on your head. A shoe goes on your foot. Where does a glove go? | B) Your hand | `relational_reasoning_present` | easy |
| K-4 | Ravi has 3 red blocks and 2 blue blocks. How many blocks total? | C) 5 | `systematic_problem_solving` | easy |
| K-5 | What is the odd one out? Apple, Banana, Carrot, Grapes? | C) Carrot | `pattern_detection_strong` | easy |
| K-6 | A bird can fly. A fish can swim. What can a frog do? | C) Jump | `relational_reasoning_present` | easy |
| K-7 | Which one is the biggest? Ant, dog, horse, cat? | C) A horse | `reasoning_under_load_emerging` | medium |
| K-8 | If today is sunny, wear sunglasses. If rainy, wear raincoat. Today is rainy. What do you wear? | B) A raincoat | `systematic_problem_solving` | medium |

**Tag coverage**: Pattern Recognition 3, Relational Reasoning 2, Systematic Problem Solving 2, Reasoning Under Load 1

### 1st Grade (Ages 6–7)

| # | Question | Correct | Cognitive Tag | Difficulty |
|---|---|---|---|---|
| 1-1 | What comes next? 2, 4, 6, 8, ___ | B) 10 | `pattern_detection_strong` | easy |
| 1-2 | Hot is to cold as big is to ___ | B) Small | `relational_reasoning_present` | easy |
| 1-3 | Mia sorted toys: Group 1 (ball, marble, orange), Group 2 (book, box, block). What rule? | C) Shape (round vs not round) | `systematic_problem_solving` | medium |
| 1-4 | What comes next? Triangle, Triangle, Circle, Triangle, Triangle, Circle, ___ | C) Triangle | `pattern_detection_strong` | medium |
| 1-5 | A puppy grows into a dog. A kitten grows into a cat. A calf grows into a ___ | B) Cow | `relational_reasoning_present` | medium |
| 1-6 | Leo tried to build a tower with round balls. It kept falling. What should he try? | B) Use flat blocks | `flexible_strategy_use` | medium |
| 1-7 | 3 birds on a fence. 2 more land. Then 1 flies away. How many birds? | B) 4 | `reasoning_under_load_emerging` | medium |
| 1-8 | Every animal with wings can fly. A penguin has wings. Can it fly in this game? | A) Yes, because it has wings | `systematic_problem_solving` | medium |

**Tag coverage**: Pattern Recognition 2, Relational Reasoning 2, Systematic Problem Solving 2, Cognitive Flexibility 1, Reasoning Under Load 1

### 2nd Grade (Ages 7–8)

| # | Question | Correct | Cognitive Tag | Difficulty |
|---|---|---|---|---|
| 2-1 | What number comes next? 3, 6, 9, 12, ___ | C) 15 | `pattern_detection_strong` | medium |
| 2-2 | Shoe is to foot as glove is to ___. Hat is to head as belt is to ___ | A) Hand, Waist | `relational_reasoning_present` | medium |
| 2-3 | Priya is taller than Sam. Sam is taller than Leo. Who is the shortest? | C) Leo | `reasoning_under_load_emerging` | hard |
| 2-4 | Animals with 4 legs → red pen, 2 legs → blue pen. Spider has 8 legs. What happens? | D) It doesn't fit either pen | `systematic_problem_solving` | hard |
| 2-5 | Look at this pattern: AB, CD, EF, GH, ___ | B) IJ | `pattern_detection_strong` | medium |
| 2-6 | Zara tried to cross a stream by jumping. She couldn't reach. What should she try? | B) Look for stepping stones or a log | `flexible_strategy_use` | medium |
| 2-7 | Red shapes = 2 pts, blue = 3 pts. You pick 2 red + 1 blue. How many points? | C) 7 | `reasoning_under_load_emerging` | hard |
| 2-8 | Wheels → garage, wings → hangar. Toy plane has both. Where does it go? | C) Both places | `flexible_strategy_use` | hard |

**Tag coverage**: Pattern Recognition 2, Relational Reasoning 1, Reasoning Under Load 2, Systematic Problem Solving 1, Cognitive Flexibility 2

### 3rd Grade (Ages 8–9)

| # | Question | Correct | Cognitive Tag | Difficulty |
|---|---|---|---|---|
| 3-1 | Look at this pattern: 2, 6, 18, 54, ___ | C) 162 | `pattern_detection_strong` | hard |
| 3-2 | Maya > Kai > Priya > Jude (age). Who is the second youngest? | C) Priya | `reasoning_under_load_emerging` | hard |
| 3-3 | Every blooper is a floop. Every floop is a zang. Is every blooper a zang? | A) Yes, definitely | `relational_reasoning_present` | hard |
| 3-4 | Star per 3 correct, lose star per 2 wrong. 9 right, 4 wrong. How many stars? | A) 1 | `systematic_problem_solving` | hard |
| 3-5 | Which group breaks its own rule? (pets, flowers, colours, instruments) | C) Red, Blue, Banana | `pattern_detection_strong` | hard |
| 3-6 | Dictionary: page 200 = "monkey", looking for "planet". What should you do? | A) Go forward a lot of pages | `systematic_problem_solving` | hard |
| 3-7 | If it rains → umbrella. If cold → jacket. Today raining AND cold. What do you do? | C) Bring umbrella and wear jacket | `flexible_strategy_use` | hard |
| 3-8 | Aisha tried 2 ways and got stuck. Friend says "try combining both." What should she do? | C) Use parts of both approaches together | `flexible_strategy_use` | hard |

**Tag coverage**: Pattern Recognition 2, Reasoning Under Load 1, Relational Reasoning 1, Systematic Problem Solving 2, Cognitive Flexibility 2

---

## 12. Data Models

### CognitiveTag (Enum)

```python
class CognitiveTag(str, Enum):
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
```

### GradeLevel (Enum)

```python
class GradeLevel(str, Enum):
    KINDERGARTEN_1 = "K-1"
    GRADE_1_2 = "1-2"
    GRADE_2_3 = "2-3"
    GRADE_3_4 = "3-4"
```

### LogicItem

```python
class LogicItem(BaseModel):
    item_id: str
    grade_level: GradeLevel
    item_number: str          # e.g., "K-1", "1-2"
    item_type: str            # "pattern", "analogy", "categorization", etc.
    question_text: str
    options: List[LogicOption]
    correct_answer_index: int
    expected_latency_seconds: int = 30
    primary_tag: CognitiveTag
    conditional_tags: Dict[str, CognitiveTag] = {}
    sort_config: Optional[SortTaskConfig] = None
    difficulty: str = "medium"  # "easy", "medium", "hard"
```

### LogicOption

```python
class LogicOption(BaseModel):
    index: int
    text: str
    image_url: Optional[str] = None
```

### StudentResponse

```python
class StudentResponse(BaseModel):
    student_id: str
    item_id: str
    selected_answer_index: int
    response_time_seconds: int
    attempts: int = 1
    self_corrected: bool = False
    explanation_provided: Optional[str] = None
    post_shift_accuracy: Optional[str] = None  # "correct"/"incorrect" for sort tasks
    rule_inferred: Optional[bool] = None       # grade 3-4 sort only
```

---

## 13. Firebase Database Schema

```
users/
  {uid}/
    name: string
    email: string
    isAdmin: boolean (optional)
    createdAt: timestamp
    children/
      {child_id}/
        name: string
        age: int
        grade: string
        created_at: ISO timestamp
        scores/                    # Spelling test results
          {score_id}/
            grade: string
            evaluation: {...}
            assessment_summary: {...}
            error_analysis: {...}
            instructional_recommendation: string
            dear_parent_tags: [...]
            per_word_tags: [...]
            results: [...]
            analysis: [...]
            timestamp: ISO timestamp
        logic_tests/               # Logic Quest results
          {score_id}/
            grade: string
            score: string
            percentage: float
            correct_answers: int
            total_items: int
            level: string
            cognitive_tags: [...]
            tag_outputs: [...]
            tag_breakdown: {...}
            dear_parent_tags: [...]
            per_item_tags: [...]
            responses: [...]
            timestamp: ISO timestamp
        speaking_tests/            # Speaking test results
          {test_id}/
            grade: string
            results: [...]
            total_marks: int
            user_score: float
            answered_count: int
            average_score: float
            percentage: float
            level: string
            dear_parent_tags: [...]
            per_sentence_tags: [...]
            timestamp: ISO timestamp
        comprehension_tests/       # Reading comprehension results
          {test_id}/
            grade: string
            results: [...]
            total_questions: int
            correct_answers: int
            percentage: float
            level: string
            status: string
            recommendation: string
            dear_parent_tags: [...]
            per_question_tags: [...]
            timestamp: ISO timestamp

# Audio caches
logic_audio/{grade}/{item_id}/
  question_audio: base64
  option_audios: [base64, ...]
  voice: string
  generated_at: ISO timestamp

speaking_audio/{grade}/{sentence_id}/
  audio_base64: base64
  voice: string
  generated_at: ISO timestamp

spelling_audio/{grade}/{word}/
  word_audio: base64
  sentence_audio: base64
  voice: string
  generated_at: ISO timestamp

story_audio/{grade}/{story_id}/
  audio_base64: base64
  title: string
  voice: string
  generated_at: ISO timestamp

# Feedback
parent_feedback/{feedback_id}/
  user_id: string
  email: string
  child_id: string
  answers: {...}
  timestamp: ISO timestamp
```

---

## 14. Deployment

### Docker Build

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Deployment Steps

1. **ECR Login**:
```bash
aws ecr get-login-password --region us-east-1 --profile mynewprofile | docker login --username AWS --password-stdin 577999459562.dkr.ecr.us-east-1.amazonaws.com
```

2. **Build Image**:
```bash
docker build -t fastapi-app11:latest .
```

3. **Tag Image**:
```bash
docker tag fastapi-app11:latest 577999459562.dkr.ecr.us-east-1.amazonaws.com/fastapi-app11:latest
```

4. **Push to ECR**:
```bash
docker push 577999459562.dkr.ecr.us-east-1.amazonaws.com/fastapi-app11:latest
```

5. **Trigger App Runner Deployment**:
```bash
aws apprunner start-deployment --region us-east-1 --profile mynewprofile --service-arn arn:aws:apprunner:us-east-1:577999459562:service/fastapi-service/b0891380abd14a2f91cd78e88a710d60
```

6. **Check Deployment Status**:
```bash
aws apprunner describe-service --region us-east-1 --profile mynewprofile --service-arn arn:aws:apprunner:us-east-1:577999459562:service/fastapi-service/b0891380abd14a2f91cd78e88a710d60
```

### Environment Variables (.env)

| Variable | Description |
|---|---|
| `FIREBASE_API_KEY` | Firebase Web API Key |
| `FIREBASE_DB_URL` | Firebase Realtime Database URL |
| `FIREBASE_CRED_BASE64` | Base64-encoded Firebase service account credentials |
| `OPENAI_API_KEY` | OpenAI API key for TTS + Whisper + GPT-4o |
| `AWS_ACCESS_KEY_ID` | AWS access key for Polly |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key for Polly |
| `AWS_REGION` | AWS region (default: `us-east-1`) |

### Post-Deployment

After deploying new questions or audio content, call the admin pre-generation endpoints:
1. `POST /admin/pregenerate_logic_audio/` — cache logic question audio
2. `POST /admin/pregenerate_speaking_audio/` — cache speaking sentence audio
3. `POST /admin/pregenerate_spelling_audio/` — cache spelling word audio
4. `POST /admin/pregenerate_story_audio/` — cache comprehension story audio

---

## 15. Security Notes

### Token Verification

- **Protected endpoints** verify Firebase ID tokens via `auth.verify_id_token()` or `verify_child_and_token()`
- Tokens are passed in the **request body** (not headers)
- Token expiration: 1 hour (use refresh token to renew)

### Endpoints Without Token Verification

The following endpoints do **not** verify Firebase ID tokens:

| Endpoint | Risk |
|---|---|
| `POST /grade/` | Returns word list for any grade — low risk (public data) |
| `POST /generate_all_grade_audio/` | Returns audio for any grade — low risk (public data) |
| `GET /logic/ui` | Serves static HTML — no risk |
| `POST /register/` | Creates account — by design (no token yet) |
| `POST /login` | Authenticates — by design (no token yet) |

### Recommendations

- Consider adding token verification to `/grade/` and `/generate_all_grade_audio/` if word lists or audio should be access-controlled
- Correct answers for comprehension questions are NOT sent to the client (only returned after submission)
- Logic Quest items DO include `correct_answer_index` in the response — consider removing if client-side cheating is a concern

---

## Appendix: API Quick Reference

| # | Method | Endpoint | Auth | Purpose |
|---|---|---|---|---|
| 1 | POST | `/register/` | None | Create user account |
| 2 | POST | `/login` | None | Authenticate user |
| 3 | POST | `/save-user-data/` | Token | Save user profile |
| 4 | POST | `/user-details/` | Token | Get user details |
| 5 | POST | `/add_child/` | Token | Create child profile |
| 6 | POST | `/get_children/` | Token | List children |
| 7 | POST | `/get_all_child_details/` | Token | Get all child details |
| 8 | POST | `/grade/` | None | Get spelling words |
| 9 | POST | `/submit_words/` | Token | Submit spelling test |
| 10 | POST | `/generate_text_audio/` | Token | Get word audio |
| 11 | POST | `/generate_all_grade_audio/` | None | Get all grade audio |
| 12 | POST | `/complete_result/` | Token | Get spelling results |
| 13 | POST | `/logic/get_test/` | Token+Child | Get logic test |
| 14 | POST | `/logic/get_test_with_audio/` | Token+Child | Get logic test with audio |
| 15 | POST | `/logic/submit_response/` | Token+Child | Submit single response |
| 16 | POST | `/logic/submit_test/` | Token+Child | Submit complete test |
| 17 | POST | `/logic/complete_result/` | Token+Child | Get logic results |
| 18 | GET | `/logic/ui` | None | Web UI |
| 19 | POST | `/speaking/get_sentence/` | Token | Get speaking sentence |
| 20 | POST | `/speaking/get_all_sentences/` | Token | Get all sentences |
| 21 | POST | `/speaking/analyze/` | Token | Analyze speech |
| 22 | POST | `/speaking/submit/` | Token | Submit speaking test |
| 23 | POST | `/speaking/complete_result/` | Token | Get speaking results |
| 24 | POST | `/comprehension/get_stories/` | Token | Get stories + questions |
| 25 | POST | `/comprehension/submit/` | Token | Submit comprehension test |
| 26 | POST | `/comprehension/complete_result/` | Token | Get comprehension results |
| 27 | POST | `/feedback/` | Token | Submit parent feedback |
| 28 | POST | `/admin/make-admin/` | Admin | Promote user to admin |
| 29 | POST | `/admin/stats/` | Admin | Get user statistics |
| 30 | POST | `/admin/feedback/` | Admin | Get all feedback |
| 31 | POST | `/admin/pregenerate_logic_audio/` | Admin | Cache logic audio |
| 32 | POST | `/admin/pregenerate_speaking_audio/` | Admin | Cache speaking audio |
| 33 | POST | `/admin/pregenerate_spelling_audio/` | Admin | Cache spelling audio |
| 34 | POST | `/admin/pregenerate_story_audio/` | Admin | Cache story audio |
| 35 | POST | `/admin/regenerate_story_audio/` | Admin | Regenerate story audio |

---

*This documentation is auto-generated from source code analysis. Last updated: August 2026.*
