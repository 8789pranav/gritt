"""
Logic API Edge Cases and Error Handling Tests
Tests various edge cases, invalid inputs, and error scenarios
"""

import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"


class EdgeCaseTester:
    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url
        self.email = email
        self.password = password
        self.id_token = None
        
    def login(self) -> bool:
        """Authenticate and get ID token"""
        url = f"{self.base_url}/login/"
        payload = {"email": self.email, "password": self.password}
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                self.id_token = data.get("idToken")
                print(f"✅ Logged in successfully\n")
                return True
            else:
                print(f"❌ Login failed: {response.status_code}\n")
                return False
        except Exception as e:
            print(f"❌ Login error: {str(e)}\n")
            return False
    
    def test_invalid_token(self):
        """Test with invalid authentication token"""
        print("="*80)
        print("TEST 1: Invalid Authentication Token")
        print("="*80)
        
        url = f"{self.base_url}/logic/get_test/"
        payload = {
            "idToken": "invalid_token_12345",
            "child_id": CHILD_ID,
            "grade": "Kindergarten"
        }
        
        try:
            response = requests.post(url, json=payload)
            print(f"📡 Request: Invalid token")
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code in [401, 403]:
                print(f"✅ Correctly rejected invalid token")
                return True
            else:
                print(f"❌ Expected 401/403, got {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_invalid_grade(self):
        """Test with invalid grade level"""
        print("\n" + "="*80)
        print("TEST 2: Invalid Grade Level")
        print("="*80)
        
        url = f"{self.base_url}/logic/get_test/"
        invalid_grades = ["Grade5", "InvalidGrade", "999", "", None]
        
        results = []
        for grade in invalid_grades:
            payload = {
                "idToken": self.id_token,
                "child_id": CHILD_ID,
                "grade": grade if grade is not None else "null"
            }
            
            try:
                response = requests.post(url, json=payload)
                print(f"\n📡 Testing grade: '{grade}'")
                print(f"📥 Status: {response.status_code}")
                
                if response.status_code == 400:
                    print(f"✅ Correctly rejected invalid grade")
                    results.append(True)
                else:
                    print(f"❌ Expected 400, got {response.status_code}")
                    results.append(False)
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                results.append(False)
        
        return all(results)
    
    def test_invalid_child_id(self):
        """Test with invalid child ID"""
        print("\n" + "="*80)
        print("TEST 3: Invalid Child ID")
        print("="*80)
        
        url = f"{self.base_url}/logic/get_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": "invalid-child-id-12345",
            "grade": "Kindergarten"
        }
        
        try:
            response = requests.post(url, json=payload)
            print(f"📡 Request: Invalid child ID")
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code in [400, 404]:
                print(f"✅ Correctly rejected invalid child ID")
                return True
            else:
                print(f"❌ Expected 400/404, got {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_invalid_item_id(self):
        """Test submitting response with invalid item ID"""
        print("\n" + "="*80)
        print("TEST 4: Invalid Item ID in Response")
        print("="*80)
        
        url = f"{self.base_url}/logic/submit_response/"
        payload = {
            "idToken": self.id_token,
            "child_id": CHILD_ID,
            "item_id": "invalid_item_id_xyz",
            "selected_answer_index": 0,
            "response_time_seconds": 10,
            "attempts": 1
        }
        
        try:
            response = requests.post(url, json=payload)
            print(f"📡 Request: Invalid item ID")
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 400:
                print(f"✅ Correctly rejected invalid item ID")
                return True
            else:
                print(f"❌ Expected 400, got {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_out_of_range_answer(self):
        """Test submitting answer index out of range"""
        print("\n" + "="*80)
        print("TEST 5: Out of Range Answer Index")
        print("="*80)
        
        # First get a valid test
        url = f"{self.base_url}/logic/get_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": CHILD_ID,
            "grade": "Kindergarten"
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                print(f"❌ Failed to get test items")
                return False
            
            data = response.json()
            items = data.get("items", [])
            if not items:
                print(f"❌ No items returned")
                return False
            
            item = items[0]
            num_options = len(item["options"])
            
            # Try submitting with out-of-range index
            url = f"{self.base_url}/logic/submit_response/"
            payload = {
                "idToken": self.id_token,
                "child_id": CHILD_ID,
                "item_id": item["item_id"],
                "selected_answer_index": num_options + 10,  # Way out of range
                "response_time_seconds": 10,
                "attempts": 1
            }
            
            response = requests.post(url, json=payload)
            print(f"📡 Request: Answer index {num_options + 10} (valid range: 0-{num_options-1})")
            print(f"📥 Status: {response.status_code}")
            
            # The API might accept it and just mark it wrong, or reject it
            if response.status_code in [200, 400]:
                print(f"✅ API handled out-of-range index appropriately")
                return True
            else:
                print(f"⚠️  Unexpected status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_negative_response_time(self):
        """Test submitting negative response time"""
        print("\n" + "="*80)
        print("TEST 6: Negative Response Time")
        print("="*80)
        
        # Get a valid item first
        url = f"{self.base_url}/logic/get_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": CHILD_ID,
            "grade": "Kindergarten"
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                print(f"❌ Failed to get test items")
                return False
            
            data = response.json()
            items = data.get("items", [])
            if not items:
                print(f"❌ No items returned")
                return False
            
            item = items[0]
            
            # Submit with negative time
            url = f"{self.base_url}/logic/submit_response/"
            payload = {
                "idToken": self.id_token,
                "child_id": CHILD_ID,
                "item_id": item["item_id"],
                "selected_answer_index": 0,
                "response_time_seconds": -10,
                "attempts": 1
            }
            
            response = requests.post(url, json=payload)
            print(f"📡 Request: Negative response time (-10)")
            print(f"📥 Status: {response.status_code}")
            
            # API might accept and sanitize, or reject
            if response.status_code in [200, 400]:
                print(f"✅ API handled negative time appropriately")
                return True
            else:
                print(f"⚠️  Unexpected status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_empty_responses_list(self):
        """Test submitting test with empty responses"""
        print("\n" + "="*80)
        print("TEST 7: Empty Responses List")
        print("="*80)
        
        url = f"{self.base_url}/logic/submit_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": CHILD_ID,
            "grade": "Kindergarten",
            "responses": []
        }
        
        try:
            response = requests.post(url, json=payload)
            print(f"📡 Request: Empty responses array")
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code in [200, 400]:
                print(f"✅ API handled empty responses appropriately")
                if response.status_code == 200:
                    data = response.json()
                    print(f"   Score: {data.get('correct_answers', 0)}/{data.get('total_items', 0)}")
                return True
            else:
                print(f"⚠️  Unexpected status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_duplicate_responses(self):
        """Test submitting duplicate responses for same item"""
        print("\n" + "="*80)
        print("TEST 8: Duplicate Item Responses")
        print("="*80)
        
        # Get a valid test first
        url = f"{self.base_url}/logic/get_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": CHILD_ID,
            "grade": "Kindergarten"
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                print(f"❌ Failed to get test items")
                return False
            
            data = response.json()
            items = data.get("items", [])
            if not items:
                print(f"❌ No items returned")
                return False
            
            item = items[0]
            
            # Submit test with duplicate item responses
            url = f"{self.base_url}/logic/submit_test/"
            payload = {
                "idToken": self.id_token,
                "child_id": CHILD_ID,
                "grade": "Kindergarten",
                "responses": [
                    {
                        "item_id": item["item_id"],
                        "selected_answer_index": 0,
                        "response_time_seconds": 10,
                        "attempts": 1
                    },
                    {
                        "item_id": item["item_id"],  # Same item again
                        "selected_answer_index": 1,
                        "response_time_seconds": 15,
                        "attempts": 2
                    }
                ]
            }
            
            response = requests.post(url, json=payload)
            print(f"📡 Request: Duplicate item responses")
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code in [200, 400]:
                print(f"✅ API handled duplicate responses appropriately")
                return True
            else:
                print(f"⚠️  Unexpected status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_missing_required_fields(self):
        """Test requests with missing required fields"""
        print("\n" + "="*80)
        print("TEST 9: Missing Required Fields")
        print("="*80)
        
        url = f"{self.base_url}/logic/get_test/"
        
        # Test missing idToken
        payload = {
            "child_id": CHILD_ID,
            "grade": "Kindergarten"
        }
        
        try:
            response = requests.post(url, json=payload)
            print(f"📡 Request: Missing idToken")
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 422:  # Pydantic validation error
                print(f"✅ Correctly rejected missing field")
            else:
                print(f"⚠️  Status: {response.status_code}")
            
            # Test missing grade
            payload = {
                "idToken": self.id_token,
                "child_id": CHILD_ID
            }
            
            response = requests.post(url, json=payload)
            print(f"\n📡 Request: Missing grade")
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 422:
                print(f"✅ Correctly rejected missing field")
                return True
            else:
                print(f"⚠️  Status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all edge case tests"""
        print("\n" + "🧪"*40)
        print("LOGIC API EDGE CASES & ERROR HANDLING TESTS")
        print("🧪"*40)
        
        if not self.login():
            print("\n❌ Cannot proceed without authentication")
            return
        
        tests = [
            ("Invalid Token", self.test_invalid_token),
            ("Invalid Grade", self.test_invalid_grade),
            ("Invalid Child ID", self.test_invalid_child_id),
            ("Invalid Item ID", self.test_invalid_item_id),
            ("Out of Range Answer", self.test_out_of_range_answer),
            ("Negative Response Time", self.test_negative_response_time),
            ("Empty Responses", self.test_empty_responses_list),
            ("Duplicate Responses", self.test_duplicate_responses),
            ("Missing Required Fields", self.test_missing_required_fields),
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
                time.sleep(0.5)
            except Exception as e:
                print(f"\n❌ Test '{test_name}' crashed: {str(e)}")
                results.append((test_name, False))
        
        # Summary
        print("\n" + "="*80)
        print("EDGE CASE TEST SUMMARY")
        print("="*80)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        print(f"\n📊 Results: {passed}/{total} tests passed\n")
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {status} - {test_name}")
        
        if passed == total:
            print(f"\n🎉 ALL EDGE CASE TESTS PASSED! 🎉")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed or had unexpected behavior")


def main():
    tester = EdgeCaseTester(BASE_URL, EMAIL, PASSWORD)
    tester.run_all_tests()


if __name__ == "__main__":
    main()
