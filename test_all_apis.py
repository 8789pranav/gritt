"""
Complete API Test Suite for Grittt Project
Tests all endpoints including Speaking APIs with OpenAI
"""
import requests
import base64
import json
import os
import wave
import struct
import math
import time

BASE_URL = "http://localhost:8000"

# Test credentials
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"

# Store test results
test_results = []

def log_test(name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    test_results.append({"name": name, "passed": passed, "details": details})
    print(f"   {status}: {name}")
    if details and not passed:
        print(f"      Details: {details[:200]}")

def create_test_audio(filename="test_audio.wav", duration=2.0):
    """Create a simple test audio file"""
    sample_rate = 16000
    n_samples = int(sample_rate * duration)
    audio_data = []
    
    for i in range(n_samples):
        t = i / sample_rate
        sample = int(32767 * 0.3 * math.sin(2 * math.pi * 440 * t))
        audio_data.append(sample)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for sample in audio_data:
            wav_file.writeframes(struct.pack('<h', sample))
    
    with open(filename, 'rb') as f:
        audio_base64 = base64.b64encode(f.read()).decode()
    
    return filename, audio_base64

def main():
    print("=" * 70)
    print("🧪 COMPLETE API TEST SUITE - Grittt Project")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")
    print(f"Test User: {EMAIL}")
    print("=" * 70)
    
    token = None
    user_id = None
    
    # ==================== SECTION 1: SERVER & AUTH ====================
    print("\n" + "=" * 70)
    print("📡 SECTION 1: Server & Authentication")
    print("=" * 70)
    
    # Test 1.1: Server Health
    print("\n1.1 Server Health Check...")
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        log_test("Server Running", response.status_code == 200)
    except Exception as e:
        log_test("Server Running", False, str(e))
        print("\n❌ Server not running! Start with: python -m uvicorn main:app")
        return
    
    # Test 1.2: Login
    print("\n1.2 User Login...")
    try:
        response = requests.post(f"{BASE_URL}/login/", json={
            "email": EMAIL,
            "password": PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            token = data.get("id_token")
            user_id = data.get("user_id")
            log_test("Login", True, f"User ID: {user_id}")
        else:
            log_test("Login", False, response.text)
            return
    except Exception as e:
        log_test("Login", False, str(e))
        return
    
    # ==================== SECTION 2: GRADE & WORDS ====================
    print("\n" + "=" * 70)
    print("📚 SECTION 2: Grade & Word APIs")
    print("=" * 70)
    
    # Test 2.1: Get Grade Words
    print("\n2.1 Get Grade Words...")
    for grade in ["Kindergarten", "First", "Second", "Third"]:
        try:
            response = requests.post(f"{BASE_URL}/grade/", json={"grade": grade})
            if response.status_code == 200:
                data = response.json()
                word_count = len(data.get("words", []))
                log_test(f"Grade Words - {grade}", True, f"{word_count} words")
            else:
                log_test(f"Grade Words - {grade}", False, response.text)
        except Exception as e:
            log_test(f"Grade Words - {grade}", False, str(e))
    
    # ==================== SECTION 3: CHILD MANAGEMENT ====================
    print("\n" + "=" * 70)
    print("👶 SECTION 3: Child Management")
    print("=" * 70)
    
    # Test 3.1: Get Children
    print("\n3.1 Get Children...")
    try:
        response = requests.post(f"{BASE_URL}/get_children/", json={"idToken": token})
        if response.status_code == 200:
            children = response.json()
            log_test("Get Children", True, f"{len(children)} children found")
        else:
            log_test("Get Children", False, response.text)
    except Exception as e:
        log_test("Get Children", False, str(e))
    
    # Test 3.2: Get All Child Details
    print("\n3.2 Get All Child Details...")
    try:
        response = requests.post(f"{BASE_URL}/get_all_child_details/", json={"idToken": token})
        if response.status_code == 200:
            log_test("Get All Child Details", True)
        else:
            log_test("Get All Child Details", False, response.text)
    except Exception as e:
        log_test("Get All Child Details", False, str(e))
    
    # ==================== SECTION 4: TTS (Text-to-Speech) ====================
    print("\n" + "=" * 70)
    print("🔊 SECTION 4: Text-to-Speech (AWS Polly)")
    print("=" * 70)
    
    # Test 4.1: Generate Word Audio
    print("\n4.1 Generate Word Audio...")
    try:
        response = requests.post(f"{BASE_URL}/generate_text_audio/", json={
            "idToken": token,
            "text": "cat"
        })
        if response.status_code == 200:
            data = response.json()
            has_audio = bool(data.get("audio_base64"))
            log_test("Generate Word Audio", has_audio, "Audio generated" if has_audio else "No audio")
        else:
            log_test("Generate Word Audio", False, response.text)
    except Exception as e:
        log_test("Generate Word Audio", False, str(e))
    
    # Test 4.2: Generate Grade Audio
    print("\n4.2 Generate Grade Audio...")
    try:
        response = requests.post(f"{BASE_URL}/generate_all_grade_audio/", json={"grade": "Kindergarten"})
        if response.status_code == 200:
            data = response.json()
            audio_count = len(data.get("audio_data", []))
            log_test("Generate Grade Audio", audio_count > 0, f"{audio_count} audio files")
        else:
            log_test("Generate Grade Audio", False, response.text)
    except Exception as e:
        log_test("Generate Grade Audio", False, str(e))
    
    # ==================== SECTION 5: SPEAKING TEST APIs ====================
    print("\n" + "=" * 70)
    print("🎤 SECTION 5: Speaking Test APIs")
    print("=" * 70)
    
    sentence_id = None
    original_sentence = None
    
    # Test 5.1: Get Speaking Sentence
    print("\n5.1 Get Speaking Sentence...")
    try:
        response = requests.post(f"{BASE_URL}/speaking/get_sentence/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": "First"
        })
        if response.status_code == 200:
            data = response.json()
            sentence_id = data.get("sentence_id")
            original_sentence = data.get("sentence")
            has_audio = bool(data.get("audio_base64"))
            log_test("Get Speaking Sentence", True, f"'{original_sentence[:30]}...' Audio: {has_audio}")
        else:
            log_test("Get Speaking Sentence", False, response.text)
    except Exception as e:
        log_test("Get Speaking Sentence", False, str(e))
    
    # Test 5.2: Get All Speaking Sentences
    print("\n5.2 Get All Speaking Sentences...")
    try:
        response = requests.post(f"{BASE_URL}/speaking/get_all_sentences/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": "First"
        })
        if response.status_code == 200:
            data = response.json()
            sentence_count = len(data.get("sentences", []))
            log_test("Get All Speaking Sentences", sentence_count > 0, f"{sentence_count} sentences")
        else:
            log_test("Get All Speaking Sentences", False, response.text)
    except Exception as e:
        log_test("Get All Speaking Sentences", False, str(e))
    
    # Test 5.3: Speaking Analysis (Text-based - no Whisper)
    print("\n5.3 Speaking Analysis (Text-based)...")
    try:
        response = requests.post(f"{BASE_URL}/speaking/analyze/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": "First",
            "original_sentence": "The cat sat on the mat.",
            "transcribed_text": "The cat sat on the mat.",
            "duration_seconds": 3.0
        })
        if response.status_code == 200:
            data = response.json()
            overall = data.get("overall_score", 0)
            log_test("Speaking Analysis (Perfect)", True, f"Score: {overall}")
        else:
            log_test("Speaking Analysis (Perfect)", False, response.text)
    except Exception as e:
        log_test("Speaking Analysis (Perfect)", False, str(e))
    
    # Test 5.4: Speaking Analysis (With Errors)
    print("\n5.4 Speaking Analysis (With Errors)...")
    try:
        response = requests.post(f"{BASE_URL}/speaking/analyze/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": "First",
            "original_sentence": "The cat sat on the mat.",
            "transcribed_text": "Cat sat on mat.",
            "duration_seconds": 2.0
        })
        if response.status_code == 200:
            data = response.json()
            overall = data.get("overall_score", 0)
            errors = data.get("errors", [])
            log_test("Speaking Analysis (Errors)", True, f"Score: {overall}, Errors: {len(errors)}")
        else:
            log_test("Speaking Analysis (Errors)", False, response.text)
    except Exception as e:
        log_test("Speaking Analysis (Errors)", False, str(e))
    
    # Test 5.5: Create Test Audio
    print("\n5.5 Create Test Audio File...")
    audio_file, audio_base64 = create_test_audio()
    log_test("Create Test Audio", os.path.exists(audio_file), f"File: {audio_file}")
    
    # Test 5.6: Transcribe Audio (OpenAI Whisper)
    print("\n5.6 Transcribe Audio (OpenAI Whisper)...")
    try:
        response = requests.post(f"{BASE_URL}/speaking/transcribe/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": "First",
            "sentence_id": sentence_id or "f1",
            "original_sentence": original_sentence or "Test sentence.",
            "audio_base64": audio_base64,
            "transcribed_text": "",
            "duration_seconds": 2.0
        })
        if response.status_code == 200:
            data = response.json()
            method = data.get("method", "unknown")
            text = data.get("transcribed_text", "")
            log_test("Transcribe Audio (Whisper)", True, f"Method: {method}")
        elif response.status_code == 500 and "quota" in response.text.lower():
            log_test("Transcribe Audio (Whisper)", False, "OpenAI quota exceeded - add credits")
        else:
            log_test("Transcribe Audio (Whisper)", False, response.text[:100])
    except Exception as e:
        log_test("Transcribe Audio (Whisper)", False, str(e))
    
    # Test 5.7: Submit Speaking Test
    print("\n5.7 Submit Speaking Test...")
    try:
        response = requests.post(f"{BASE_URL}/speaking/submit/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": "First",
            "sentence_id": sentence_id or "f1",
            "original_sentence": original_sentence or "The cat sat on the mat.",
            "audio_base64": audio_base64,
            "transcribed_text": original_sentence or "The cat sat on the mat.",
            "duration_seconds": 3.0
        })
        if response.status_code == 200:
            data = response.json()
            score_id = data.get("score_id")
            log_test("Submit Speaking Test", True, f"Score ID: {score_id}")
        else:
            log_test("Submit Speaking Test", False, response.text[:100])
    except Exception as e:
        log_test("Submit Speaking Test", False, str(e))
    
    # Test 5.8: Transcribe File Upload
    print("\n5.8 Transcribe File Upload...")
    try:
        with open(audio_file, 'rb') as f:
            files = {'audio_file': (audio_file, f, 'audio/wav')}
            data = {
                'idToken': token,
                'child_id': CHILD_ID,
                'original_sentence': original_sentence or "Test sentence."
            }
            response = requests.post(f"{BASE_URL}/speaking/transcribe_file/", files=files, data=data)
        
        if response.status_code == 200:
            data = response.json()
            method = data.get("method", "unknown")
            log_test("Transcribe File Upload", True, f"Method: {method}")
        elif response.status_code == 500 and "quota" in response.text.lower():
            log_test("Transcribe File Upload", False, "OpenAI quota exceeded")
        else:
            log_test("Transcribe File Upload", False, response.text[:100])
    except Exception as e:
        log_test("Transcribe File Upload", False, str(e))
    
    # Test 5.9: Speaking Complete Result
    print("\n5.9 Speaking Complete Result...")
    try:
        response = requests.post(f"{BASE_URL}/speaking/complete_result/", json={
            "idToken": token,
            "child_id": CHILD_ID
        })
        if response.status_code == 200:
            data = response.json()
            tests = data.get("tests_completed", 0)
            overall = data.get("parent_summary", {}).get("overall_score", 0)
            log_test("Speaking Complete Result", True, f"Tests: {tests}, Score: {overall}")
        elif response.status_code == 404:
            log_test("Speaking Complete Result", True, "No results yet (expected)")
        else:
            log_test("Speaking Complete Result", False, response.text[:100])
    except Exception as e:
        log_test("Speaking Complete Result", False, str(e))
    
    # ==================== SECTION 6: SPELLING TEST ====================
    print("\n" + "=" * 70)
    print("📝 SECTION 6: Spelling Test APIs")
    print("=" * 70)
    
    # Test 6.1: Submit Words
    print("\n6.1 Submit Spelling Words...")
    try:
        response = requests.post(f"{BASE_URL}/submit_words/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": "Kindergarten",
            "words": [
                {"word": "cat", "user_input": "cat", "type": "regular", "time": 2.5, "hints_used": 0},
                {"word": "dog", "user_input": "dog", "type": "regular", "time": 3.0, "hints_used": 0},
                {"word": "the", "user_input": "the", "type": "sight", "time": 1.5, "hints_used": 0}
            ]
        })
        if response.status_code == 200:
            data = response.json()
            score_id = data.get("score_id")
            log_test("Submit Spelling Words", True, f"Score ID: {score_id}")
        else:
            log_test("Submit Spelling Words", False, response.text[:100])
    except Exception as e:
        log_test("Submit Spelling Words", False, str(e))
    
    # Test 6.2: Complete Result (Spelling)
    print("\n6.2 Spelling Complete Result...")
    try:
        response = requests.post(f"{BASE_URL}/complete_result/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": "Kindergarten"
        })
        if response.status_code == 200:
            data = response.json()
            accuracy = data.get("parent_summary", {}).get("overall_accuracy", 0)
            log_test("Spelling Complete Result", True, f"Accuracy: {accuracy}%")
        elif response.status_code == 404:
            log_test("Spelling Complete Result", True, "No results yet")
        else:
            log_test("Spelling Complete Result", False, response.text[:100])
    except Exception as e:
        log_test("Spelling Complete Result", False, str(e))
    
    # ==================== SECTION 7: FEEDBACK ====================
    print("\n" + "=" * 70)
    print("📋 SECTION 7: Feedback API")
    print("=" * 70)
    
    print("\n7.1 Submit Feedback...")
    try:
        response = requests.post(f"{BASE_URL}/feedback/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "q1_grade": "First",
            "q2_prior_assessments": "Yes",
            "q3_spelling_confidence": "Very confident",
            "q4_assessment_length": "Just right",
            "q5_difficulty_level": "Appropriate",
            "q6_engagement_level": "Very engaged",
            "q7_technical_issues": "No",
            "q8_results_clarity": "Very clear",
            "q9_recommendations_helpful": "Very helpful",
            "q10_information_amount": "Just right",
            "q11_overall_satisfaction": "Very satisfied",
            "q12_comments": "Great app for testing!"
        })
        if response.status_code == 200:
            log_test("Submit Feedback", True)
        else:
            log_test("Submit Feedback", False, response.text[:100])
    except Exception as e:
        log_test("Submit Feedback", False, str(e))
    
    # ==================== CLEANUP ====================
    if os.path.exists(audio_file):
        os.remove(audio_file)
    
    # ==================== SUMMARY ====================
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for t in test_results if t["passed"])
    failed = sum(1 for t in test_results if not t["passed"])
    total = len(test_results)
    
    print(f"\n   Total Tests: {total}")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   Success Rate: {(passed/total*100):.1f}%")
    
    if failed > 0:
        print("\n   Failed Tests:")
        for t in test_results:
            if not t["passed"]:
                print(f"      - {t['name']}: {t['details'][:50]}")
    
    print("\n" + "=" * 70)
    print("🏁 TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
