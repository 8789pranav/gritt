# The Dear Parent Project — Learning Snapshot Architecture

## 1. What we are building

A single-page **Learning Snapshot** report that reads like a warm letter from a
teacher, not a dashboard. It synthesizes data from all four assessments into
five cross-cutting **learning areas**, shows strengths and growth edges, and
gives parents two or three specific things to try at home.

The target UI is in `snapshot-letter-live.pdf`. Its tone is:

- First-person narrative ("I sat with Aria through four short adventures")
- Observations, not scores, labels, or grade levels
- Evidence badges: "Seen more than once" vs "Seen once, so held lightly"
- A closing disclaimer: not a diagnosis, compares the child to no one

**The narrative is written by an LLM.** The structure — which areas fired,
which tags are behind them, how many tests contributed evidence — is computed
deterministically. The LLM writes the words. The pipeline feeds it structured
evidence and enforces guardrails on what comes out.

---

## 2. Why an LLM is required

The writing in the PDF references specific behaviors and makes connections
that a static copy library can never produce:

| Example from the PDF | What it requires |
|---------------------|-----------------|
| "the two hardest she slowed right down, took her time, and got both of them out" | References specific hard items, their timing, and their outcome |
| "On the ones she recognised, she was quick" | Nuanced behavioral observation from timing data |
| "both sit at the ends of words" | Cross-test pattern connecting speaking and spelling |
| "expression is still catching up with how accurately she reads" | Interpretive comparison across dimensions |
| "that is a child choosing her speed to suit the problem" | Insight unique to this child's evidence |
| "When Aria goes quiet on something hard, that is the thinking happening" | Specific suggestion derived from observed behavior |

Each letter is different because each child's evidence is different. The LLM
receives the structured evidence and writes a letter that could only belong
to that child.

---

## 3. The five learning areas

Every tag from every test is mapped to exactly one of five areas. The areas
are the organizing principle of the letter; individual test tags are the
evidence underneath them.

| Learning Area | What it measures | Which tests feed it |
|---------------|-----------------|---------------------|
| **Pace & Approach** | Speed vs difficulty, persistence, adaptability, self-correction | Logic Quest, Word Wizard, Voice Challenge |
| **Patterns & Structure** | Pattern detection, phonetic decoding, rule-switching, word construction | Logic Quest, Word Wizard |
| **Reasoning & Meaning** | Inference, connecting ideas, comprehension, working through multi-step problems | Story Explorer, Logic Quest |
| **Language & Expression** | Reading aloud, pronunciation, prosody, fluency, spelling conventions | Voice Challenge, Word Wizard |
| **Listening Channel** | Following a story by ear, holding details across a passage | Story Explorer, Word Wizard |

---

## 4. Tag-to-area mapping

Declared in a config file so it lives outside the code.

**File:** `data/tags/learning_areas.json`

```json
{
  "pace_and_approach": {
    "display_name": "Pace & Approach",
    "sources": {
      "logic": ["deliberate_pace", "impulsive_response", "self_correction_present"],
      "spelling": ["phonetic_strategy_strong", "rushed_spelling"],
      "speaking": ["deliberate_pace_speaking"]
    }
  },
  "patterns_and_structure": {
    "display_name": "Patterns & Structure",
    "sources": {
      "logic": ["pattern_detection_strong", "pattern_detection_emerging",
                 "systematic_problem_solving", "flexible_strategy_use",
                 "flexible_strategy_emerging"],
      "spelling": ["digraph_competent", "blend_competent", "long_vowel_competent"]
    }
  },
  "reasoning_and_meaning": {
    "display_name": "Reasoning & Meaning",
    "sources": {
      "logic": ["relational_reasoning_present", "reasoning_under_load",
                 "reasoning_under_load_emerging"],
      "comprehension": ["inferential_comprehension_strong",
                         "inferential_comprehension_emerging"]
    }
  },
  "language_and_expression": {
    "display_name": "Language & Expression",
    "sources": {
      "speaking": ["pronunciation_strong", "prosody_emerging", "fluency_strong"],
      "spelling": ["spelling_convention_emerging"]
    }
  },
  "listening_channel": {
    "display_name": "Listening Channel",
    "sources": {
      "comprehension": ["literal_comprehension_strong",
                         "literal_comprehension_emerging",
                         "vocabulary_in_context_strong",
                         "vocabulary_in_context_emerging"]
    }
  }
}
```

