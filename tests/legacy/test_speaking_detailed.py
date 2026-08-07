"""
Detailed Speaking API Test Suite
Tests all 5 endpoints with real requests
"""

import requests
import base64
import json
import struct
import math
import time

BASE_URL = "http://localhost:8000"

# Test credentials (real user)
TEST_EMAIL = "rajdandeepak@gmail.com"
TEST_PASSWORD = "Test@123"
TEST_CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"

# Store tokens and IDs
session = {
    "idToken": None,
    "userId": None,
    "childId": None
}

def create_test_wav_audio(duration=2.0, frequency=440):
    """Create a simple WAV audio file with a tone"""
    sample_rate = 16000
    num_samples = int(sample_rate * duration)
    
    # Generate simple sine wave
    audio_data = []
    for i in range(num_samples):
        t = i / sample_rate
        # Silence with small noise (simulates speech-like audio)
        value = int(32767 * 0.1 * math.sin(2 * math.pi * frequency * t))
        audio_data.append(struct.pack('<h', value))
    
    audio_bytes = b''.join(audio_data)
    
    # Create WAV header
    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + len(audio_bytes),
        b'WAVE',
        b'fmt ',
        16,  # Subchunk1Size
        1,   # AudioFormat (PCM)
        1,   # NumChannels
        sample_rate,
        sample_rate * 2,  # ByteRate
        2,   # BlockAlign
        16,  # BitsPerSample
        b'data',
        len(audio_bytes)
    )
    
    return wav_header + audio_bytes

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def print_result(success, message):
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")

def print_json(data, indent=2):
    """Pretty print JSON data"""
    if isinstance(data, dict):
        # Truncate long base64 strings
        data_copy = data.copy()
        for key in data_copy:
            if isinstance(data_copy[key], str) and len(data_copy[key]) > 100:
                if 'audio' in key.lower() or 'base64' in key.lower():
                    data_copy[key] = data_copy[key][:50] + "... [TRUNCATED]"
        print(json.dumps(data_copy, indent=indent))
    else:
        print(data)

