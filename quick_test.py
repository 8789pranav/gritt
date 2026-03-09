# Quick API Test - No Auth Required for Some Tests
import requests
import json

BASE_URL = "http://localhost:8000"

print("="*60)
print("🧪 QUICK API TESTS (No Auth Required)")
print("="*60)

# Test 1: Check if server is running
print("\n1️⃣ Testing server connection...")
try:
    response = requests.get(f"{BASE_URL}/docs", timeout=5)
    if response.status_code == 200:
        print("   ✅ Server is running!")
    else:
        print(f"   ⚠️ Server returned: {response.status_code}")
except Exception as e:
    print(f"   ❌ Server not responding: {e}")
    print("   Make sure to run: uvicorn main:app --reload")
    exit(1)

# Test 2: Grade endpoint (no auth needed)
print("\n2️⃣ Testing /grade/ endpoint...")
response = requests.post(
    f"{BASE_URL}/grade/",
    json={"grade": "Kindergarten"}
)
if response.status_code == 200:
    data = response.json()
    print(f"   ✅ Got {len(data.get('words', []))} words for Kindergarten")
else:
    print(f"   ❌ Failed: {response.text}")

# Test 3: Try to register a test user
print("\n3️⃣ Creating test user...")
test_email = f"testuser_{int(__import__('time').time())}@test.com"
test_password = "TestPass123!"

response = requests.post(
    f"{BASE_URL}/register/",
    json={
        "idToken": "dummy",  # Will be ignored for registration
        "email": test_email,
        "name": "Test User",
        "password": test_password
    }
)

if response.status_code == 200:
    user_data = response.json()
    print(f"   ✅ User created: {test_email}")
    user_id = user_data.get("user_id")
else:
    print(f"   ❌ Registration failed: {response.text}")
    exit(1)

# Test 4: Login
print("\n4️⃣ Logging in...")
response = requests.post(
    f"{BASE_URL}/login",
    json={"email": test_email, "password": test_password}
)

if response.status_code == 200:
    login_data = response.json()
    id_token = login_data.get("id_token")
    print(f"   ✅ Login successful!")
else:
    print(f"   ❌ Login failed: {response.text}")
    exit(1)

# Test 5: Add a child
print("\n5️⃣ Adding test child...")
response = requests.post(
    f"{BASE_URL}/add_child/",
    json={
        "idToken": id_token,
        "name": "Test Child",
        "age": 6,
        "grade": "Kindergarten"
    }
)

if response.status_code == 200:
    child_data = response.json()
    child_id = child_data.get("child_id")
    print(f"   ✅ Child created: {child_id}")
else:
    print(f"   ❌ Add child failed: {response.text}")
    exit(1)

# ==================== SPEAKING API TESTS ====================

print("\n" + "="*60)
print("🎤 SPEAKING API TESTS")
print("="*60)

