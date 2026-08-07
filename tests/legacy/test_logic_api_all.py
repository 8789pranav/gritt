"""
Comprehensive Logic API Test Script
Tests all Logic Assessment endpoints and saves responses to markdown file
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"
GRADE = "Kindergarten"

def login():
    """Login to get idToken"""
    print("=" * 60)
    print("TEST 1: Login Endpoint")
    print("=" * 60)
    url = f"{BASE_URL}/login"
    payload = {"email": EMAIL, "password": PASSWORD}
    
    start_time = time.time()
    response = requests.post(url, json=payload)
    elapsed = time.time() - start_time
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS: Got id_token")
        return data.get("id_token")
    else:
        print(f"FAILED: {response.text}")
        return None

def test_get_logic_test(id_token):
    """Test GET Logic Test endpoint"""
    print("\n" + "=" * 60)
    print("TEST 2: POST /logic/get_test/")
    print("=" * 60)
    url = f"{BASE_URL}/logic/get_test/"
    payload = {
        "idToken": id_token,
        "child_id": CHILD_ID,
        "grade": GRADE
    }
    
    start_time = time.time()
    response = requests.post(url, json=payload)
    elapsed = time.time() - start_time
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS: Got {data.get('total_items')} items")
        print(f"Test ID: {data.get('test_id')}")
        return data
    else:
        print(f"FAILED: {response.text}")
        return None

def test_submit_response(id_token, test_data):
    """Test Submit Single Response endpoint"""
    print("\n" + "=" * 60)
    print("TEST 3: POST /logic/submit_response/")
    print("=" * 60)
    
    if not test_data or not test_data.get("items"):
        print("SKIPPED: No test items available")
        return None
    
    # Get first item from test
    item = test_data["items"][0]
    item_id = item["item_id"]
    correct_index = 0  # Try first option
    
    url = f"{BASE_URL}/logic/submit_response/"
    payload = {
        "idToken": id_token,
        "child_id": CHILD_ID,
        "item_id": item_id,
        "selected_answer_index": correct_index,
        "response_time_seconds": 5,
        "attempts": 1,
        "self_corrected": False,
        "explanation_provided": "Test response"
    }
    
    start_time = time.time()
    response = requests.post(url, json=payload)
    elapsed = time.time() - start_time
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS: Item {item_id} scored")
        print(f"Is Correct: {data.get('is_correct')}")
        return data
    else:
        print(f"FAILED: {response.text}")
        return None

def test_submit_test(id_token, test_data):
    """Test Submit Full Test endpoint"""
    print("\n" + "=" * 60)
    print("TEST 4: POST /logic/submit_test/")
    print("=" * 60)
    
    if not test_data or not test_data.get("items"):
        print("SKIPPED: No test items available")
        return None
    
    # Create responses for all items (first option for each)
    responses = []
    for item in test_data["items"]:
        responses.append({
            "item_id": item["item_id"],
            "selected_answer_index": 0,
            "response_time_seconds": 5,
            "attempts": 1,
            "self_corrected": False,
            "explanation_provided": "Test response"
        })
    
    url = f"{BASE_URL}/logic/submit_test/"
    payload = {
        "idToken": id_token,
        "child_id": CHILD_ID,
        "grade": GRADE,
        "responses": responses
    }
    
    start_time = time.time()
    response = requests.post(url, json=payload)
    elapsed = time.time() - start_time
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS: Test submitted")
        print(f"Score: {data.get('score')}/{data.get('total_items')}")
        print(f"Percentage: {data.get('percentage')}")
        print(f"Level: {data.get('level')}")
        return data
    else:
        print(f"FAILED: {response.text}")
        return None

def test_complete_result(id_token):
    """Test Complete Result endpoint"""
    print("\n" + "=" * 60)
    print("TEST 5: POST /logic/complete_result/")
    print("=" * 60)
    
    url = f"{BASE_URL}/logic/complete_result/"
    payload = {
        "idToken": id_token,
        "child_id": CHILD_ID,
        "grade": GRADE
    }
    
    start_time = time.time()
    response = requests.post(url, json=payload)
    elapsed = time.time() - start_time
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Time: {elapsed:.3f}s")
    
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS: Got complete result")
        print(f"Success: {data.get('success')}")
        return data
    else:
        print(f"FAILED: {response.text}")
        return None

def test_logic_ui():
    """Test Logic UI endpoint"""
    print("\n" + "=" * 60)
    print("TEST 6: GET /logic/ui")
    print("=" * 60)
    
    url = f"{BASE_URL}/logic/ui"
    
    start_time = time.time()
    response = requests.get(url)
    elapsed = time.time() - start_time
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Time: {elapsed:.3f}s")
    print(f"Content Type: {response.headers.get('content-type')}")
    
    if response.status_code == 200:
        print(f"SUCCESS: HTML page returned")
        print(f"Page size: {len(response.text)} bytes")
        return True
    else:
        print(f"FAILED: {response.text}")
        return False

def create_markdown_doc(results):
    """Create comprehensive markdown documentation"""
    md_content = f"""# Logic Test API - Test Results Documentation

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Base URL:** {BASE_URL}
**Child ID:** {CHILD_ID}
**Grade:** {GRADE}

---

## Summary

| Test | Endpoint | Status | Response Time |
|------|----------|--------|---------------|
| Login | POST /login | {results['login']['status']} | {results['login']['time']}s |
| Get Test | POST /logic/get_test/ | {results['get_test']['status']} | {results['get_test']['time']}s |
| Submit Response | POST /logic/submit_response/ | {results['submit_response']['status']} | {results['submit_response']['time']}s |
| Submit Test | POST /logic/submit_test/ | {results['submit_test']['status']} | {results['submit_test']['time']}s |
| Complete Result | POST /logic/complete_result/ | {results['complete_result']['status']} | {results['complete_result']['time']}s |
| Logic UI | GET /logic/ui | {results['logic_ui']['status']} | {results['logic_ui']['time']}s |