---

## 5. Architecture: two-stage pipeline

The deterministic stage computes the STRUCTURE. The LLM stage writes the
WORDS. Neither can do the other's job.

```
┌──────────────────────────────────────────────────────────────┐
│  STAGE A: DETERMINISTIC (no LLM)                             │
│                                                              │
│  A1. Fetch — call all 4 complete-result endpoints            │
│  A2. Extract — pull rollup tags, per-item tags, signals,     │
│      timing data, per-item outcomes                         │
│  A3. Map to areas — group tags into the 5 learning areas     │
│  A4. Compute evidence — for each area:                       │
│        - which tests contributed                            │
│        - evidence_strength: seen_more_than_once | seen_once │
│        - polarity: strength | growth_edge                   │
│        - supporting per-item evidence (for the LLM)         │
│  A5. Rank — order observations by evidence strength,        │
│      pick top 2-3 strengths and top 2-3 growth edges         │
│                                                              │
│  Output: StructuredEvidence (JSON)                           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  STAGE B: LLM NARRATIVE (GPT-4o)                             │
│                                                              │
│  B1. Build prompt — system prompt + structured evidence      │
│  B2. Generate — one LLM call writes the entire letter        │
│  B3. Validate — enforce guardrails on the output            │
│                                                              │
│  Output: SnapshotLetter (JSON)                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. What the LLM receives

The LLM receives a structured evidence package. This is the INPUT — it
contains everything the LLM needs to write the letter, and nothing it
doesn't.

```json
{
  "child_name": "Aria",
  "grade": "kindergarten",
  "tests_completed": ["logic", "spelling", "speaking", "comprehension"],

  "observations": [
    {
      "area": "pace_and_approach",
      "area_display_name": "Pace & Approach",
      "polarity": "strength",
      "evidence_strength": "seen_more_than_once",
      "seen_in": ["Logic Quest", "Voice Challenge"],
      "tags": ["deliberate_pace", "self_correction_present"],
      "evidence_detail": {
        "logic": {
          "slow_and_correct_count": 2,
          "hard_items_total": 3,
          "hard_items_correct": 3,
          "median_response_time": 12.5,
          "slow_items_response_times": [28.0, 35.0],
          "fast_items_response_times": [4.0, 5.0, 6.0]
        },
        "speaking": {
          "pauses_detected": 4,
          "avg_pause_duration": 2.1,
          "self_corrections": 2
        }
      }
    },
    {
      "area": "reasoning_and_meaning",
      "area_display_name": "Reasoning & Meaning",
      "polarity": "strength",
      "evidence_strength": "seen_more_than_once",
      "seen_in": ["Story Explorer", "Logic Quest"],
      "tags": ["inferential_comprehension_strong", "relational_reasoning_present"],
      "evidence_detail": {
        "comprehension": {
          "inferential_attempted": 3,
          "inferential_correct": 3,
          "question_types": ["why character felt", "implied meaning"]
        },
        "logic": {
          "relational_attempted": 3,
          "relational_correct": 3
        }
      }
    }
  ],

  "growth_edges": [
    {
      "area": "language_and_expression",
      "area_display_name": "Language & Expression",
      "polarity": "growth_edge",
      "evidence_strength": "seen_once",
      "seen_in": ["Voice Challenge"],
      "tags": ["prosody_emerging"],
      "evidence_detail": {
        "speaking": {
          "accuracy_score": 0.92,
          "prosody_score": 0.61,
          "fluency_score": 0.88,
          "dimension_gap": "prosody 0.31 below accuracy"
        }
      }
    },
    {
      "area": "patterns_and_structure",
      "area_display_name": "Patterns & Structure",
      "polarity": "growth_edge",
      "evidence_strength": "seen_more_than_once",
      "seen_in": ["Voice Challenge", "Word Wizard"],
      "tags": ["spelling_convention_emerging"],
      "evidence_detail": {
        "speaking": {
          "word_endings_slipped": ["-ed", "-s"]
        },
        "spelling": {
          "convention_errors": ["candle→kandle", "outline→owtline"],
          "convention_error_count": 2
        }
      }
    }
  ],

  "full_picture_areas": [
    {
      "area": "pace_and_approach",
      "display_name": "Pace & Approach",
      "badge": "seen_repeatedly",
      "seen_in": ["Logic Quest", "Voice Challenge"]
    }
  ]
}
```

---

## 7. The LLM prompt

### System prompt

```
You are a teacher writing a letter to a parent about their child.

