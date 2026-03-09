# 🎤 Speaking Test API Documentation

## Overview

The Speaking Test API enables oral reading assessment for children in grades K-3. It uses:
- **OpenAI Whisper** - Speech-to-text transcription with word timestamps
- **OpenAI GPT-4o** - Intelligent speech analysis
- **AWS Polly** - Text-to-speech for sentence audio
- **Firebase** - Data storage

---

## Authentication

All endpoints require a Firebase ID token in the request body:

```json
{
  "idToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6..."
}
```

Get the token by calling `/login/` first.

---

## Endpoints

### 1️⃣ Get Single Sentence

**Endpoint:** `POST /speaking/get_sentence/`

Returns a random sentence for the child to read, with TTS audio.

#### Request
```json
{
  "idToken": "firebase_id_token",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "First"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | string | ✅ | Firebase ID token |
| `child_id` | string | ✅ | Child's UUID |
| `grade` | string | ✅ | Grade level: `Kindergarten`, `First`, `Second`, `Third` |

#### Response
```json
{
  "grade": "First",
  "sentence_id": "f3",
  "sentence": "The children are playing outside in the rain.",
  "word_count": 8,
  "difficulty": "medium",
  "audio_base64": "//uQxAAAAAANIAAAAAExBTUUzLjEw...",
  "instructions": "Listen to the sentence, then record yourself saying it clearly."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `grade` | string | Grade level |
| `sentence_id` | string | Unique sentence identifier |
| `sentence` | string | The sentence to read |
| `word_count` | integer | Number of words |
| `difficulty` | string | `easy`, `medium`, or `hard` |
| `audio_base64` | string | MP3 audio (AWS Polly TTS) |
| `instructions` | string | Instructions for the child |

---

### 2️⃣ Get All Sentences

**Endpoint:** `POST /speaking/get_all_sentences/`

Returns all 8 sentences for a grade with TTS audio.

#### Request
```json
{
  "idToken": "firebase_id_token",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "Kindergarten"
}
```

#### Response
```json
{
  "grade": "Kindergarten",
  "total_sentences": 8,
  "sentences": [
    {
      "sentence_id": "k1",
      "sentence": "The cat sat on the mat.",
      "word_count": 6,
      "difficulty": "easy",
      "audio_base64": "//uQxAAAAAANIAAAAAExBTUUzLjEw..."
    },
    {
      "sentence_id": "k2",
      "sentence": "I see a big red dog.",
      "word_count": 6,
      "difficulty": "easy",
      "audio_base64": "//uQxAAAAAANIAAAAAExBTUUzLjEw..."
    }
  ]
}
```

---

### 3️⃣ Analyze Speech (Main API)

**Endpoint:** `POST /speaking/analyze/`

Transcribes audio using Whisper and analyzes speech using GPT-4o.

#### Request
```json
{
  "idToken": "firebase_id_token",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "First",
  "original_sentence": "The children are playing outside in the rain.",
  "audio_base64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEA...",
  "audio_format": "wav"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | string | ✅ | Firebase ID token |
| `child_id` | string | ✅ | Child's UUID |
| `grade` | string | ✅ | Grade level |
| `original_sentence` | string | ✅ | The sentence child should read |
| `audio_base64` | string | ✅ | Base64 encoded audio file |
| `audio_format` | string | ❌ | Format: `mp3`, `wav`, `webm`, `m4a` (default: `mp3`) |

#### Response
```json
{
  "original_sentence": "The children are playing outside in the rain.",
  "transcribed_text": "The children are playing outside in the rain.",
  "duration_seconds": 3.5,
  "word_timestamps": [
    {"word": "The", "start": 0.0, "end": 0.2},
    {"word": "children", "start": 0.3, "end": 0.6},
    {"word": "are", "start": 0.7, "end": 0.8},
    {"word": "playing", "start": 0.9, "end": 1.2},
    {"word": "outside", "start": 1.3, "end": 1.6},
    {"word": "in", "start": 1.7, "end": 1.8},
    {"word": "the", "start": 1.9, "end": 2.0},
    {"word": "rain", "start": 2.1, "end": 2.4}
  ],
  "analysis_method": "openai_gpt4",
  "pronunciation": {
    "score": 85,
    "correct_words": 7,
    "total_words": 8,
    "mispronounced_words": [
      {
        "expected": "the",
        "heard": "da",
        "feedback": "Practice the 'th' sound by putting your tongue between your teeth."
      }
    ],
    "feedback": "Good job! You read most words correctly."
  },
  "speaking_rate": {
    "score": 100,
    "wpm": 120,
    "status": "Perfect",
    "feedback": "Great speaking speed! Very clear and easy to understand."
  },
  "fluency": {
    "score": 90,
    "long_pauses_count": 0,
    "feedback": "Excellent fluency! Smooth and natural speaking."
  },
  "grammar": {
    "score": 100,
    "issues": [],
    "feedback": "Perfect word order!"
  },
  "overall": {
    "score": 94,
    "status": "Above",
    "level": "Excellent Speaker",
    "strengths": ["Good pace", "Clear pronunciation", "Smooth fluency"],
    "areas_to_improve": ["Practice 'th' sound"],
    "recommendation": "Keep reading aloud daily! Try more challenging sentences.",
    "parent_tip": "Practice words with 'th' sounds together: the, this, that, there."
  },
  "recommendation": "Keep reading aloud daily!",
  "parent_tip": "Practice words with 'th' sounds together."
}
```

#### Analysis Scoring

| Component | Weight | What It Measures |
|-----------|--------|------------------|
| Pronunciation | 40% | Word accuracy, sound substitutions |
| Fluency | 25% | Smoothness, pauses between words |
| Grammar | 20% | Word order, missing/extra words |
| Speaking Rate | 15% | Words per minute (target: 100-150 WPM) |

#### Overall Status Levels

| Score | Status | Level |
|-------|--------|-------|
| 90-100 | Above | Excellent Speaker |
| 70-89 | At | Good Speaker |
| 0-69 | Below | Developing Speaker |

---

### 4️⃣ Submit Speaking Test

**Endpoint:** `POST /speaking/submit/`

Transcribes, analyzes, and saves results to Firebase.

#### Request
```json
{
  "idToken": "firebase_id_token",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "First",
  "sentence_id": "f3",
  "original_sentence": "The children are playing outside in the rain.",
  "audio_base64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEA...",
  "audio_format": "wav"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | string | ✅ | Firebase ID token |
| `child_id` | string | ✅ | Child's UUID |
| `grade` | string | ✅ | Grade level |
| `sentence_id` | string | ✅ | Sentence ID from get_sentence |
| `original_sentence` | string | ✅ | The sentence child should read |
| `audio_base64` | string | ✅ | Base64 encoded audio file |
| `audio_format` | string | ❌ | Format (default: `mp3`) |

#### Response
```json
{
  "user_id": "OUE6yVj1m5MUQ3Tx7H9mXa6SbzA3",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "score_id": "-OnINI3u7HdT4SJ0piOh",
  "transcribed_text": "The children are playing outside in the rain.",
  "analysis_method": "openai_gpt4",
  "pronunciation": {
    "score": 85,
    "correct_words": 7,
    "total_words": 8,
    "mispronounced_words": [],
    "feedback": "Good pronunciation!"
  },
  "speaking_rate": {
    "score": 100,
    "wpm": 120,
    "status": "Perfect",
    "feedback": "Great pace!"
  },
  "fluency": {
    "score": 90,
    "long_pauses_count": 0,
    "feedback": "Smooth reading!"
  },
  "grammar": {
    "score": 100,
    "issues": [],
    "feedback": "Perfect!"
  },
  "overall": {
    "score": 94,
    "status": "Above",
    "level": "Excellent Speaker"
  },
  "recommendation": "Keep practicing daily!",
  "message": "Speaking test submitted successfully"
}
```

---

### 5️⃣ Get Complete Results

**Endpoint:** `POST /speaking/complete_result/`

Returns all speaking test results for a child.

#### Request
```json
{
  "idToken": "firebase_id_token",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "First"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | string | ✅ | Firebase ID token |
| `child_id` | string | ✅ | Child's UUID |
| `grade` | string | ❌ | Filter by grade (optional) |

#### Response
```json
{
  "user_id": "OUE6yVj1m5MUQ3Tx7H9mXa6SbzA3",
  "child_id": "f9fee450-a1ae-4d56-b0a7-e6edb6536074",
  "grade": "First",
  "tests_completed": 3,
  "latest_result": {
    "score_id": "-OnINI3u7HdT4SJ0piOh",
    "sentence": "The children are playing outside in the rain.",
    "transcribed": "The children are playing outside in the rain.",
    "overall": {
      "score": 94,
      "status": "Above",
      "level": "Excellent Speaker"
    },
    "timestamp": "2026-03-09T14:30:00.000Z"
  },
  "parent_summary": {
    "average_score": 88.5,
    "level": "Excellent Speaker",
    "recommendation": "Keep reading aloud daily!",
    "grade_placement": "Above Grade Level",
    "note": "Assessment is instructional and not a clinical diagnosis."
  },
  "all_results": [
    {
      "score_id": "-OnINI3u7HdT4SJ0piOh",
      "sentence": "The children are playing outside in the rain.",
      "overall_score": 94,
      "timestamp": "2026-03-09T14:30:00.000Z"
    },
    {
      "score_id": "-OnIML2v6GcS3I9oph0g",
      "sentence": "The cat sat on the mat.",
      "overall_score": 85,
      "timestamp": "2026-03-09T14:25:00.000Z"
    }
  ]
}
```

---

## Sentence Data

Each grade has 8 sentences with varying difficulty:

### Kindergarten
| ID | Sentence | Words | Difficulty |
|----|----------|-------|------------|
| k1 | The cat sat on the mat. | 6 | easy |
| k2 | I see a big red dog. | 6 | easy |
| k3 | The sun is very hot. | 5 | easy |
| k4 | My mom has a blue cup. | 6 | easy |
| k5 | The fish can swim fast. | 5 | easy |
| k6 | I like to run and hop. | 6 | medium |
| k7 | The little bug is on the leaf. | 7 | medium |
| k8 | Dad and I play in the park. | 7 | medium |

### First Grade
| ID | Sentence | Words | Difficulty |
|----|----------|-------|------------|
| f1 | The brown dog likes to play with the ball. | 9 | easy |
| f2 | She went to the store to buy some apples. | 9 | easy |
| f3 | The children are playing outside in the rain. | 8 | medium |
| f4 | My friend has a pretty yellow flower. | 7 | easy |
| f5 | We like to read books before bedtime. | 7 | medium |
| f6 | The rabbit jumped over the small fence. | 7 | medium |
| f7 | I can see the bright stars at night. | 8 | medium |
| f8 | The teacher told us a funny story today. | 8 | medium |

### Second Grade
| ID | Sentence | Words | Difficulty |
|----|----------|-------|------------|
| s1 | The beautiful butterfly landed on the colorful flower. | 8 | medium |
| s2 | Yesterday we went to the zoo and saw elephants. | 9 | medium |
| s3 | My grandmother bakes delicious cookies every weekend. | 7 | medium |
| s4 | The excited children ran quickly to the playground. | 8 | medium |
| s5 | We learned about different animals in science class. | 8 | hard |
| s6 | The thunder was loud but the lightning was bright. | 9 | hard |
| s7 | She carefully placed the fragile glass on the table. | 9 | hard |
| s8 | The astronaut floated in space looking at Earth. | 8 | hard |

### Third Grade
| ID | Sentence | Words | Difficulty |
|----|----------|-------|------------|
| t1 | The magnificent castle stood proudly on top of the mountain. | 10 | medium |
| t2 | Scientists discovered an unusual species of fish in the ocean. | 10 | hard |
| t3 | The determined athlete practiced every morning before school started. | 8 | hard |
| t4 | My favorite subject is mathematics because I enjoy solving problems. | 9 | hard |
| t5 | The ancient Egyptian pyramids are thousands of years old. | 8 | hard |
| t6 | We celebrated my sister's birthday with a spectacular surprise party. | 9 | hard |
| t7 | The courageous firefighter rescued the kitten from the tall tree. | 10 | hard |
| t8 | Reading comprehension improves when you practice regularly every day. | 8 | hard |

---

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Invalid token: Token expired or invalid"
}
```

### 404 Not Found
```json
{
  "detail": "Child not found"
}
```

```json
{
  "detail": "No speaking test results found"
}
```

### 400 Bad Request
```json
{
  "detail": "Invalid grade. Must be: Kindergarten, First, Second, or Third"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Transcription failed: OpenAI API key not configured"
}
```

---

## Audio Format Support

| Format | MIME Type | Extension |
|--------|-----------|-----------|
| MP3 | audio/mpeg | .mp3 |
| WAV | audio/wav | .wav |
| WebM | audio/webm | .webm |
| M4A | audio/m4a | .m4a |
| OGG | audio/ogg | .ogg |
| FLAC | audio/flac | .flac |

---

## Flow Diagram

```
┌─────────────────┐
│  1. Get Sentence │
│  /get_sentence/  │
└────────┬────────┘
         │ Returns sentence + TTS audio
         ▼
┌─────────────────┐
│  2. Child Reads │
│  Records Audio  │
└────────┬────────┘
         │ Base64 audio
         ▼
┌─────────────────┐
│  3. Analyze     │
│  /analyze/      │──────────────────────┐
└────────┬────────┘                      │
         │                               │
         ▼                               ▼
┌─────────────────┐              ┌───────────────┐
│ OpenAI Whisper  │              │ OpenAI GPT-4o │
│ Transcription   │──────────────│ Analysis      │
└────────┬────────┘              └───────┬───────┘
         │                               │
         └───────────────┬───────────────┘
                         │
                         ▼
               ┌─────────────────┐
               │  4. Submit      │
               │  /submit/       │
               └────────┬────────┘
                        │ Save to Firebase
                        ▼
               ┌─────────────────┐
               │  5. Results     │
               │  /complete_result/│
               └─────────────────┘
```

---

## Environment Variables

```env
OPENAI_API_KEY=sk-proj-your-key-here
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_REGION=us-east-1
FIREBASE_API_KEY=your-firebase-key
FIREBASE_DB_URL=https://your-project.firebaseio.com
FIREBASE_CRED_BASE64=base64-encoded-service-account
```

---

## Testing

Run the test script:

```bash
python test_real_audio.py
```

This tests all endpoints with a synthetic audio file.

---

## Firebase Data Structure

```
users/
  {user_id}/
    children/
      {child_id}/
        speaking_scores/
          {score_id}/
            grade: "First"
            sentence_id: "f3"
            original_sentence: "The children are..."
            transcribed_text: "The children are..."
            duration_seconds: 3.5
            pronunciation: {...}
            speaking_rate: {...}
            fluency: {...}
            grammar: {...}
            overall: {...}
            recommendation: "..."
            analysis_method: "openai_gpt4"
            timestamp: "2026-03-09T14:30:00.000Z"
```
