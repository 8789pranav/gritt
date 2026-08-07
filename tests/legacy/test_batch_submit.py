"""
Test Speaking API - Single and Batch Submissions
Tests all endpoints including the new batch feature
"""

import requests
import base64
import json
import struct
import math
import time

BASE_URL = "http://localhost:8000"

# Test credentials
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"

session = {"idToken": None, "childId": None, "userId": None}

def create_test_wav_audio(duration=2.0):
    """Create a simple WAV audio file"""
    sample_rate = 16000
    num_samples = int(sample_rate * duration)
    audio_data = []
    for i in range(num_samples):
        t = i / sample_rate
        value = int(32767 * 0.1 * math.sin(2 * math.pi * 440 * t))
        audio_data.append(struct.pack('<h', value))
    audio_bytes = b''.join(audio_data)
    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + len(audio_bytes), b'WAVE', b'fmt ', 16, 1, 1,
        sample_rate, sample_rate * 2, 2, 16, b'data', len(audio_bytes)
    )
    return wav_header + audio_bytes

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)

def print_result(success, message):
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")

# ============================================================
# TEST 1: LOGIN
# ============================================================
def test_login():
    print_header("TEST 1: LOGIN")
    response = requests.post(f"{BASE_URL}/login/", json={"email": EMAIL, "password": PASSWORD})
    if response.status_code == 200:
        data = response.json()
        session["idToken"] = data.get("id_token") or data.get("idToken")
        session["userId"] = data.get("user_id") or data.get("localId")
        print_result(True, f"Login successful! User: {session['userId'][:20]}...")
        return True
    print_result(False, f"Login failed: {response.status_code}")
    return False

# ============================================================
# TEST 2: GET CHILDREN
# ============================================================
def test_get_children():
    print_header("TEST 2: GET CHILDREN")
    response = requests.post(f"{BASE_URL}/get_children/", json={"idToken": session["idToken"]})
    if response.status_code == 200:
        data = response.json()
        children = data.get("children", [])
        if children:
            session["childId"] = children[0].get("child_id")
            print_result(True, f"Found {len(children)} children. Using: {session['childId']}")
            return True
    print_result(False, "No children found")
    return False

# ============================================================
# TEST 3: GET SENTENCE
# ============================================================
def test_get_sentence():
    print_header("TEST 3: GET SENTENCE")
    response = requests.post(f"{BASE_URL}/speaking/get_sentence/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    })
    if response.status_code == 200:
        data = response.json()
        print_result(True, f"Sentence: '{data.get('sentence')}'")
        print(f"   📝 ID: {data.get('sentence_id')}, Words: {data.get('word_count')}")
        return data
    print_result(False, f"Failed: {response.status_code}")
    return None

# ============================================================
# TEST 4: GET ALL SENTENCES
# ============================================================
def test_get_all_sentences():
    print_header("TEST 4: GET ALL SENTENCES")
    response = requests.post(f"{BASE_URL}/speaking/get_all_sentences/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    })
    if response.status_code == 200:
        data = response.json()
        sentences = data.get("sentences", [])
        print_result(True, f"Got {len(sentences)} sentences")
        for s in sentences[:3]:
            print(f"   {s['sentence_id']}: {s['sentence'][:40]}...")
        return sentences
    print_result(False, f"Failed: {response.status_code}")
    return []

# ============================================================
# TEST 5: SINGLE SUBMIT (Backward Compatible)
# ============================================================
def test_single_submit(sentence_data):
    print_header("TEST 5: SINGLE SUBMIT (Backward Compatible)")
    
    audio_bytes = create_test_wav_audio(2.5)
    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
    
    sentence = sentence_data.get("sentence", "The cat sat.") if sentence_data else "The cat sat."
    sentence_id = sentence_data.get("sentence_id", "f1") if sentence_data else "f1"
    
    print(f"   📤 Submitting: '{sentence[:40]}...'")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/speaking/submit/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First",
        "sentence_id": sentence_id,
        "original_sentence": sentence,
        "audio_base64": audio_base64,
        "audio_format": "wav"
    }, timeout=60)
    elapsed = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        print_result(True, f"Single submit OK ({elapsed:.1f}s)")
        print(f"   🔑 Score ID: {data.get('score_id')}")
        print(f"   ⭐ Overall: {data.get('overall', {}).get('score', 'N/A')}")
        return True
    print_result(False, f"Failed: {response.status_code} - {response.text[:100]}")
    return False