You will receive structured evidence from four educational assessments the
child completed this week. Your job is to write a warm, specific, honest
letter about what the child did.

VOICE AND TONE
- Write in first person, as if you sat with the child through the activities.
- Be warm but never saccharine.
- Be specific: reference actual behaviors, actual items, actual outcomes.
- Be honest: if something is still developing, say so plainly and kindly.
- Never use the words "score", "percent", "grade level", "above", "below",
  "average", "normal", "advanced", "behind", or "diagnosis".
- Never compare the child to other children or to a standard.
- Describe what the child DID, not what the child IS.

STRUCTURE
Return JSON with these exact keys:

{
  "opening": {
    "headline": "One sentence, the most striking thing about this child.",
    "paragraph": "2-3 sentences. Personal, narrative. Reference specific
                  behaviors from the evidence."
  },
  "what_i_noticed": [
    {
      "headline": "One-line observation. Short.",
      "area_display_name": "From the evidence.",
      "paragraph": "2-3 sentences. Reference specific items, counts, or
                     timing from the evidence_detail.",
      "seen_in": ["From the evidence."],
      "learning_signals": ["2-4 short phrases, e.g. 'Takes thinking time'"]
    }
  ],
  "what_helped": {
    "headline": "One sentence about what conditions helped.",
    "signals": ["2-3 short phrases"]
  },
  "still_growing": [
    {
      "headline": "One-line growth area. Kind, not clinical.",
      "paragraph": "2-3 sentences. What is still developing and why
                     that's okay.",
      "suggestion": {
        "title": "One specific thing to try at home.",
        "body": "2-3 sentences. Concrete and actionable.",
        "because": "One sentence starting with 'Because' explaining why
                     this suggestion follows from the evidence."
      }
    }
  ],
  "full_picture": [
    {
      "area_display_name": "From the evidence.",
      "badge": "seen_repeatedly or seen_once",
      "paragraph": "2-3 sentences summarizing this area across all tests
                     that contributed.",
      "seen_in": ["From the evidence."]
    }
  ],
  "closing": "1-2 sentences. Warm. References the disclaimer tone."
}

RULES
- Maximum 3 items in "what_i_noticed".
- Maximum 3 items in "still_growing".
- Every "seen_in" must match the evidence exactly.
- Every suggestion must follow from a specific observation in the evidence.
- If evidence_strength is "seen_once", mention that this was observed in
  one context only, gently.
