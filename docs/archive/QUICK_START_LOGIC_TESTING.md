# Quick Start - Logic API Testing

## 🚀 Quick Start Guide

### Step 1: Start the API Server

```bash
python main.py
```

**Expected Output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://localhost:8000
```

---

### Step 2: Run Tests

#### Option A: Run All Tests (Recommended)
```bash
python run_all_logic_tests.py
```

#### Option B: Run Individual Tests

**Comprehensive Test (Full Workflow):**
```bash
python test_logic_comprehensive.py
```

**All Grades Test:**
```bash
python test_logic_all_grades.py
```

**Edge Cases Test:**
```bash
python test_logic_edge_cases.py
```

---

## 📋 Test Configuration

Edit these values at the top of each test file:

```python
BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"
GRADE = "Kindergarten"
```

---

## ✅ What Gets Tested

### 1. Comprehensive Test (`test_logic_comprehensive.py`)
- ✅ User login and authentication
- ✅ Get logic test (10 items for grade)
- ✅ Submit single item response
- ✅ Submit complete test (all items)
- ✅ Get complete result with parent summary

### 2. All Grades Test (`test_logic_all_grades.py`)
- ✅ Kindergarten / K-1
- ✅ First / 1-2
- ✅ Second / 2-3
- ✅ Third / 3-4

### 3. Edge Cases Test (`test_logic_edge_cases.py`)
- ❌ Invalid authentication token
- ❌ Invalid grade level
- ❌ Invalid child ID
- ❌ Invalid item ID
- ❌ Out-of-range answers
- ❌ Negative response times
- ❌ Empty responses
- ❌ Duplicate responses
- ❌ Missing required fields

---

## 📊 Expected Results

### Successful Test Output:
```
✅ Login successful!
✅ Test retrieved successfully!
✅ Response submitted successfully!
✅ Test submitted successfully!
✅ Complete result retrieved successfully!

🎉 ALL TESTS PASSED! 🎉
```

### Test Metrics:
- **Total Items**: 10 per grade
- **Response Time**: 5-45 seconds (simulated)
- **Score**: Random (0-10 correct)
- **Cognitive Tags**: Generated based on performance
- **Performance Level**: Based on percentage

---

## 🔍 API Endpoints Tested

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/logic/get_test/` | POST | Get test items for grade |
| `/logic/submit_response/` | POST | Submit single item response |
| `/logic/submit_test/` | POST | Submit complete test |
| `/logic/complete_result/` | POST | Get detailed results |

---

## 🎯 Performance Levels

| Score | Level |
|-------|-------|
| 90%+ | Exceptional Logical Thinker |
| 80-89% | Advanced Logical Thinker |
| 70-79% | Good Logical Thinker |
| 60-69% | Developing Logical Thinker |
| <60% | Emerging Logical Thinker |

---

## 🧠 Cognitive Tags

### Strengths:
- `pattern_detection_strong`
- `relational_reasoning_present`
- `systematic_problem_solving`
- `cognitive_flexibility_intact`
- `flexible_strategy_use`

### Areas to Develop:
- `pattern_detection_emerging`
- `reasoning_under_load_emerging`
- `trial_and_error_strategy`
- `strategy_shift_difficulty`

---

## 🐛 Troubleshooting

### Issue: Connection Refused
```
Error: Connection refused
```
**Solution:** Start the API server with `python main.py`

### Issue: Authentication Failed
```
Status: 401 Unauthorized
```
**Solution:** 
1. Check email/password in test file
2. Verify Firebase credentials
3. Ensure user account exists

### Issue: Child Not Found
```
Status: 404 Not Found
```
**Solution:** 
1. Verify child ID in test file
2. Create child profile if needed
3. Check database connection

---

## 📁 Test Files Created

1. **`test_logic_comprehensive.py`** - Full workflow test
2. **`test_logic_all_grades.py`** - Multi-grade test
3. **`test_logic_edge_cases.py`** - Error handling test
4. **`run_all_logic_tests.py`** - Master test runner
5. **`LOGIC_API_TESTING_GUIDE.md`** - Detailed documentation
6. **`QUICK_START_LOGIC_TESTING.md`** - This file

---

## 💡 Tips

1. **Run tests after code changes** to ensure nothing broke
2. **Check test output** for detailed error messages
3. **Review JSON report** for comprehensive results
4. **Update test data** if credentials change
5. **Monitor performance** by tracking test duration

---

## 📞 Need Help?

1. Check server logs: Look at console output from `python main.py`
2. Review test output: Read error messages carefully
3. Verify configuration: Double-check credentials and IDs
4. Check documentation: See `LOGIC_API_TESTING_GUIDE.md`

---

## ⚡ One-Liner Test Commands

```bash
# Start server (Terminal 1)
python main.py

# Run all tests (Terminal 2)
python run_all_logic_tests.py

# Or run individual tests
python test_logic_comprehensive.py
python test_logic_all_grades.py
python test_logic_edge_cases.py
```

---

**Happy Testing! 🎉**
