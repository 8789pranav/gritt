
# Speaking Test API Documentation (v2)

This document describes the endpoints, payloads, and responses for the Speaking Test APIs, including the new scoring logic (percentage-based, consistent for all grades/users).

---

## 1. /speaking/get_all_sentences/
**Purpose:** Get all sentences for a speaking test (with audio) for a given grade and child.

**Method:** POST

**Request Payload:**
```
{
  "idToken": "<Firebase ID token>",
  "child_id": "<child_id>",
  "grade": "Kindergarten" | "First" | "Second" | "Third"
}
```

**Response:**
```
{
  "grade": "Kindergarten",
  "total_sentences": 8,
  "sentences": [
    {
      "sentence_id": "abc123",
      "sentence": "The cat sat on the mat.",
      "word_count": 6,
      "difficulty": "easy",
      "audio_base64": "..."
    },
    ...
  ]
}
```

---

## 2. /speaking/submit/
**Purpose:** Submit all answers (audio or blank) for a speaking test in one batch.

**Method:** POST

**Request Payload:**
```
{
  "idToken": "<Firebase ID token>",
  "child_id": "<child_id>",
  "grade": "Kindergarten" | "First" | "Second" | "Third",
  "submissions": [
    {
      "sentence_id": "abc123",
      "original_sentence": "The cat sat on the mat.",
      "audio_base64": "...",   // base64-encoded audio, or blank if not attempted
      "audio_format": "mp3"     // or "wav"
    },
    ...
  ]
}
```

**Response:**
```
{
  "success": true,
  "user_id": "...",
  "child_id": "...",
  "grade": "Kindergarten",
  "test_id": "...",
  "total_submitted": 8,
  "answered_count": 5,
  "average_score": 62.5,           // average per sentence (0-100)
  "total_marks": 800,              // number_of_sentences * 100 (e.g., 8*100)
  "user_score": 500,               // sum of all sentence scores (0-100 each)
  "percentage": 62.5,              // (user_score / total_marks) * 100
  "level": "Good Speaker",        // Based on percentage (see below)
  "results": [
    {
      "sentence_id": "abc123",
      "original_sentence": "The cat sat on the mat.",
      "transcribed_text": "The cat sat on the mat.",
      "duration_seconds": 3.2,
      "pronunciation": { ... },
      "speaking_rate": { ... },
      "fluency": { ... },
      "grammar": { ... },
      "overall": { "score": 92.5, "status": "Above", ... },
      "recommendation": "...",
      "analysis_method": "openai_gpt4",
      "status": "Answered"
    },
    {
      "sentence_id": "def456",
      "original_sentence": "I like to run and hop.",
      "transcribed_text": "",
      "duration_seconds": 0,
      "pronunciation": {},
      "speaking_rate": {},
      "fluency": {},
      "grammar": {},
      "overall": { "score": 0, "status": "Not Attempted", ... },
      "recommendation": "Not attempted.",
      "analysis_method": "",
      "status": "Not Attempted"
    },
    ...
  ],
  "message": "Submission completed: 5 answered, 3 not attempted."
}
```

---


## 3. /speaking/complete_result/
**Purpose:** Get the complete result for the latest speaking test (all sentences, total score, explanations, percentage, and level).

**Method:** POST

**Request Payload:**
```
{
  "idToken": "<Firebase ID token>",
  "child_id": "<child_id>",
  "grade": "Kindergarten" | "First" | "Second" | "Third"
}
```

**Response:**
```
{
  "user_id": "...",
  "child_id": "...",
  "grade": "Kindergarten",
  "total_marks": 800,
  "user_score": 500,
  "answered_count": 5,
  "average_score": 62.5,
  "percentage": 62.5,              // (user_score / total_marks) * 100
  "level": "Good Speaker",        // Based on percentage (see below)
  "parent_summary": {
    "level": "Good Speaker",
    "recommendation": "See detailed feedback for each sentence.",
    "grade_placement": "At Grade Level", // Based on percentage (see below)
    "note": "Assessment is instructional and not a clinical diagnosis."
  },
  "all_results": [
    {
      "sentence_id": "abc123",
      "original_sentence": "The cat sat on the mat.",
      "transcribed_text": "The cat sat on the mat.",
      "duration_seconds": 3.2,
      "pronunciation": { ... },
      "speaking_rate": { ... },
      "fluency": { ... },
      "grammar": { ... },
      "overall": { "score": 92.5, "status": "Above", ... },
      "recommendation": "...",
      "analysis_method": "openai_gpt4",
      "status": "Answered"
    },
    ...
  ]
}
```

## Scoring & Level Mapping
- **total_marks** = number_of_sentences × 100 (e.g., 8 × 100 = 800)
- **user_score** = sum of all sentence scores (including zeros for not attempted)
- **percentage** = (user_score / total_marks) × 100
- **level**:
  - 90% and above: "Excellent Speaker"
  - 75%–89.9%: "Good Speaker"
  - 50%–74.9%: "Developing Speaker"
  - Below 50%: "Needs Improvement"
- **grade_placement**:
  - 90% and above: "Above Grade Level"
  - 75%–89.9%: "At Grade Level"
  - Below 75%: "Below Grade Level"

---

## Notes
- All endpoints require a valid Firebase ID token for authentication.
- All audio must be base64-encoded (mp3 or wav).
- Not attempted sentences should have blank audio and will be scored as zero.
- Only the latest test (batch submission) is returned by /speaking/complete_result/.
- Scoring logic is consistent for all grades and users.

---

For further details on each field or for example payloads, see the backend code or contact the API maintainer.
