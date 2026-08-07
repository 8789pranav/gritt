"""
Test Speaking APIs with REAL AUDIO using OpenAI Whisper + GPT-4o
Uses existing user credentials - includes idToken in all requests
"""
import requests
import base64
import json
import os
import wave
import struct
import math

BASE_URL = "http://localhost:8000"

# Real credentials
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"

def create_synthetic_audio(filename="test_audio.wav"):
    """Create a simple synthetic audio file for testing"""
    sample_rate = 16000
    duration = 2.0
    frequency = 440
    
    n_samples = int(sample_rate * duration)
    audio_data = []
    
    for i in range(n_samples):
        t = i / sample_rate
        sample = int(32767 * 0.3 * math.sin(2 * math.pi * frequency * t))
        audio_data.append(sample)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for sample in audio_data:
            wav_file.writeframes(struct.pack('<h', sample))
    
    with open(filename, 'rb') as f:
        audio_base64 = base64.b64encode(f.read()).decode()
    
    print(f"   ✅ Audio created: {filename}")
    return filename, audio_base64

def main():
    print("=" * 60)
    print("🎤 SPEAKING API TEST - All Endpoints")
    print("=" * 60)
    
    # 1. Check server
    print("\n1️⃣ Checking server...")
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        print(f"   ✅ Server running!")
    except Exception as e:
        print(f"   ❌ Server not running: {e}")
        return
    
    # 2. Login
    print(f"\n2️⃣ Logging in as {EMAIL}...")
    response = requests.post(f"{BASE_URL}/login/", json={
        "email": EMAIL,
        "password": PASSWORD
    })
    
    if response.status_code != 200:
        print(f"   ❌ Login failed: {response.text}")
        return
    
    login_data = response.json()
    token = login_data.get("id_token")
    user_id = login_data.get("user_id")
    print(f"   ✅ Login successful!")
    print(f"   User ID: {user_id}")
    
    # 3. Get a sentence to test
    print(f"\n3️⃣ Testing /speaking/get_sentence/...")
    response = requests.post(f"{BASE_URL}/speaking/get_sentence/", json={
        "idToken": token,
        "child_id": CHILD_ID,
        "grade": "First"
    })
    
    if response.status_code != 200:
        print(f"   ❌ Failed: {response.text}")
        return
    
    sentence_data = response.json()
    sentence_id = sentence_data.get("sentence_id")
    original_sentence = sentence_data["sentence"]
    print(f"   ✅ Got sentence!")
    print(f"      ID: {sentence_id}")
    print(f"      Sentence: {original_sentence}")
    print(f"      Word Count: {sentence_data.get('word_count')}")
    print(f"      Difficulty: {sentence_data.get('difficulty')}")
    print(f"      Has Audio: {'Yes' if sentence_data.get('audio_base64') else 'No'}")
    
    # 4. Get all sentences
    print(f"\n4️⃣ Testing /speaking/get_all_sentences/...")
    response = requests.post(f"{BASE_URL}/speaking/get_all_sentences/", json={
        "idToken": token,
        "child_id": CHILD_ID,
        "grade": "Kindergarten"
    })
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Got {data.get('total_sentences')} sentences for {data.get('grade')}")
        for s in data.get('sentences', [])[:3]:
            print(f"      - [{s.get('sentence_id')}] {s.get('sentence')[:40]}...")
    else:
        print(f"   ❌ Failed: {response.text[:200]}")
    
    # 5. Generate test audio
    print(f"\n5️⃣ Generating test audio...")
    audio_file, audio_base64 = create_synthetic_audio()
    
    # 6. Test /speaking/analyze/ (Main API - accepts base64 audio)
    print(f"\n6️⃣ Testing /speaking/analyze/ (Base64 Audio Analysis)...")
    response = requests.post(f"{BASE_URL}/speaking/analyze/", json={
        "idToken": token,
        "child_id": CHILD_ID,
        "grade": "First",
        "original_sentence": original_sentence,
        "audio_base64": audio_base64,
        "audio_format": "wav"
    })
    
    if response.status_code == 200:
        analysis = response.json()
        print(f"   ✅ Analysis complete!")
        print(f"      Method: {analysis.get('analysis_method', 'N/A')}")
        print(f"      Transcribed: '{analysis.get('transcribed_text', 'N/A')}'")
        print(f"      Duration: {analysis.get('duration_seconds', 'N/A')}s")
        
        pron = analysis.get('pronunciation', {})
        print(f"      Pronunciation: {pron.get('score', 'N/A')}")
        
        rate = analysis.get('speaking_rate', {})
        print(f"      Speaking Rate: {rate.get('wpm', 'N/A')} WPM ({rate.get('status', 'N/A')})")
        
        fluency = analysis.get('fluency', {})
        print(f"      Fluency: {fluency.get('score', 'N/A')}")
        
        grammar = analysis.get('grammar', {})
        print(f"      Grammar: {grammar.get('score', 'N/A')}")
        
        overall = analysis.get('overall', {})
        print(f"      Overall: {overall.get('score', 'N/A')} - {overall.get('level', 'N/A')}")
        
        if analysis.get('recommendation'):
            print(f"      Recommendation: {analysis.get('recommendation')[:60]}...")
    else:
        print(f"   ❌ Failed: {response.status_code}")
        print(f"      {response.text[:300]}")
    
    # 7. Test /speaking/submit/ (Save to Firebase)
    print(f"\n7️⃣ Testing /speaking/submit/ (Save to Firebase)...")
    response = requests.post(f"{BASE_URL}/speaking/submit/", json={
        "idToken": token,
        "child_id": CHILD_ID,
        "grade": "First",
        "sentence_id": sentence_id,
        "original_sentence": original_sentence,
        "audio_base64": audio_base64,
        "audio_format": "wav"
    })
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Submitted to Firebase!")
        print(f"      Score ID: {data.get('score_id', 'N/A')}")
        print(f"      Method: {data.get('analysis_method', 'N/A')}")
        overall = data.get('overall', {})
        print(f"      Overall: {overall.get('score', 'N/A')} - {overall.get('level', 'N/A')}")
        print(f"      Message: {data.get('message', 'N/A')}")
    else:
        print(f"   ❌ Failed: {response.status_code}")
        print(f"      {response.text[:300]}")
    
    # 8. Get complete results
    print(f"\n8️⃣ Testing /speaking/complete_result/ (Get All Results)...")
    response = requests.post(f"{BASE_URL}/speaking/complete_result/", json={
        "idToken": token,
        "child_id": CHILD_ID
    })
    
    if response.status_code == 200:
        results = response.json()
        print(f"   ✅ Got results!")
        print(f"      Tests Completed: {results.get('tests_completed', 0)}")
        
        summary = results.get('parent_summary', {})
        print(f"      Average Score: {summary.get('average_score', 'N/A')}")
        print(f"      Level: {summary.get('level', 'N/A')}")
        print(f"      Placement: {summary.get('grade_placement', 'N/A')}")
        
        latest = results.get('latest_result', {})
        if latest:
            print(f"      Latest Sentence: {latest.get('sentence', 'N/A')[:40]}...")
            print(f"      Latest Transcribed: {latest.get('transcribed', 'N/A')[:40]}...")
    elif response.status_code == 404:
        print(f"   ⚠️ No results yet (expected for first test)")
    else:
        print(f"   ❌ Failed: {response.status_code}")
        print(f"      {response.text[:300]}")
    
    # 9. Test all grades
    print(f"\n9️⃣ Testing all grades...")
    for grade in ["Kindergarten", "First", "Second", "Third"]:
        response = requests.post(f"{BASE_URL}/speaking/get_sentence/", json={
            "idToken": token,
            "child_id": CHILD_ID,
            "grade": grade
        })
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ {grade}: {data.get('sentence')[:45]}...")
        else:
            print(f"   ❌ {grade}: Failed")
    
    # Cleanup
    if os.path.exists(audio_file):
        os.remove(audio_file)
    
    print("\n" + "=" * 60)
    print("✅ ALL SPEAKING API TESTS COMPLETE!")
    print("=" * 60)

if __name__ == "__main__":
    main()