# ============================================================
# TEST 6: BATCH SUBMIT (NEW FEATURE)
# ============================================================
def test_batch_submit(sentences):
    print_header("TEST 6: BATCH SUBMIT (NEW FEATURE)")
    
    if not sentences or len(sentences) < 2:
        print_result(False, "Need at least 2 sentences for batch test")
        return False
    
    # Create batch with first 3 sentences
    batch_sentences = sentences[:3]
    audio_bytes = create_test_wav_audio(2.5)
    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
    
    submissions = []
    for s in batch_sentences:
        submissions.append({
            "sentence_id": s["sentence_id"],
            "original_sentence": s["sentence"],
            "audio_base64": audio_base64,
            "audio_format": "wav"
        })
    
    print(f"   📤 Submitting batch of {len(submissions)} sentences...")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/speaking/submit/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First",
        "submissions": submissions
    }, timeout=180)  # 3 minutes for batch
    elapsed = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        print_result(True, f"Batch submit OK ({elapsed:.1f}s)")
        print(f"   📊 Total submitted: {data.get('total_submitted')}")
        print(f"   📈 Average score: {data.get('average_score')}")
        
        results = data.get("results", [])
        for r in results:
            print(f"      {r.get('sentence_id')}: Score {r.get('overall_score', 'N/A')}")
        return True
    
    print_result(False, f"Failed: {response.status_code}")
    print(f"   Response: {response.text[:200]}")
    return False

# ============================================================
# TEST 7: GET COMPLETE RESULTS
# ============================================================
def test_complete_results():
    print_header("TEST 7: GET COMPLETE RESULTS")
    response = requests.post(f"{BASE_URL}/speaking/complete_result/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    })
    if response.status_code == 200:
        data = response.json()
        print_result(True, f"Got {data.get('tests_completed', 0)} test results")
        if "parent_summary" in data:
            summary = data["parent_summary"]
            print(f"   📈 Average: {summary.get('average_score')}")
            print(f"   🎯 Level: {summary.get('level')}")
        return True
    print_result(False, f"Failed: {response.status_code}")
    return False

# ============================================================
# MAIN
# ============================================================
def main():
    print("\n🎤" + "="*68 + "🎤")
    print("     SPEAKING API TEST - SINGLE & BATCH SUBMISSIONS")
    print("🎤" + "="*68 + "🎤")
    
    # Wait for server
    print("\n⏳ Waiting for server...")
    time.sleep(3)
    
    results = []
    
    # Test 1: Login
    if not test_login():
        print("\n❌ Cannot continue without login")
        return
    results.append(("Login", True))
    
    # Test 2: Get Children
    if not test_get_children():
        print("\n❌ Cannot continue without child")
        return
    results.append(("Get Children", True))
    
    # Test 3: Get Sentence
    sentence = test_get_sentence()
    results.append(("Get Sentence", sentence is not None))
    
    # Test 4: Get All Sentences
    sentences = test_get_all_sentences()
    results.append(("Get All Sentences", len(sentences) > 0))
    
    # Test 5: Single Submit
    single_ok = test_single_submit(sentence)
    results.append(("Single Submit", single_ok))
    
    # Test 6: Batch Submit
    batch_ok = test_batch_submit(sentences)
    results.append(("Batch Submit", batch_ok))
    
    # Test 7: Complete Results
    results_ok = test_complete_results()
    results.append(("Complete Results", results_ok))
    
    # Summary
    print("\n" + "="*70)
    print("                    📊 TEST SUMMARY")
    print("="*70)
    
    passed = 0
    for name, ok in results:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")
        if ok:
            passed += 1
    
    print("-"*70)
    print(f"  Total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n  🎉 ALL TESTS PASSED!")
    else:
        print(f"\n  ⚠️ {len(results) - passed} test(s) failed")
    print("="*70)

if __name__ == "__main__":
    main()
