# `/final_report/` API — Request & Response JSON

## Endpoint

```
POST /final_report/
```

## Request Payload

```json
{
  "idToken": "eyJhbGciOiJSaZ2I...",
  "child_id": "child-uuid-1234",
  "grade": "First"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idToken` | `string` | Yes | Firebase ID token for authentication |
| `child_id` | `string` | Yes | UUID of the child profile |
| `grade` | `string` | Yes | Grade to filter results by (`Kindergarten`, `First`, `Second`, `Third`) |

## Response JSON (complete)

```json
{
  "success": true,
  "child_id": "child-uuid-1234",
  "child_name": "Aanya",
  "grade": "First",
  "generated_at": "2026-08-15T23:20:00+00:00",

  "domain_summary": {
    "logic": {
      "percentage": 87.5,
      "correct_answers": 7,
      "total_items": 8,
      "level": "Exceptional Logical Thinker",
      "tag_count": 3
    },
    "spelling": {
      "overall_accuracy": 55,
      "phonics_score": 50,
      "sight_word_score": 60,
      "confidence": "Medium",
      "tag_count": 4
    },
    "speaking": {
      "percentage": 93.0,
      "average_score": 93.0,
      "answered_count": 8,
      "level": "Excellent Speaker",
      "tag_count": 3
    },
    "comprehension": {
      "percentage": 100.0,
      "correct_answers": 8,
      "total_questions": 8,
      "level": "Excellent Reader",
      "tag_count": 4
    }
  },

  "top_5_tags": [
    {
      "tag": "vowel_accuracy_developing",
      "polarity": "growth_edge",
      "confidence": "high",
      "source_assessment": "Spelling Assessment",
      "one_sentence": "Child struggles with vowel sounds and patterns in spelling."
    },
    {
      "tag": "fluency_developing",
      "polarity": "growth_edge",
      "confidence": "medium",
      "source_assessment": "Speaking Challenge",
      "one_sentence": "Child reads with frequent pauses and hesitations."
    },
    {
      "tag": "pattern_detection_strong",
      "polarity": "strength",
      "confidence": "high",
      "source_assessment": "Logic Quest",
      "one_sentence": "Child recognises and extends patterns with confidence."
    },
    {
      "tag": "pronunciation_strong",
      "polarity": "strength",
      "confidence": "high",
      "source_assessment": "Speaking Challenge",
      "one_sentence": "Child pronounces words clearly and accurately."
    },
    {
      "tag": "relational_reasoning_present",
      "polarity": "strength",
      "confidence": "high",
      "source_assessment": "Logic Quest",
      "one_sentence": "Child connects ideas and sees relationships between concepts."
    }
  ],

  "test_importance": [
    {
      "test": "logic",
      "test_name": "Logic Quest",
      "why_it_matters": "Logic Quest measures pattern recognition, relational reasoning, and systematic problem-solving — the foundations of mathematical and scientific thinking.",
      "child_status": "This is a STRENGTH area — the child demonstrates strong logical reasoning and is ready for advanced challenges.",
      "score_summary": {
        "percentage": 87.5,
        "correct_answers": 7,
        "total_items": 8,
        "level": "Exceptional Logical Thinker",
        "tag_count": 3
      },
      "tag_count": 3,
      "dear_parent_tags": [
        {
          "tag": "pattern_detection_strong",
          "polarity": "strength",
          "description": "Child recognises and extends patterns confidently."
        }
      ]
    },
    {
      "test": "spelling",
      "test_name": "Spelling Assessment",
      "why_it_matters": "Word Wizard assesses phonetic awareness, sight-word memory, and encoding skills — critical building blocks for writing and reading fluency.",
      "child_status": "This is a HIGH PRIORITY area — spelling scores suggest the child needs daily phonics practice and targeted work on weak features.",
      "score_summary": {
        "overall_accuracy": 55,
        "phonics_score": 50,
        "sight_word_score": 60,
        "confidence": "Medium",
        "tag_count": 4
      },
      "tag_count": 4,
      "dear_parent_tags": [
        {
          "tag": "vowel_accuracy_developing",
          "polarity": "growth_edge",
          "description": "Child finds vowel sounds and patterns challenging."
        }
      ]
    },
    {
      "test": "speaking",
      "test_name": "Speaking Challenge",
      "why_it_matters": "Voice Challenge evaluates pronunciation, fluency, prosody, and grammar in spoken language — essential for communication confidence and reading aloud.",
      "child_status": "This is a STRENGTH area — the child speaks fluently and clearly, and is ready for longer or more complex passages.",
      "score_summary": {
        "percentage": 93.0,
        "average_score": 93.0,
        "answered_count": 8,
        "level": "Excellent Speaker",
        "tag_count": 3
      },
      "tag_count": 3,
      "dear_parent_tags": [
        {
          "tag": "pronunciation_strong",
          "polarity": "strength",
          "description": "Child speaks words clearly and accurately."
        }
      ]
    },
    {
      "test": "comprehension",
      "test_name": "Comprehension Assessment",
      "why_it_matters": "Story Explorer tests literal recall, inferential reasoning, and vocabulary in context — the core of reading comprehension and academic learning.",
      "child_status": "This is a STRENGTH area — the child comprehends well across question types and is ready for harder texts.",
      "score_summary": {
        "percentage": 100.0,
        "correct_answers": 8,
        "total_questions": 8,
        "level": "Excellent Reader",
        "tag_count": 4
      },
      "tag_count": 4,
      "dear_parent_tags": [
        {
          "tag": "strong_all_around_comprehension",
          "polarity": "strength",
          "description": "Child shows well-rounded reading comprehension."
        }
      ]
    }
  ],

  "all_tags": {
    "strengths": [
      {
        "tag": "pattern_detection_strong",
        "polarity": "strength",
        "confidence": "high",
        "description": "Child recognises and extends patterns confidently.",
        "evidence": "",
        "source_assessment": "Logic Quest"
      }
    ],
    "growth_edges": [
      {
        "tag": "vowel_accuracy_developing",
        "polarity": "growth_edge",
        "confidence": "high",
        "description": "Child finds vowel sounds and patterns challenging.",
        "evidence": "",
        "source_assessment": "Spelling Assessment"
      }
    ],
    "unanswered": []
  },

  "ai_report": {
    "developmental_snapshot": "Aanya is a strong logical thinker and communicator, with clear strengths in pattern recognition, pronunciation, and comprehension. She is still building fluency and vowel accuracy in spelling.",
    "strengths": [
      {
        "area": "Logic Reasoning",
        "description": "Aanya shows strong pattern detection and relational reasoning.",
        "evidence_tags": ["pattern_detection_strong", "relational_reasoning_present"],
        "evidence_assessments": ["logic"]
      },
      {
        "area": "Speaking",
        "description": "She pronounces words clearly and reads with good accuracy.",
        "evidence_tags": ["pronunciation_strong"],
        "evidence_assessments": ["speaking"]
      }
    ],
    "growth_areas": [
      {
        "area": "Spelling",
        "description": "Aanya is still developing her vowel sound awareness.",
        "evidence_tags": ["vowel_accuracy_developing"],
        "evidence_assessments": ["spelling"]
      }
    ],
    "cross_domain_patterns": [
      {
        "pattern": "Strong Verbal-Academic Profile",
        "description": "Aanya performs strongly in speaking and comprehension, showing strong verbal reasoning.",
        "assessments": ["speaking", "comprehension"],
        "evidence_tags": ["pronunciation_strong", "strong_all_around_comprehension"]
      }
    ],
    "recommendations": [
      {
        "priority": "high",
        "action": "Practice short-vowel patterns in short, decodable words for 10 minutes daily.",
        "evidence_tags": ["vowel_accuracy_developing"],
        "evidence_assessments": ["spelling"]
      }
    ],
    "parent_message": "Aanya is doing well across most areas, especially logic, speaking, and comprehension. Focus on vowel spelling practice at home, and keep encouraging read-aloud time to build fluency."
  },

  "assessments_included": ["logic", "spelling", "speaking", "comprehension"],
  "assessments_missing": []
}
```

## Response Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `success` | `boolean` | Always `true` for 200 OK |
| `child_id` | `string` | The child UUID |
| `child_name` | `string` | Child's display name |
| `grade` | `string` | Grade of the report |
| `generated_at` | `string` | ISO 8601 timestamp in UTC |
| `domain_summary` | `object` | Raw scores for each completed test (no AI) |
| `top_5_tags` | `array` | 5 most important tags with one-sentence summaries |
| `test_importance` | `array` | Why each taken test matters for this child |
| `all_tags` | `object` | All `dear_parent_tags` grouped by polarity |
| `ai_report` | `object` | AI-synthesised holistic narrative |
| `assessments_included` | `array` | List of tests the child completed |
| `assessments_missing` | `array` | List of tests the child has not yet taken |
