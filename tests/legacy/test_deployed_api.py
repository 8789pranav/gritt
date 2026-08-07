"""
Test Deployed API - All Endpoints
"""
import requests
import time

BASE_URL = 'https://nvupmmyd66.us-east-1.awsapprunner.com'

# Test credentials
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"

session = {"idToken": None, "childId": None}

def print_header(text):
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def print_result(success, message):
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")

# ============================================================
# TEST 1: LOGIN
# ============================================================
def test_login():
    print_header("TEST 1: LOGIN")
    response = requests.post(f"{BASE_URL}/login", json={"email": EMAIL, "password": PASSWORD})
    if response.status_code == 200:
        data = response.json()
        session["idToken"] = data.get("id_token")
        print_result(True, f"Login successful!")
        return True
    print_result(False, f"Login failed: {response.status_code} - {response.text[:100]}")
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
            print_result(True, f"Found {len(children)} children. Using: {session['childId'][:20]}...")
            return True
    print_result(False, f"Failed: {response.status_code}")
    return False

# ============================================================
# TEST 3: GRADE WORDS
# ============================================================
def test_grade():
    print_header("TEST 3: GET GRADE WORDS")
    response = requests.post(f"{BASE_URL}/grade/", json={"grade": "Kindergarten"})
    if response.status_code == 200:
        data = response.json()
        words = data.get("words", [])
        print_result(True, f"Got {len(words)} words for Kindergarten")
        return True
    print_result(False, f"Failed: {response.status_code}")
    return False

# ============================================================
# TEST 4: GENERATE ALL GRADE AUDIO
# ============================================================
def test_generate_audio():
    print_header("TEST 4: GENERATE ALL GRADE AUDIO")
    response = requests.post(f"{BASE_URL}/generate_all_grade_audio/", json={"grade": "Kindergarten"}, timeout=120)
    if response.status_code == 200:
        data = response.json()
        audio_files = data.get("audio_files", [])
        print_result(True, f"Got {len(audio_files)} audio files")
        if audio_files:
            first = audio_files[0]
            print(f"   Sample: '{first.get('word')}' - {len(first.get('word_audio', ''))} chars")
        return True
    print_result(False, f"Failed: {response.status_code} - {response.text[:100]}")
    return False

# ============================================================
# TEST 5: SPEAKING - GET SENTENCE
# ============================================================
def test_speaking_get_sentence():
    print_header("TEST 5: SPEAKING - GET SENTENCE")
    response = requests.post(f"{BASE_URL}/speaking/get_sentence/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    })
    if response.status_code == 200:
        data = response.json()
        print_result(True, f"Sentence: '{data.get('sentence')}'")
        return True
    print_result(False, f"Failed: {response.status_code} - {response.text[:100]}")
    return False

# ============================================================
# TEST 6: SPEAKING - GET ALL SENTENCES
# ============================================================
def test_speaking_get_all():
    print_header("TEST 6: SPEAKING - GET ALL SENTENCES")
    response = requests.post(f"{BASE_URL}/speaking/get_all_sentences/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    })
    if response.status_code == 200:
        data = response.json()
        sentences = data.get("sentences", [])
        print_result(True, f"Got {len(sentences)} sentences")
        return True
    print_result(False, f"Failed: {response.status_code} - {response.text[:100]}")
    return False

# ============================================================
# TEST 7: COMPLETE RESULT (Spelling)
# ============================================================
def test_complete_result():
    print_header("TEST 7: COMPLETE RESULT (Spelling)")
    response = requests.post(f"{BASE_URL}/complete_result/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    })
    if response.status_code == 200:
        data = response.json()
        print_result(True, f"Got results for grade: {data.get('grade')}")
        return True
    elif response.status_code == 404:
        print_result(True, "No results yet (expected for new child)")
        return True
    print_result(False, f"Failed: {response.status_code} - {response.text[:100]}")
    return False

# ============================================================
# TEST 8: SPEAKING COMPLETE RESULT
# ============================================================
def test_speaking_complete_result():
    print_header("TEST 8: SPEAKING COMPLETE RESULT")
    response = requests.post(f"{BASE_URL}/speaking/complete_result/", json={
        "idToken": session["idToken"],
        "child_id": session["childId"],
        "grade": "First"
    })
    if response.status_code == 200:
        data = response.json()
        print_result(True, f"Got {data.get('tests_completed', 0)} speaking test results")
        return True
    elif response.status_code == 404:
        print_result(True, "No speaking results yet (expected)")
        return True
    print_result(False, f"Failed: {response.status_code} - {response.text[:100]}")
    return False

# ============================================================
# MAIN
# ============================================================
def main():
    print("\n🚀" + "="*58 + "🚀")
    print("     DEPLOYED API TEST - nvupmmyd66.us-east-1.awsapprunner.com")
    print("🚀" + "="*58 + "🚀")
    
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
    
    # Test 3: Grade
    results.append(("Grade Words", test_grade()))
    
    # Test 4: Generate Audio
    results.append(("Generate Audio", test_generate_audio()))
    
    # Test 5: Speaking Get Sentence
    results.append(("Speaking Get Sentence", test_speaking_get_sentence()))
    
    # Test 6: Speaking Get All
    results.append(("Speaking Get All", test_speaking_get_all()))
    
    # Test 7: Complete Result
    results.append(("Complete Result", test_complete_result()))
    
    # Test 8: Speaking Complete Result
    results.append(("Speaking Complete Result", test_speaking_complete_result()))
    
    # Summary
    print("\n" + "="*60)
    print("                    📊 TEST SUMMARY")
    print("="*60)
    
    passed = 0
    for name, ok in results:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")
        if ok:
            passed += 1
    
    print("-"*60)
    print(f"  Total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n  🎉 ALL TESTS PASSED!")
    print("="*60)

if __name__ == "__main__":
    main()
