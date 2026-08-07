# Logic Assessment - Quick Reference Card

## 📊 At a Glance

| Metric | Value |
|--------|-------|
| **Total Questions** | 40 (10 per grade) |
| **Grade Levels** | K-1, 1-2, 2-3, 3-4 |
| **Cognitive Tags** | 9 tracked |
| **Item Types** | 25+ unique types |
| **Test Duration** | 10-20 minutes |
| **Performance Levels** | 5 levels |

---

## 🎯 Sample Questions by Grade

### Kindergarten (K-1)
```
Q1: "Red, blue, red, blue, ___"
    → Answer: Blue (Pattern)

Q3: "Which doesn't belong? Apple, banana, car"
    → Answer: Car (Categorization)

Q6: "Bird is to sky as fish is to ___"
    → Answer: Water (Analogy)

Q8: "All glims are red. This is a glim. So this is ___"
    → Answer: Red (Rule Application)
```

### Grade 1-2
```
Q2: "What comes next? 5, 10, 15, ___"
    → Answer: 20 (Number Pattern)

Q6: "All squares have 4 sides. This has 4 sides. Is it a square?"
    → Answer: Can't tell (Logic Fallacy)

Q8: "Sort by color, then by size. Success?"
    → Answer: Yes, easily (Cognitive Flexibility)
```

### Grade 2-3
```
Q1: "What comes next? 3, 6, 9, 12, ___"
    → Answer: 15 (Skip Counting)

Q6: "If A = B and B = C, then A = C. True or false?"
    → Answer: True (Transitive Property)

Q7: "5 apples + 3 oranges - 2 apples. How many apples?"
    → Answer: 4 (Multi-Step)
```

### Grade 3-4
```
Q1: "What comes next? 2, 4, 8, 16, ___"
    → Answer: 32 (Exponential)

Q5: "Justice is to law as ??? is to science"
    → Answer: Truth (Abstract Analogy)

Q7: "10 - (3 + 2) × 2 = ?"
    → Answer: 0 (Order of Operations)
```

---

## 🧠 9 Cognitive Tags

### ✅ Strength Tags
1. **Pattern Detection Strong** - Identifies patterns quickly
2. **Pattern Detection Emerging** - Basic pattern recognition
3. **Relational Reasoning Present** - Understands relationships
4. **Systematic Problem Solving** - Methodical approach
5. **Cognitive Flexibility Intact** - Adapts strategies
6. **Flexible Strategy Use** - Creative problem-solving

### ⚠️ Development Tags
7. **Reasoning Under Load Emerging** - Struggles under pressure
8. **Trial and Error Strategy** - Random attempts
9. **Strategy Shift Difficulty** - Can't change approaches

---

## 📈 Performance Levels

| Score | Level | Description |
|-------|-------|-------------|
| 90%+ | **Exceptional** | Outstanding logical reasoning |
| 80-89% | **Advanced** | Strong logical skills |
| 70-79% | **Good** | Solid reasoning abilities |
| 60-69% | **Developing** | Building logical skills |
| <60% | **Emerging** | Beginning logical journey |

---

## 📝 What We Track Per Response

```json
{
  "item_id": "k1_1",
  "selected_answer_index": 1,
  "response_time_seconds": 18,
  "attempts": 1,
  "self_corrected": false,
  "is_correct": true,
  "tags_earned": ["pattern_detection_emerging"]
}
```

**7 Data Points Per Question:**
1. Selected answer
2. Response time
3. Number of attempts
4. Self-correction
5. Correctness
6. Cognitive tags earned
7. Explanation quality

---

## 🎯 Scoring Thresholds

### Tag Award Criteria
- **Pattern Detection**: 3+ pattern items correct
- **Relational Reasoning**: 3+ relational items correct
- **Cognitive Flexibility**: 2+ flexibility items correct
- **Reasoning Under Load**: 2+ items with time struggles
- **Trial and Error**: 2+ items with multiple attempts
- **Strategy Shift Difficulty**: 1+ flexibility item failed

---

## 📊 Example Test Result