---

## 1. Login Endpoint

**Endpoint:** `POST /login`

### Request
```json
{{
  "email": "{EMAIL}",
  "password": "{PASSWORD}"
}}
```

### Response
```json
{json.dumps(results['login']['response'], indent=2)}
```

---

## 2. Get Logic Test Endpoint

**Endpoint:** `POST /logic/get_test/`

### Request
```json
{{
  "idToken": "<Firebase ID Token>",
  "child_id": "{CHILD_ID}",
  "grade": "{GRADE}"
}}
```

### Response
```json
{json.dumps(results['get_test']['response'], indent=2)}
```

### Notes
- Returns {results['get_test']['response'].get('total_items', 'N/A')} test items for the grade level
- Each item includes item_id, question_text, options, and difficulty level

---

## 3. Submit Single Response Endpoint

**Endpoint:** `POST /logic/submit_response/`

### Request
```json
{{
  "idToken": "<Firebase ID Token>",
  "child_id": "{CHILD_ID}",
  "item_id": "{results['submit_response']['response'].get('item_id', 'N/A')}",
  "selected_answer_index": 0,
  "response_time_seconds": 5,
  "attempts": 1,
  "self_corrected": false,
  "explanation_provided": "Test response"
}}
```

### Response
```json
{json.dumps(results['submit_response']['response'], indent=2)}
```

### Notes
- Scores individual item response
- Returns is_correct, tags_earned, and feedback

---

## 4. Submit Full Test Endpoint

**Endpoint:** `POST /logic/submit_test/`

### Request
```json
{{
  "idToken": "<Firebase ID Token>",
  "child_id": "{CHILD_ID}",
  "grade": "{GRADE}",
  "responses": [
    {{
      "item_id": "<item_id>",
      "selected_answer_index": 0,
      "response_time_seconds": 5,
      "attempts": 1,
      "self_corrected": false,
      "explanation_provided": "Test response"
    }}
  ]
}}
```

### Response
```json
{json.dumps(results['submit_test']['response'], indent=2)}
```

### Notes
- Submits all responses at once
- Returns overall score, percentage, level, and cognitive tags

---

## 5. Complete Result Endpoint

**Endpoint:** `POST /logic/complete_result/`

### Request
```json
{{
  "idToken": "<Firebase ID Token>",
  "child_id": "{CHILD_ID}",
  "grade": "{GRADE}"
}}
```

### Response
```json
{json.dumps(results['complete_result']['response'], indent=2)}
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
- **Page Size:** {results['logic_ui'].get('page_size', 'N/A')} bytes

### Notes
- Returns the Logic Assessment web UI HTML page
- Can be accessed directly in browser at: {BASE_URL}/logic/ui

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
"""
    return md_content

def main():
    """Main test execution"""
    print("=" * 60)
    print("LOGIC TEST API - COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Child ID: {CHILD_ID}")
    print(f"Grade: {GRADE}")
    print("=" * 60)
    
    results = {}
    
    # Test 1: Login
    start_time = time.time()
    id_token = login()
    elapsed = time.time() - start_time
    results['login'] = {
        'status': '✅ PASS' if id_token else '❌ FAIL',
        'time': f"{elapsed:.3f}",
        'response': {'success': True, 'id_token': id_token[:50] + '...' if id_token else None}
    }
    
    if not id_token:
        print("\n❌ Cannot continue without valid idToken")
        return
    
    # Test 2: Get Logic Test
    start_time = time.time()
    test_data = test_get_logic_test(id_token)
    elapsed = time.time() - start_time
    results['get_test'] = {
        'status': '✅ PASS' if test_data else '❌ FAIL',
        'time': f"{elapsed:.3f}",
        'response': test_data or {}
    }
    
    # Test 3: Submit Response
    start_time = time.time()
    submit_response_result = test_submit_response(id_token, test_data)
    elapsed = time.time() - start_time
    results['submit_response'] = {
        'status': '✅ PASS' if submit_response_result else '❌ FAIL',
        'time': f"{elapsed:.3f}",
        'response': submit_response_result or {}
    }
    
    # Test 4: Submit Test
    start_time = time.time()
    submit_test_result = test_submit_test(id_token, test_data)
    elapsed = time.time() - start_time
    results['submit_test'] = {
        'status': '✅ PASS' if submit_test_result else '❌ FAIL',
        'time': f"{elapsed:.3f}",
        'response': submit_test_result or {}
    }
    
    # Test 5: Complete Result
    start_time = time.time()
    complete_result = test_complete_result(id_token)
    elapsed = time.time() - start_time
    results['complete_result'] = {
        'status': '✅ PASS' if complete_result else '❌ FAIL',
        'time': f"{elapsed:.3f}",
        'response': complete_result or {}
    }
    
    # Test 6: Logic UI
    start_time = time.time()
    ui_result = test_logic_ui()
    elapsed = time.time() - start_time
    results['logic_ui'] = {
        'status': '✅ PASS' if ui_result else '❌ FAIL',
        'time': f"{elapsed:.3f}",
        'page_size': 'N/A'
    }
    
    # Create documentation
    print("\n" + "=" * 60)
    print("GENERATING DOCUMENTATION")
    print("=" * 60)
    
    md_content = create_markdown_doc(results)
    
    with open("LOGIC_API_TEST_RESULTS.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    
    print("✅ Documentation saved to LOGIC_API_TEST_RESULTS.md")
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, result in results.items():
        print(f"{test_name}: {result['status']} ({result['time']}s)")

if __name__ == "__main__":
    main()
