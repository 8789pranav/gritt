"""
Test Logic API 404 Behavior
Verifies that the API returns 404 (not 200) when results are not found
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"


def login(email: str, password: str) -> str:
    """Login and get ID token"""
    url = f"{BASE_URL}/login/"
    payload = {"email": email, "password": password}
    
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("idToken")
    else:
        raise Exception(f"Login failed: {response.status_code}")


def test_404_on_no_results():
    """Test that API returns 404 when no results are found"""
    print("\n" + "="*80)
    print("TEST: Verify 404 Response When No Results Found")
    print("="*80)
    
    # Login
    print("\n1️⃣  Logging in...")
    id_token = login(EMAIL, PASSWORD)
    print("   ✅ Logged in successfully")
    
    # Test with a grade that likely has no results
    # Or use a fake child ID that exists but has no test data
    print("\n2️⃣  Testing /logic/complete_result/ with no data...")
    
    url = f"{BASE_URL}/logic/complete_result/"
    payload = {
        "idToken": id_token,
        "child_id": CHILD_ID,
        "grade": "Third"  # Try a grade that might not have results
    }
    
    print(f"   📡 POST {url}")
    print(f"   📤 Request: child_id={CHILD_ID}, grade=Third")
    
    response = requests.post(url, json=payload)
    
    print(f"\n   📥 Response Status: {response.status_code}")
    
    if response.status_code == 404:
        print("   ✅ CORRECT: API returns 404 when no results found")
        try:
            data = response.json()
            print(f"   📄 Error Detail: {data.get('detail', 'N/A')}")
        except:
            pass
        return True
    elif response.status_code == 200:
        print("   ❌ INCORRECT: API returns 200 instead of 404")
        try:
            data = response.json()
            print(f"   📄 Response: {json.dumps(data, indent=2)}")
            if data.get("success") == False:
                print("   ⚠️  Response has success:false but status is 200 (should be 404)")
        except:
            pass
        return False
    else:
        print(f"   ⚠️  Unexpected status code: {response.status_code}")
        return False


def test_200_on_found_results():
    """Test that API returns 200 when results are found"""
    print("\n" + "="*80)
    print("TEST: Verify 200 Response When Results Are Found")
    print("="*80)
    
    # Login
    print("\n1️⃣  Logging in...")
    id_token = login(EMAIL, PASSWORD)
    print("   ✅ Logged in successfully")
    
    # First, submit a test to ensure we have data
    print("\n2️⃣  Submitting a test first...")
    
    # Get test
    get_url = f"{BASE_URL}/logic/get_test/"
    get_payload = {
        "idToken": id_token,
        "child_id": CHILD_ID,
        "grade": "Kindergarten"
    }
    
    response = requests.post(get_url, json=get_payload)
    if response.status_code != 200:
        print(f"   ❌ Failed to get test: {response.status_code}")
        return False
    
    test_data = response.json()
    items = test_data.get("items", [])
    print(f"   ✅ Got {len(items)} test items")
    
    # Submit test
    import random
    submit_url = f"{BASE_URL}/logic/submit_test/"
    submit_payload = {
        "idToken": id_token,
        "child_id": CHILD_ID,
        "grade": "Kindergarten",
        "responses": [
            {
                "item_id": item["item_id"],
                "selected_answer_index": random.randint(0, len(item["options"]) - 1),
                "response_time_seconds": random.randint(5, 30),
                "attempts": 1,
                "self_corrected": False
            }
            for item in items
        ]
    }
    
    response = requests.post(submit_url, json=submit_payload)
    if response.status_code != 200:
        print(f"   ❌ Failed to submit test: {response.status_code}")
        return False
    
    print(f"   ✅ Test submitted successfully")
    
    # Now get complete result
    print("\n3️⃣  Getting complete result...")
    
    result_url = f"{BASE_URL}/logic/complete_result/"
    result_payload = {
        "idToken": id_token,
        "child_id": CHILD_ID,
        "grade": "Kindergarten"
    }
    
    response = requests.post(result_url, json=result_payload)
    
    print(f"   📥 Response Status: {response.status_code}")
    
    if response.status_code == 200:
        print("   ✅ CORRECT: API returns 200 when results are found")
        try:
            data = response.json()
            print(f"   📊 Score: {data.get('summary', {}).get('correct_answers', 'N/A')}/{data.get('summary', {}).get('total_items', 'N/A')}")
            print(f"   🎯 Level: {data.get('parent_summary', {}).get('performance_level', 'N/A')}")
        except:
            pass
        return True
    elif response.status_code == 404:
        print("   ❌ INCORRECT: API returns 404 even though results exist")
        return False
    else:
        print(f"   ⚠️  Unexpected status code: {response.status_code}")
        return False


def main():
    """Run all 404 behavior tests"""
    print("\n" + "🧪"*40)
    print("LOGIC API 404 BEHAVIOR TESTS")
    print("🧪"*40)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Child ID: {CHILD_ID}")
    
    results = {}
    
    try:
        # Test 1: 200 when results found (run first to create data)
        results["200_on_found"] = test_200_on_found_results()
        
        # Test 2: 404 when no results
        results["404_on_not_found"] = test_404_on_no_results()
        
    except Exception as e:
        print(f"\n❌ Test suite error: {str(e)}")
        return 1
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n📊 Results: {passed}/{total} tests passed\n")
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name.replace('_', ' ').title()}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        print("\n✅ API correctly returns:")
        print("   - 200 when results are found")
        print("   - 404 when no results are found")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