- Use the child's name naturally, not in every sentence.
```

### User message

The structured evidence JSON (Section 6).

### Model

`gpt-4o` with `response_format: { "type": "json_object" }`.

---

## 8. Guardrails (enforced on LLM output)

The LLM output is validated before it reaches the parent. If validation
fails, the letter falls back to a generic warm letter with no specifics.

| Guardrail | How enforced |
|-----------|-------------|
| No scores or percentages | Regex check for digits followed by "%" or "out of" |
| No grade levels or labels | Word list: "above grade", "below grade", "at grade", "advanced", "behind", "average", "normal" |
| No clinical language | Word list: "diagnosis", "disorder", "deficit", "delay", "therapy" |
| No comparison to other children | Word list: "compared to", "other children", "most children", "peers" |
| Max 3 observations | `len(what_i_noticed) <= 3` |
| Max 3 growth edges | `len(still_growing) <= 3` |
| Correct structure | JSON schema validation |
| seen_in matches evidence | Cross-check against the input evidence |
| Every suggestion has a "because" | Schema validation |

If any guardrail fails, the pipeline:
1. Logs the failure
2. Retries the LLM once with the guardrail violation in the error message
3. If it fails again, falls back to a generic warm letter (no specifics, no tags)

---

## 9. API contract

### New endpoint

```
GET /api/v1/snapshot/{child_id}?grade=kindergarten
Authorization: Bearer <id_token>
```

Returns the fully synthesized letter. The frontend renders it as-is.

### Response shape

```json
{
  "child_id": "child_123",
  "child_name": "Aria",
  "grade": "kindergarten",
  "generated_at": "2026-09-09T15:00:00Z",
  "tests_completed": ["logic", "spelling", "speaking", "comprehension"],

  "opening": {
    "headline": "Aria stayed with the hardest problems until she worked them out.",
    "paragraph": "I sat with Aria through four short adventures this week..."
  },

  "what_i_noticed": [
    {
      "headline": "She stays with a hard problem",
      "area_display_name": "Pace & Approach",
      "paragraph": "On the most demanding puzzles Aria took several times longer...",
      "seen_in": ["Logic Quest", "Voice Challenge"],
      "learning_signals": ["Takes thinking time", "Works step by step"]
    }
  ],

  "what_helped": {
    "headline": "Time, mostly. Given room to think, Aria finished every hard problem on her own.",
    "signals": ["Thinking time", "Room to try"]
  },

  "still_growing": [
    {
      "headline": "Growing into expression",
      "paragraph": "When Aria reads aloud, her expression is still catching up...",
      "suggestion": {
        "title": "Read aloud together, for fun rather than for accuracy.",
        "body": "Take a character each in something with plenty of dialogue...",
        "because": "Because expression was the one thing still developing."
      }
    }
  ],

  "full_picture": [
    {
      "area_display_name": "Pace & Approach",
      "badge": "seen_repeatedly",
      "paragraph": "Aria varied her pace with the difficulty of the task...",
      "seen_in": ["Logic Quest", "Voice Challenge"]
    }
  ],

  "closing": "This is a starting point for a conversation about how Aria learns. It is not a diagnosis or a formal assessment, and it compares her to no one.",
  "branding": "The Dear Parent Project",

  "meta": {
    "llm_generated": true,
    "evidence_areas_count": 5,
    "guardrails_passed": true
  }
}
```

---

## 10. Implementation plan

### Phase 1: Backend

| Step | File | What it does |
|------|------|-------------|
| 1 | `data/tags/learning_areas.json` | Tag-to-area mapping config |
| 2 | `app/services/snapshot_service.py` | Stage A: deterministic evidence pipeline |
| 3 | `app/services/snapshot_writer.py` | Stage B: LLM prompt, generation, guardrail validation |
| 4 | `app/routers/snapshot.py` | `GET /snapshot/{child_id}` |
| 5 | `scripts/test_snapshot_service.py` | Test Stage A with mocked test results |
| 6 | `scripts/test_snapshot_writer.py` | Test Stage B with mocked LLM |
| 7 | `scripts/test_snapshot_e2e.py` | Full E2E: submit 4 tests, fetch snapshot |

### Phase 2: Frontend

| Step | Component | What it renders |
|------|-----------|-----------------|
| 8 | `SnapshotLetter` | The main letter page |
| 9 | `ObservationCard` | One "WHAT I NOTICED" card |
| 10 | `GrowthCard` | One "STILL GROWING" card with suggestion + because |
| 11 | `FullPictureSection` | All 5 areas with badges |
| 12 | `Disclaimer` | The closing note |

### Phase 3: Tuning

| Step | What |
|------|------|
| 13 | Generate letters for sample data, review tone |
| 14 | Tune the prompt based on output quality |
| 15 | Add more evidence_detail fields as needed |

---

## 11. Fallbacks

| Scenario | Behavior |
|----------|----------|
| 0 tests completed | Generic letter: "We haven't had a chance to work together yet" |
| 1 test completed | Letter works, all observations are "seen once" |
| LLM call fails | Retry once, then fall back to a warm generic letter |
| Guardrail fails | Retry once with violation noted, then fall back |
| A test fetch fails | Skip it, note it in the letter |

The fallback letter is warm, short, and references no specifics. It is
better to send no specifics than wrong specifics.

---

## 12. Cost and latency

- **One LLM call per snapshot generation** (gpt-4o, JSON mode)
- **Input:** ~2000-4000 tokens (structured evidence)
- **Output:** ~1500-2500 tokens (the letter JSON)
- **Estimated cost:** ~$0.03-0.06 per snapshot
- **Latency:** ~5-10 seconds for the LLM call
- **Caching:** The snapshot is cached in Firebase per child per grade.
  Regenerating requires an explicit refresh.

---

## 13. What we are NOT doing

- No AI-generated tag semantics. The LLM writes words, not judgements.
- No scores, percentages, grade levels, or labels anywhere.
- No comparison to other children or to a standard.
- No clinical language or diagnostic framing.
- No client-side processing. The backend returns the finished letter.
- No per-question detail in the letter. Specifics come from aggregate evidence.