# Test 6: Get Speaking Sentence
print("\n6️⃣ Testing /speaking/get_sentence/...")
response = requests.post(
    f"{BASE_URL}/speaking/get_sentence/",
    json={
        "idToken": id_token,
        "child_id": child_id,
        "grade": "Kindergarten"
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"   ✅ Got sentence!")
    print(f"      ID: {data.get('sentence_id')}")
    print(f"      Sentence: {data.get('sentence')}")
    print(f"      Words: {data.get('word_count')}")
    print(f"      Difficulty: {data.get('difficulty')}")
    print(f"      Has Audio: {'Yes' if data.get('audio_base64') else 'No'}")
    sentence_for_test = data.get('sentence')
    sentence_id = data.get('sentence_id')
else:
    print(f"   ❌ Failed: {response.text}")
    sentence_for_test = "The cat sat on the mat."
    sentence_id = "k1"

# Test 7: Get All Sentences
print("\n7️⃣ Testing /speaking/get_all_sentences/...")
response = requests.post(
    f"{BASE_URL}/speaking/get_all_sentences/",
    json={
        "idToken": id_token,
        "child_id": child_id,
        "grade": "Kindergarten"
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"   ✅ Got {data.get('total_sentences')} sentences")
    for s in data.get('sentences', [])[:3]:
        print(f"      - {s.get('sentence')}")
else:
    print(f"   ❌ Failed: {response.text}")

# Test 8: Analyze Speaking (Perfect Speech)
print("\n8️⃣ Testing /speaking/analyze/ (Perfect Speech)...")
response = requests.post(
    f"{BASE_URL}/speaking/analyze/",
    json={
        "idToken": id_token,
        "child_id": child_id,
        "grade": "Kindergarten",
        "original_sentence": "The cat sat on the mat.",
        "transcribed_text": "The cat sat on the mat.",
        "duration_seconds": 3.5,
        "word_timestamps": [
            {"word": "The", "start": 0.0, "end": 0.3},
            {"word": "cat", "start": 0.4, "end": 0.6},
            {"word": "sat", "start": 0.7, "end": 0.9},
            {"word": "on", "start": 1.0, "end": 1.1},
            {"word": "the", "start": 1.2, "end": 1.3},
            {"word": "mat", "start": 1.4, "end": 1.6}
        ]
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"   ✅ Analysis complete!")
    print(f"      Method: {data.get('analysis_method', 'N/A')}")
    
    pron = data.get('pronunciation_analysis', {})
    print(f"      Pronunciation: {pron.get('score', pron.get('accuracy_level', 'N/A'))}")
    
    rate = data.get('speaking_rate_analysis', {})
    print(f"      Speaking Rate: {rate.get('wpm', 'N/A')} WPM - {rate.get('status', 'N/A')}")
    
    fluency = data.get('fluency_analysis', {})
    print(f"      Fluency: {fluency.get('score', fluency.get('fluency_score', 'N/A'))}")
    
    grammar = data.get('grammar_analysis', {})
    print(f"      Grammar: {grammar.get('score', grammar.get('grammar_score', 'N/A'))}")
    
    eval_data = data.get('evaluation', {})
    print(f"      Overall: {eval_data.get('overall_score', eval_data.get('score', 'N/A'))}")
    print(f"      Status: {eval_data.get('status', 'N/A')}")
    print(f"      Level: {eval_data.get('level', 'N/A')}")
else:
    print(f"   ❌ Failed: {response.text}")

# Test 9: Analyze Speaking (With Errors)
print("\n9️⃣ Testing /speaking/analyze/ (With Errors)...")
response = requests.post(
    f"{BASE_URL}/speaking/analyze/",
    json={
        "idToken": id_token,
        "child_id": child_id,
        "grade": "Kindergarten",
        "original_sentence": "The cat sat on the mat.",
        "transcribed_text": "Da cat sit on da mat.",  # Errors!
        "duration_seconds": 5.0,
        "word_timestamps": []
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"   ✅ Analysis complete!")
    
    eval_data = data.get('evaluation', {})
    print(f"      Overall: {eval_data.get('overall_score', eval_data.get('score', 'N/A'))}")
    print(f"      Status: {eval_data.get('status', 'N/A')} (Should be lower due to errors)")
    
    pron = data.get('pronunciation_analysis', {})
    errors = pron.get('mispronounced', pron.get('mispronounced_words', []))
    if errors:
        print(f"      Errors detected:")
        for e in errors[:3]:
            print(f"         - '{e.get('expected')}' → '{e.get('heard')}'")
else:
    print(f"   ❌ Failed: {response.text}")

# Test 10: Submit Speaking Test
print("\n🔟 Testing /speaking/submit/...")
response = requests.post(
    f"{BASE_URL}/speaking/submit/",
    json={
        "idToken": id_token,
        "child_id": child_id,
        "grade": "Kindergarten",
        "sentence_id": sentence_id,
        "original_sentence": sentence_for_test,
        "audio_base64": "",
        "transcribed_text": sentence_for_test,
        "duration_seconds": 4.0
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"   ✅ Test submitted!")
    print(f"      Score ID: {data.get('score_id')}")
    print(f"      Method: {data.get('analysis_method')}")
    print(f"      Message: {data.get('message')}")
else:
    print(f"   ❌ Failed: {response.text}")

# Test 11: Get Complete Results
print("\n1️⃣1️⃣ Testing /speaking/complete_result/...")
response = requests.post(
    f"{BASE_URL}/speaking/complete_result/",
    json={
        "idToken": id_token,
        "child_id": child_id,
        "grade": "Kindergarten"
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"   ✅ Got results!")
    print(f"      Tests Completed: {data.get('tests_completed')}")
    
    summary = data.get('parent_summary', {})
    print(f"      Overall Score: {summary.get('overall_score')}")
    print(f"      Level: {summary.get('level')}")
    print(f"      Strengths: {summary.get('strengths')}")
    print(f"      Focus Areas: {summary.get('focus_areas')}")
    
    band = summary.get('grade_band', {})
    print(f"      Placement: {band.get('placement')}")
else:
    print(f"   ❌ Failed: {response.text}")

# Test 12: Test all grades
print("\n1️⃣2️⃣ Testing all grades...")
for grade in ["Kindergarten", "First", "Second", "Third"]:
    response = requests.post(
        f"{BASE_URL}/speaking/get_sentence/",
        json={
            "idToken": id_token,
            "child_id": child_id,
            "grade": grade
        }
    )
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ {grade}: {data.get('sentence')[:50]}...")
    else:
        print(f"   ❌ {grade}: Failed")

# Summary
print("\n" + "="*60)
print("📊 TEST COMPLETE!")
print("="*60)
print(f"Test User: {test_email}")
print(f"Test Password: {test_password}")
print("="*60)