# ============================================================
# TEST 1: LOGIN
# ============================================================
def test_login():
    print_header("TEST 1: LOGIN - POST /login/")
    
    print("\n📤 Request:")
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    print_json(payload)
    
    try:
        response = requests.post(f"{BASE_URL}/login/", json=payload)
        print(f"\n📥 Response (Status: {response.status_code}):")
        
        if response.status_code == 200:
            data = response.json()
            session["idToken"] = data.get("idToken") or data.get("id_token")
            session["userId"] = data.get("localId") or data.get("user_id")
            print_json(data)
            print_result(True, "Login successful!")
            return True
        else:
            print_json(response.json())
            print_result(False, f"Login failed: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

# ============================================================
# TEST 2: GET CHILDREN (to get childId)
# ============================================================
def test_get_children():
    print_header("TEST 2: GET CHILDREN - POST /get_children/")
    
    print("\n📤 Request:")
    payload = {"idToken": session["idToken"]}
    print_json({"idToken": payload["idToken"][:50] + "..."})
    
    try:
        response = requests.post(f"{BASE_URL}/get_children/", json=payload)
        print(f"\n📥 Response (Status: {response.status_code}):")
        
        if response.status_code == 200:
            data = response.json()
            print_json(data)
            
            children = data.get("children", [])
            if children:
                session["childId"] = children[0].get("child_id") or children[0].get("id")
                print_result(True, f"Found {len(children)} child(ren). Using childId: {session['childId']}")
                return True
            else:
                print_result(False, "No children found. Please add a child first.")
                return False
        else:
            print_json(response.json())
            print_result(False, f"Failed: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

# ============================================================
# TEST 3: GET SINGLE SENTENCE
# ============================================================
def test_get_sentence():
    print_header("TEST 3: GET SENTENCE - POST /speaking/get_sentence/")
    
    print("\n📤 Request:")
    payload = {
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    }
    print_json({
        "idToken": payload["idToken"][:50] + "...",
        "child_id": payload["child_id"],
        "grade": payload["grade"]
    })
    
    try:
        response = requests.post(f"{BASE_URL}/speaking/get_sentence/", json=payload)
        print(f"\n📥 Response (Status: {response.status_code}):")
        
        data = response.json()
        print_json(data)
        
        if response.status_code == 200 and "sentence" in data:
            print_result(True, f"Got sentence: '{data.get('sentence')}'")
            print(f"   📝 Word count: {data.get('word_count')}")
            print(f"   📊 Difficulty: {data.get('difficulty')}")
            print(f"   🔊 Audio: {'Present' if data.get('audio_base64') else 'Missing'}")
            return data
        else:
            print_result(False, f"Failed: {response.status_code}")
            return None
    except Exception as e:
        print_result(False, f"Error: {e}")
        return None

# ============================================================
# TEST 4: GET ALL SENTENCES
# ============================================================
def test_get_all_sentences():
    print_header("TEST 4: GET ALL SENTENCES - POST /speaking/get_all_sentences/")
    
    for grade in ["Kindergarten", "First", "Second", "Third"]:
        print(f"\n--- Testing grade: {grade} ---")
        
        payload = {
            "idToken": session["idToken"],
            "child_id": session["childId"],
            "grade": grade
        }
        
        try:
            response = requests.post(f"{BASE_URL}/speaking/get_all_sentences/", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                sentences = data.get("sentences", [])
                print_result(True, f"{grade}: Got {len(sentences)} sentences")
                
                for s in sentences[:2]:  # Show first 2
                    print(f"      {s.get('sentence_id')}: {s.get('sentence')[:40]}...")
            else:
                print_result(False, f"{grade}: Failed - {response.status_code}")
        except Exception as e:
            print_result(False, f"{grade}: Error - {e}")
    
    return True

# ============================================================
# TEST 5: ANALYZE SPEECH (Main API)
# ============================================================
def test_analyze_speech(sentence_data):
    print_header("TEST 5: ANALYZE SPEECH - POST /speaking/analyze/")
    
    # Create test audio
    audio_bytes = create_test_wav_audio(duration=2.5)
    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
    
    sentence = sentence_data.get("sentence", "The cat sat on the mat.") if sentence_data else "The cat sat on the mat."
    
    print("\n📤 Request:")
    payload = {
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First",
        "original_sentence": sentence,
        "audio_base64": audio_base64,
        "audio_format": "wav"
    }
    print_json({
        "idToken": payload["idToken"][:50] + "...",
        "child_id": payload["child_id"],
        "grade": payload["grade"],
        "original_sentence": payload["original_sentence"],
        "audio_base64": payload["audio_base64"][:50] + "... [TRUNCATED]",
        "audio_format": payload["audio_format"]
    })
    
    try:
        print("\n⏳ Calling OpenAI Whisper + GPT-4o (this may take 5-10 seconds)...")
        start = time.time()
        response = requests.post(f"{BASE_URL}/speaking/analyze/", json=payload, timeout=60)
        elapsed = time.time() - start
        
        print(f"\n📥 Response (Status: {response.status_code}, Time: {elapsed:.2f}s):")
        
        data = response.json()
        print_json(data)
        
        if response.status_code == 200:
            print("\n📊 Analysis Summary:")
            print(f"   🎯 Transcribed: '{data.get('transcribed_text', 'N/A')}'")
            
            if "pronunciation" in data:
                print(f"   🗣️ Pronunciation Score: {data['pronunciation'].get('score', 'N/A')}")
            if "speaking_rate" in data:
                print(f"   ⏱️ Speaking Rate: {data['speaking_rate'].get('wpm', 'N/A')} WPM")
            if "fluency" in data:
                print(f"   💫 Fluency Score: {data['fluency'].get('score', 'N/A')}")
            if "overall" in data:
                print(f"   ⭐ Overall Score: {data['overall'].get('score', 'N/A')}")
                print(f"   📈 Level: {data['overall'].get('level', 'N/A')}")
            
            print_result(True, "Speech analysis completed!")
            return data
        else:
            print_result(False, f"Analysis failed: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print_result(False, "Request timed out (>60s)")
        return None
    except Exception as e:
        print_result(False, f"Error: {e}")
        return None

# ============================================================
# TEST 6: SUBMIT SPEAKING TEST
# ============================================================
def test_submit_speaking(sentence_data):
    print_header("TEST 6: SUBMIT SPEAKING TEST - POST /speaking/submit/")
    
    # Create test audio
    audio_bytes = create_test_wav_audio(duration=2.5)
    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
    
    sentence = sentence_data.get("sentence", "The cat sat on the mat.") if sentence_data else "The cat sat on the mat."
    sentence_id = sentence_data.get("sentence_id", "f1") if sentence_data else "f1"
    
    print("\n📤 Request:")
    payload = {
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First",
        "sentence_id": sentence_id,
        "original_sentence": sentence,
        "audio_base64": audio_base64,
        "audio_format": "wav"
    }
    print_json({
        "idToken": payload["idToken"][:50] + "...",
        "child_id": payload["child_id"],
        "grade": payload["grade"],
        "sentence_id": payload["sentence_id"],
        "original_sentence": payload["original_sentence"],
        "audio_base64": payload["audio_base64"][:50] + "... [TRUNCATED]",
        "audio_format": payload["audio_format"]
    })
    
    try:
        print("\n⏳ Submitting and saving to Firebase...")
        start = time.time()
        response = requests.post(f"{BASE_URL}/speaking/submit/", json=payload, timeout=60)
        elapsed = time.time() - start
        
        print(f"\n📥 Response (Status: {response.status_code}, Time: {elapsed:.2f}s):")
        
        data = response.json()
        print_json(data)
        
        if response.status_code == 200:
            print(f"\n   🔑 Score ID: {data.get('score_id', 'N/A')}")
            print(f"   💾 Saved to Firebase: Yes")
            print_result(True, "Speaking test submitted successfully!")
            return data
        else:
            print_result(False, f"Submit failed: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print_result(False, "Request timed out (>60s)")
        return None
    except Exception as e:
        print_result(False, f"Error: {e}")
        return None

# ============================================================
# TEST 7: GET COMPLETE RESULTS
# ============================================================
def test_complete_results():
    print_header("TEST 7: GET COMPLETE RESULTS - POST /speaking/complete_result/")
    
    print("\n📤 Request:")
    payload = {
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    }
    print_json({
        "idToken": payload["idToken"][:50] + "...",
        "child_id": payload["child_id"],
        "grade": payload["grade"]
    })
    
    try:
        response = requests.post(f"{BASE_URL}/speaking/complete_result/", json=payload)
        print(f"\n📥 Response (Status: {response.status_code}):")
        
        data = response.json()
        print_json(data)
        
        if response.status_code == 200:
            print(f"\n📊 Results Summary:")
            print(f"   📝 Tests Completed: {data.get('tests_completed', 0)}")
            
            if "parent_summary" in data:
                summary = data["parent_summary"]
                print(f"   📈 Average Score: {summary.get('average_score', 'N/A')}")
                print(f"   🎯 Level: {summary.get('level', 'N/A')}")
                print(f"   📍 Grade Placement: {summary.get('grade_placement', 'N/A')}")
            
            if "all_results" in data and data["all_results"]:
                print(f"\n   📋 Recent Results:")
                for r in data["all_results"][:3]:
                    print(f"      - {r.get('sentence', 'N/A')[:30]}... Score: {r.get('overall_score', 'N/A')}")
            
            print_result(True, "Complete results retrieved!")
            return data
        else:
            print_result(False, f"Failed: {response.status_code}")
            return None
    except Exception as e:
        print_result(False, f"Error: {e}")
        return None

# ============================================================
# MAIN TEST RUNNER
# ============================================================
def main():
    print("\n")
    print("🎤" + "="*68 + "🎤")
    print("     SPEAKING TEST API - DETAILED TEST SUITE")
    print("🎤" + "="*68 + "🎤")
    
    results = {
        "passed": 0,
        "failed": 0,
        "tests": []
    }
    
    # Test 1: Login
    if test_login():
        results["passed"] += 1
        results["tests"].append(("Login", "✅"))
    else:
        results["failed"] += 1
        results["tests"].append(("Login", "❌"))
        print("\n⚠️ Cannot continue without login. Exiting.")
        return
    
    # Test 2: Get Children
    if test_get_children():
        results["passed"] += 1
        results["tests"].append(("Get Children", "✅"))
    else:
        results["failed"] += 1
        results["tests"].append(("Get Children", "❌"))
        print("\n⚠️ No child found. Please add a child first.")
        return
    
    # Test 3: Get Single Sentence
    sentence_data = test_get_sentence()
    if sentence_data:
        results["passed"] += 1
        results["tests"].append(("Get Sentence", "✅"))
    else:
        results["failed"] += 1
        results["tests"].append(("Get Sentence", "❌"))
    
    # Test 4: Get All Sentences
    if test_get_all_sentences():
        results["passed"] += 1
        results["tests"].append(("Get All Sentences", "✅"))
    else:
        results["failed"] += 1
        results["tests"].append(("Get All Sentences", "❌"))
    
    # Test 5: Analyze Speech
    analysis_result = test_analyze_speech(sentence_data)
    if analysis_result:
        results["passed"] += 1
        results["tests"].append(("Analyze Speech", "✅"))
    else:
        results["failed"] += 1
        results["tests"].append(("Analyze Speech", "❌"))
    
    # Test 6: Submit Speaking Test
    submit_result = test_submit_speaking(sentence_data)
    if submit_result:
        results["passed"] += 1
        results["tests"].append(("Submit Speaking", "✅"))
    else:
        results["failed"] += 1
        results["tests"].append(("Submit Speaking", "❌"))
    
    # Test 7: Get Complete Results
    if test_complete_results():
        results["passed"] += 1
        results["tests"].append(("Complete Results", "✅"))
    else:
        results["failed"] += 1
        results["tests"].append(("Complete Results", "❌"))
    
    # Summary
    print("\n")
    print("="*70)
    print("                    📊 TEST SUMMARY")
    print("="*70)
    
    for test_name, status in results["tests"]:
        print(f"  {status} {test_name}")
    
    print("-"*70)
    total = results["passed"] + results["failed"]
    print(f"  Total: {results['passed']}/{total} tests passed")
    
    if results["failed"] == 0:
        print("\n  🎉 ALL TESTS PASSED! Speaking API is working correctly.")
    else:
        print(f"\n  ⚠️ {results['failed']} test(s) failed. Check the logs above.")
    
    print("="*70)

if __name__ == "__main__":
    main()
