# ==================== SPEAKING API TEST SCRIPT ====================
# Run this file to test all speaking test endpoints
# Make sure the server is running: uvicorn main:app --reload

import requests
import json
import base64
import time

# ==================== CONFIGURATION ====================
BASE_URL = "http://localhost:8000"
HEADERS = {"Content-Type": "application/json"}

# You need to get a valid Firebase ID token for testing
# Option 1: Login with existing user
# Option 2: Use a test token

# Test credentials (update these with your test account)
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword123"

# ==================== HELPER FUNCTIONS ====================

def login_and_get_token(email: str, password: str) -> dict:
    """Login and get Firebase ID token"""
    print("\n" + "="*60)
    print("🔐 LOGGING IN...")
    print("="*60)
    
    response = requests.post(
        f"{BASE_URL}/login",
        headers=HEADERS,
        json={"email": email, "password": password}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Login successful!")
        print(f"   User ID: {data.get('user_id')}")
        return data
    else:
        print(f"❌ Login failed: {response.json()}")
        return None


def get_children(id_token: str) -> list:
    """Get list of children for the user"""
    response = requests.post(
        f"{BASE_URL}/get_children/",
        headers=HEADERS,
        json={"idToken": id_token}
    )
    
    if response.status_code == 200:
        return response.json().get("children", [])
    return []


def create_test_child(id_token: str) -> str:
    """Create a test child if none exists"""
    print("\n📝 Creating test child...")
    
    response = requests.post(
        f"{BASE_URL}/add_child/",
        headers=HEADERS,
        json={
            "idToken": id_token,
            "name": f"TestChild_{int(time.time())}",
            "age": 6,
            "grade": "Kindergarten"
        }
    )
    
    if response.status_code == 200:
        child_id = response.json().get("child_id")
        print(f"✅ Created child: {child_id}")
        return child_id
    else:
        print(f"❌ Failed to create child: {response.json()}")
        return None


# ==================== TEST FUNCTIONS ====================

def test_get_sentence(id_token: str, child_id: str, grade: str = "Kindergarten"):
    """Test: GET single sentence for speaking test"""
    print("\n" + "="*60)
    print("📖 TEST 1: /speaking/get_sentence/")
    print("="*60)
    
    payload = {
        "idToken": id_token,
        "child_id": child_id,
        "grade": grade
    }
    
    response = requests.post(
        f"{BASE_URL}/speaking/get_sentence/",
        headers=HEADERS,
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ SUCCESS!")
        print(f"   Grade: {data.get('grade')}")
        print(f"   Sentence ID: {data.get('sentence_id')}")
        print(f"   Sentence: {data.get('sentence')}")
        print(f"   Word Count: {data.get('word_count')}")
        print(f"   Difficulty: {data.get('difficulty')}")
        print(f"   Has Audio: {'Yes' if data.get('audio_base64') else 'No'}")
        print(f"   Instructions: {data.get('instructions')}")
        return data
    else:
        print(f"❌ FAILED: {response.json()}")
        return None


def test_get_all_sentences(id_token: str, child_id: str, grade: str = "Kindergarten"):
    """Test: GET all sentences for a grade"""
    print("\n" + "="*60)
    print("📚 TEST 2: /speaking/get_all_sentences/")
    print("="*60)
    
    payload = {
        "idToken": id_token,
        "child_id": child_id,
        "grade": grade
    }
    
    response = requests.post(
        f"{BASE_URL}/speaking/get_all_sentences/",
        headers=HEADERS,
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ SUCCESS!")
        print(f"   Grade: {data.get('grade')}")
        print(f"   Total Sentences: {data.get('total_sentences')}")
        print(f"   Sentences:")
        for i, sent in enumerate(data.get('sentences', [])[:3]):  # Show first 3
            print(f"      {i+1}. [{sent.get('sentence_id')}] {sent.get('sentence')}")
        if len(data.get('sentences', [])) > 3:
            print(f"      ... and {len(data.get('sentences', [])) - 3} more")
        return data
    else:
        print(f"❌ FAILED: {response.json()}")
        return None


def test_analyze_speaking(id_token: str, child_id: str, grade: str = "Kindergarten"):
    """Test: Analyze speech (without audio, just text comparison)"""
    print("\n" + "="*60)
    print("🔍 TEST 3: /speaking/analyze/")
    print("="*60)
    
    # Simulate what a child might say
    original = "The cat sat on the mat."
    transcribed = "The cat sat on the mat."  # Perfect match
    
    payload = {
        "idToken": id_token,
        "child_id": child_id,
        "grade": grade,
        "original_sentence": original,
        "transcribed_text": transcribed,
        "duration_seconds": 3.5,
        "word_timestamps": [
            {"word": "The", "start": 0.0, "end": 0.3},
            {"word": "cat", "start": 0.35, "end": 0.6},
            {"word": "sat", "start": 0.65, "end": 0.9},
            {"word": "on", "start": 0.95, "end": 1.1},
            {"word": "the", "start": 1.15, "end": 1.3},
            {"word": "mat", "start": 1.35, "end": 1.6}
        ]
    }
    
    print(f"   Original: '{original}'")
    print(f"   Transcribed: '{transcribed}'")
    print(f"   Duration: {payload['duration_seconds']}s")
    
    response = requests.post(
        f"{BASE_URL}/speaking/analyze/",
        headers=HEADERS,
        json=payload
    )
    
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ SUCCESS!")
        print(f"   Analysis Method: {data.get('analysis_method', 'N/A')}")
        
        # Pronunciation
        pron = data.get('pronunciation_analysis', {})
        print(f"\n   📢 Pronunciation:")
        print(f"      Score: {pron.get('score', pron.get('accuracy_level', 'N/A'))}")
        
        # Speaking Rate
        rate = data.get('speaking_rate_analysis', {})
        print(f"\n   ⏱️ Speaking Rate:")
        print(f"      WPM: {rate.get('wpm', 'N/A')}")
        print(f"      Status: {rate.get('status', 'N/A')}")
        
        # Fluency
        fluency = data.get('fluency_analysis', {})
        print(f"\n   🌊 Fluency:")
        print(f"      Score: {fluency.get('score', fluency.get('fluency_score', 'N/A'))}")
        
        # Grammar
        grammar = data.get('grammar_analysis', {})
        print(f"\n   📝 Grammar:")
        print(f"      Score: {grammar.get('score', grammar.get('grammar_score', 'N/A'))}")
        
        # Overall
        eval_data = data.get('evaluation', {})
        print(f"\n   🎯 Overall Evaluation:")
        print(f"      Score: {eval_data.get('overall_score', eval_data.get('score', 'N/A'))}")
        print(f"      Status: {eval_data.get('status', 'N/A')}")
        print(f"      Level: {eval_data.get('level', 'N/A')}")
        
        print(f"\n   💡 Recommendation: {data.get('recommendation', 'N/A')}")
        
        return data
    else:
        print(f"❌ FAILED: {response.json()}")
        return None


def test_analyze_with_errors(id_token: str, child_id: str, grade: str = "Kindergarten"):
    """Test: Analyze speech with pronunciation errors"""
    print("\n" + "="*60)
    print("🔍 TEST 4: /speaking/analyze/ (WITH ERRORS)")
    print("="*60)
    
    # Simulate errors
    original = "The cat sat on the mat."
    transcribed = "Da cat sit on da mat."  # Errors: The→Da, sat→sit
    
    payload = {
        "idToken": id_token,
        "child_id": child_id,
        "grade": grade,
        "original_sentence": original,
        "transcribed_text": transcribed,
        "duration_seconds": 5.0,  # Slower speech
        "word_timestamps": []
    }
    
    print(f"   Original:    '{original}'")
    print(f"   Transcribed: '{transcribed}'")
    print(f"   Expected: Lower scores due to errors")
    
    response = requests.post(
        f"{BASE_URL}/speaking/analyze/",
        headers=HEADERS,
        json=payload
    )
    
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ SUCCESS!")
        
        eval_data = data.get('evaluation', {})
        print(f"\n   🎯 Overall:")
        print(f"      Score: {eval_data.get('overall_score', eval_data.get('score', 'N/A'))}")
        print(f"      Status: {eval_data.get('status', 'N/A')}")
        
        pron = data.get('pronunciation_analysis', {})
        print(f"\n   📢 Pronunciation Issues:")
        mispronounced = pron.get('mispronounced', pron.get('mispronounced_words', []))
        for item in mispronounced[:5]:
            print(f"      - Expected: '{item.get('expected')}' → Heard: '{item.get('heard')}'")
        
        print(f"\n   💡 Recommendation: {data.get('recommendation', 'N/A')}")
        
        return data
    else:
        print(f"❌ FAILED: {response.json()}")
        return None


def test_submit_speaking(id_token: str, child_id: str, grade: str = "Kindergarten"):
    """Test: Submit speaking test (saves to database)"""
    print("\n" + "="*60)
    print("💾 TEST 5: /speaking/submit/")
    print("="*60)
    
    original = "The cat sat on the mat."
    transcribed = "The cat sat on the mat."
    
    payload = {
        "idToken": id_token,
        "child_id": child_id,
        "grade": grade,
        "sentence_id": "k1",
        "original_sentence": original,
        "audio_base64": "",  # No audio for this test
        "transcribed_text": transcribed,
        "duration_seconds": 3.5
    }
    
    print(f"   Sentence: '{original}'")
    print(f"   Saving to database...")
    
    response = requests.post(
        f"{BASE_URL}/speaking/submit/",
        headers=HEADERS,
        json=payload
    )
    
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ SUCCESS!")
        print(f"   Score ID: {data.get('score_id')}")
        print(f"   Analysis Method: {data.get('analysis_method')}")
        
        eval_data = data.get('evaluation', {})
        print(f"   Overall Score: {eval_data.get('overall_score', eval_data.get('score', 'N/A'))}")
        print(f"   Status: {eval_data.get('status', 'N/A')}")
        print(f"   Message: {data.get('message')}")
        
        return data
    else:
        print(f"❌ FAILED: {response.json()}")
        return None


def test_complete_result(id_token: str, child_id: str, grade: str = "Kindergarten"):
    """Test: Get complete speaking test results"""
    print("\n" + "="*60)
    print("📊 TEST 6: /speaking/complete_result/")
    print("="*60)
    
    payload = {
        "idToken": id_token,
        "child_id": child_id,
        "grade": grade
    }
    
    response = requests.post(
        f"{BASE_URL}/speaking/complete_result/",
        headers=HEADERS,
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ SUCCESS!")
        print(f"   Grade: {data.get('grade')}")
        print(f"   Tests Completed: {data.get('tests_completed')}")
        
        summary = data.get('parent_summary', {})
        print(f"\n   📈 Parent Summary:")
        print(f"      Overall Score: {summary.get('overall_score')}")
        print(f"      Pronunciation: {summary.get('pronunciation_score')}")
        print(f"      Speaking Rate: {summary.get('speaking_rate_score')}")
        print(f"      Fluency: {summary.get('fluency_score')}")
        print(f"      Grammar: {summary.get('grammar_score')}")
        print(f"      Level: {summary.get('level')}")
        print(f"      Strengths: {summary.get('strengths')}")
        print(f"      Focus Areas: {summary.get('focus_areas')}")
        
        band = summary.get('grade_band', {})
        print(f"\n   🎓 Grade Band:")
        print(f"      Band: {band.get('band')}")
        print(f"      Placement: {band.get('placement')}")
        print(f"      Next Step: {band.get('next_step')}")
        
        return data
    else:
        print(f"❌ FAILED: {response.json()}")
        return None


def test_different_grades(id_token: str, child_id: str):
    """Test sentences for all grades"""
    print("\n" + "="*60)
    print("🎓 TEST 7: ALL GRADES SENTENCES")
    print("="*60)
    
    grades = ["Kindergarten", "First", "Second", "Third"]
    
    for grade in grades:
        print(f"\n--- {grade} Grade ---")
        
        response = requests.post(
            f"{BASE_URL}/speaking/get_sentence/",
            headers=HEADERS,
            json={
                "idToken": id_token,
                "child_id": child_id,
                "grade": grade
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Sentence: {data.get('sentence')}")
            print(f"      Words: {data.get('word_count')}, Difficulty: {data.get('difficulty')}")
        else:
            print(f"   ❌ Failed: {response.json()}")


# ==================== MAIN TEST RUNNER ====================

def run_all_tests():
    """Run all speaking API tests"""
    print("\n" + "="*60)
    print("🚀 SPEAKING API TEST SUITE")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print("="*60)
    
    # Step 1: Login
    login_data = login_and_get_token(TEST_EMAIL, TEST_PASSWORD)
    
    if not login_data:
        print("\n⚠️  Cannot proceed without login.")
        print("   Please update TEST_EMAIL and TEST_PASSWORD in this file.")
        print("   Or create a test user first.")
        return
    
    id_token = login_data.get("id_token")
    
    # Step 2: Get or create a child
    children = get_children(id_token)
    
    if children:
        child_id = children[0].get("child_id") if isinstance(children[0], dict) else children[0].child_id
        print(f"\n✅ Using existing child: {child_id}")
    else:
        child_id = create_test_child(id_token)
        if not child_id:
            print("\n⚠️  Cannot proceed without a child account.")
            return
    
    # Step 3: Run all tests
    print("\n" + "="*60)
    print("📋 RUNNING ALL TESTS...")
    print("="*60)
    
    results = {
        "get_sentence": None,
        "get_all_sentences": None,
        "analyze_perfect": None,
        "analyze_errors": None,
        "submit": None,
        "complete_result": None,
        "all_grades": None
    }
    
    # Test 1: Get single sentence
    results["get_sentence"] = test_get_sentence(id_token, child_id)
    
    # Test 2: Get all sentences
    results["get_all_sentences"] = test_get_all_sentences(id_token, child_id)
    
    # Test 3: Analyze perfect speech
    results["analyze_perfect"] = test_analyze_speaking(id_token, child_id)
    
    # Test 4: Analyze speech with errors
    results["analyze_errors"] = test_analyze_with_errors(id_token, child_id)
    
    # Test 5: Submit speaking test
    results["submit"] = test_submit_speaking(id_token, child_id)
    
    # Test 6: Get complete results
    results["complete_result"] = test_complete_result(id_token, child_id)
    
    # Test 7: Test all grades
    test_different_grades(id_token, child_id)
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    print(f"\n   Total: {passed}/{total} tests passed")
    print("="*60)


# ==================== RUN TESTS ====================

if __name__ == "__main__":
    print("\n⚠️  BEFORE RUNNING:")
    print("   1. Make sure the server is running: uvicorn main:app --reload")
    print("   2. Update TEST_EMAIL and TEST_PASSWORD with valid credentials")
    print("   3. Or create a test user first")
    
    input("\nPress Enter to start tests...")
    
    run_all_tests()
