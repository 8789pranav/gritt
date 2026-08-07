# 🚀 Run Logic API Tests

## Quick Commands

### 1️⃣ Start the API Server (Terminal 1)
```bash
python main.py
```

Wait for:
```
INFO:     Uvicorn running on http://localhost:8000
```

---

### 2️⃣ Run All Tests (Terminal 2)
```bash
python run_all_logic_tests.py
```

**This runs:**
- ✅ Comprehensive workflow test
- ✅ All grades test (8 grades)
- ✅ Edge cases test (9 scenarios)

**Output:**
- Console report with statistics
- JSON file: `logic_test_report_YYYYMMDD_HHMMSS.json`

---

## Or Run Individual Tests

### Comprehensive Test (Full Workflow)
```bash
python test_logic_comprehensive.py
```

**Tests:**
- Login authentication
- Get logic test
- Submit single response
- Submit complete test
- Get complete result

---

### All Grades Test
```bash
python test_logic_all_grades.py
```

**Tests:**
- Kindergarten, First, Second, Third
- K-1, 1-2, 2-3, 3-4

---

### Edge Cases Test
```bash
python test_logic_edge_cases.py
```

**Tests:**
- Invalid tokens
- Invalid grades
- Invalid IDs
- Out-of-range answers
- Missing fields
- And more...

---

## Configuration

Edit at the top of each test file:

```python
BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"
GRADE = "Kindergarten"
```

---

## Expected Output

### ✅ Success
```
🎉 ALL TESTS PASSED! 🎉
```

### ❌ Failure
```
⚠️ X test(s) failed
```

Check output for detailed error messages.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Start server: `python main.py` |
| 401 Unauthorized | Check email/password |
| 404 Not Found | Verify child ID |
| 400 Bad Request | Check grade value |

---

## Documentation

- **Detailed Guide**: `LOGIC_API_TESTING_GUIDE.md`
- **Quick Start**: `QUICK_START_LOGIC_TESTING.md`
- **Summary**: `LOGIC_TESTING_SUMMARY.md`

---

**Ready? Run the tests! 🧪**