### High Performer (90%)
```
Grade: Kindergarten
Score: 9/10 (90%)
Level: Exceptional Logical Thinker

Tags Earned:
✅ Pattern Detection Strong
✅ Relational Reasoning Present
✅ Systematic Problem Solving

Strengths:
• Excellent pattern recognition
• Strong visual-spatial reasoning

Recommendation:
"Challenge with advanced puzzles!"
```

### Developing Student (60%)
```
Grade: Second
Score: 6/10 (60%)
Level: Developing Logical Thinker

Tags Earned:
✅ Pattern Detection Emerging
⚠️ Reasoning Under Load Emerging
⚠️ Trial and Error Strategy
⚠️ Strategy Shift Difficulty

Areas to Develop:
• Working under time pressure
• Multi-step problem solving
• Shifting strategies

Recommendation:
"Focus on guided problem-solving"
```

---

## 🔄 API Flow

```
1. GET TEST
   POST /logic/get_test/
   → Returns 10 questions

2. SUBMIT RESPONSES
   POST /logic/submit_test/
   → Scores & saves results

3. GET RESULTS
   POST /logic/complete_result/
   → Returns parent summary
```

---

## 📱 Response Format

### Submit Test Request
```json
{
  "idToken": "token",
  "child_id": "uuid",
  "grade": "Kindergarten",
  "responses": [
    {
      "item_id": "k1_1",
      "selected_answer_index": 1,
      "response_time_seconds": 18,
      "attempts": 1,
      "self_corrected": false
    }
    // ... 9 more
  ]
}
```

### Complete Result Response
```json
{
  "success": true,
  "student_id": "uuid",
  "grade": "Kindergarten",
  "summary": {
    "total_items": 10,
    "correct_answers": 9,
    "percentage": 90.0,
    "level": "Exceptional Logical Thinker"
  },
  "parent_summary": {
    "performance_level": "Exceptional",
    "grade_placement": "Above Grade Level",
    "strengths": [...],
    "areas_to_develop": [...],
    "recommendation": "..."
  },
  "behavioral_signals": {
    "reasoning_under_load": false,
    "trial_and_error": false,
    "strategy_shift_difficulty": false
  }
}
```

---

## ⏱️ Expected Response Times

| Grade | Easy | Medium | Hard |
|-------|------|--------|------|
| K-1 | 15-20s | 25-30s | 30-35s |
| 1-2 | 20-25s | 30-40s | 45-50s |
| 2-3 | 25-30s | 35-45s | 50-60s |
| 3-4 | 30-35s | 40-50s | 50-60s |

---

## 🎓 Item Type Distribution

### K-1 (10 items)
- Pattern: 4
- Relational: 3
- Matching: 2
- Rule: 1

### 1-2 (10 items)
- Pattern: 3
- Relational: 2
- Problem Solving: 3
- Flexibility: 2

### 2-3 (10 items)
- Pattern: 2
- Relational: 2
- Problem Solving: 4
- Flexibility: 2

### 3-4 (10 items)
- Pattern: 2
- Abstract: 3
- Problem Solving: 3
- Flexibility: 2

---

## 🔍 Key Insights

### Response Time Patterns
- **Fast (<80% expected)**: Strong mastery
- **Normal (80-120% expected)**: Appropriate difficulty
- **Slow (>150% expected)**: Struggling, may trigger "Under Load" tag

### Multiple Attempts
- **1 attempt**: Confident, clear understanding
- **2-3 attempts**: Some uncertainty, trial and error
- **3+ attempts**: Significant struggle, needs support

### Self-Correction
- **Positive indicator**: Meta-cognitive awareness
- **Shows**: Ability to monitor own thinking
- **Rare in K-1**: More common in 3-4

---

## 📞 Quick Links

- **Full Analysis**: `LOGIC_ASSESSMENT_DEEP_ANALYSIS.md`
- **API Testing**: `LOGIC_API_TESTING_GUIDE.md`
- **Quick Start**: `QUICK_START_LOGIC_TESTING.md`
- **Test Scripts**: `test_logic_*.py`

---

**Version**: 1.0  
**Status**: ✅ Production Ready
