"""
Comprehensive Logic API Testing Suite
Tests all logic assessment endpoints with proper authentication
"""

import requests
import json
import time
from typing import Dict, List, Any

# Configuration
BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"
GRADE = "Kindergarten"

class LogicAPITester:
    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url
        self.email = email
        self.password = password
        self.id_token = None
        self.test_id = None
        self.test_items = []
        self.responses = []
        
    def login(self) -> bool:
        """Authenticate and get ID token"""
        print("\n" + "="*80)
        print("STEP 1: AUTHENTICATION")
        print("="*80)
        
        url = f"{self.base_url}/login/"
        payload = {
            "email": self.email,
            "password": self.password
        }
        
        try:
            print(f"\n📡 POST {url}")
            print(f"📤 Request: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url, json=payload)
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                self.id_token = data.get("idToken")
                print(f"✅ Login successful!")
                print(f"🔑 ID Token: {self.id_token[:50]}...")
                print(f"👤 User ID: {data.get('userId')}")
                return True
            else:
                print(f"❌ Login failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error during login: {str(e)}")
            return False
    
    def test_get_logic_test(self, child_id: str, grade: str) -> bool:
        """Test GET /logic/get_test/ endpoint"""
        print("\n" + "="*80)
        print("STEP 2: GET LOGIC TEST")
        print("="*80)
        
        url = f"{self.base_url}/logic/get_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": child_id,
            "grade": grade
        }
        
        try:
            print(f"\n📡 POST {url}")
            print(f"📤 Request: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url, json=payload)
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Test retrieved successfully!")
                print(f"\n📊 Test Details:")
                print(f"   - Test ID: {data.get('test_id')}")
                print(f"   - Grade: {data.get('grade')}")
                print(f"   - Total Items: {data.get('total_items')}")
                print(f"   - Instructions: {data.get('instructions')[:80]}...")
                
                self.test_id = data.get('test_id')
                self.test_items = data.get('items', [])
                
                print(f"\n📝 Sample Items:")
                for i, item in enumerate(self.test_items[:3], 1):
                    print(f"\n   Item {i}:")
                    print(f"   - ID: {item.get('item_id')}")
                    print(f"   - Type: {item.get('item_type')}")
                    print(f"   - Question: {item.get('question_text')[:60]}...")
                    print(f"   - Difficulty: {item.get('difficulty')}")
                    print(f"   - Options: {len(item.get('options', []))} choices")
                
                if len(self.test_items) > 3:
                    print(f"\n   ... and {len(self.test_items) - 3} more items")
                
                return True
            else:
                print(f"❌ Failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_submit_single_response(self, child_id: str, item_index: int = 0) -> bool:
        """Test POST /logic/submit_response/ endpoint"""
        print("\n" + "="*80)
        print(f"STEP 3: SUBMIT SINGLE RESPONSE (Item {item_index + 1})")
        print("="*80)
        
        if not self.test_items:
            print("❌ No test items available. Run get_test first.")
            return False
        
        item = self.test_items[item_index]
        url = f"{self.base_url}/logic/submit_response/"
        
        # Simulate answering (randomly select an answer for testing)
        import random
        selected_answer = random.randint(0, len(item['options']) - 1)
        response_time = random.randint(5, 30)
        
        payload = {
            "idToken": self.id_token,
            "child_id": child_id,
            "item_id": item['item_id'],
            "selected_answer_index": selected_answer,
            "response_time_seconds": response_time,
            "attempts": 1,
            "self_corrected": False,
            "explanation_provided": None
        }
        
        try:
            print(f"\n📡 POST {url}")
            print(f"📤 Request:")
            print(f"   - Item ID: {item['item_id']}")
            print(f"   - Question: {item['question_text'][:60]}...")
            print(f"   - Selected Answer: Option {selected_answer}")
            print(f"   - Response Time: {response_time}s")
            
            response = requests.post(url, json=payload)
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"\n✅ Response submitted successfully!")
                print(f"\n📊 Result:")
                print(f"   - Correct: {'✅ YES' if data.get('is_correct') else '❌ NO'}")
                print(f"   - Correct Answer: Option {data.get('correct_answer_index')} - {data.get('correct_answer')}")
                print(f"   - Tags Earned: {', '.join(data.get('tags_earned', []))}")
                print(f"   - Feedback: {data.get('feedback')}")
                
                # Store for batch submission
                self.responses.append({
                    "item_id": item['item_id'],
                    "selected_answer_index": selected_answer,
                    "response_time_seconds": response_time,
                    "attempts": 1,
                    "self_corrected": False
                })
                
                return True
            else:
                print(f"❌ Failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_submit_complete_test(self, child_id: str, grade: str) -> bool:
        """Test POST /logic/submit_test/ endpoint"""
        print("\n" + "="*80)
        print("STEP 4: SUBMIT COMPLETE TEST")
        print("="*80)
        
        if not self.test_items:
            print("❌ No test items available. Run get_test first.")
            return False
        
        # Generate responses for all items
        import random
        all_responses = []
        
        print(f"\n📝 Generating responses for {len(self.test_items)} items...")
        for i, item in enumerate(self.test_items, 1):
            selected_answer = random.randint(0, len(item['options']) - 1)
            response_time = random.randint(5, 45)
            
            all_responses.append({
                "item_id": item['item_id'],
                "selected_answer_index": selected_answer,
                "response_time_seconds": response_time,
                "attempts": 1,
                "self_corrected": False
            })
            print(f"   Item {i}: Answer {selected_answer}, Time {response_time}s")
        
        url = f"{self.base_url}/logic/submit_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": child_id,
            "grade": grade,
            "responses": all_responses
        }
        
        try:
            print(f"\n📡 POST {url}")
            print(f"📤 Submitting {len(all_responses)} responses...")
            
            response = requests.post(url, json=payload)
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"\n✅ Test submitted successfully!")
                print(f"\n📊 Test Results:")
                print(f"   - Test ID: {data.get('test_id')}")
                print(f"   - Student ID: {data.get('student_id')}")
                print(f"   - Grade: {data.get('grade')}")
                print(f"   - Total Items: {data.get('total_items')}")
                print(f"   - Correct Answers: {data.get('correct_answers')}")
                print(f"   - Score: {data.get('score')}/{data.get('total_items')}")
                print(f"   - Percentage: {data.get('percentage'):.1f}%")
                print(f"   - Performance Level: {data.get('level')}")
                print(f"   - Message: {data.get('message')}")
                
                print(f"\n🧠 Cognitive Analysis:")
                print(f"   - Tags: {', '.join(data.get('cognitive_tags', []))}")
                print(f"   - Tag Breakdown: {json.dumps(data.get('tag_breakdown', {}), indent=6)}")
                
                print(f"\n🔍 Behavioral Signals:")
                print(f"   - Reasoning Under Load: {data.get('reasoning_under_load_detected')}")
                print(f"   - Trial and Error: {data.get('trial_and_error_detected')}")
                print(f"   - Strategy Shift Difficulty: {data.get('strategy_shift_difficulty_detected')}")
                
                return True
            else:
                print(f"❌ Failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def test_complete_result(self, child_id: str, grade: str) -> bool:
        """Test POST /logic/complete_result/ endpoint"""
        print("\n" + "="*80)
        print("STEP 5: GET COMPLETE RESULT")
        print("="*80)
        
        url = f"{self.base_url}/logic/complete_result/"
        payload = {
            "idToken": self.id_token,
            "child_id": child_id,
            "grade": grade
        }
        
        try:
            print(f"\n📡 POST {url}")
            print(f"📤 Request: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url, json=payload)
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"\n✅ Complete result retrieved successfully!")
                
                print(f"\n📊 Summary:")
                summary = data.get('summary', {})
                print(f"   - Total Items: {summary.get('total_items')}")
                print(f"   - Correct: {summary.get('correct_answers')}")
                print(f"   - Percentage: {summary.get('percentage')}%")
                print(f"   - Level: {summary.get('level')}")
                
                print(f"\n👨‍👩‍👧 Parent Summary:")
                parent = data.get('parent_summary', {})
                print(f"   - Overall Score: {parent.get('overall_score')}")
                print(f"   - Performance Level: {parent.get('performance_level')}")
                print(f"   - Grade Placement: {parent.get('grade_placement')}")
                print(f"   - Next Step: {parent.get('next_step')}")
                
                print(f"\n💪 Strengths:")
                for strength in parent.get('strengths', []):
                    print(f"   • {strength}")
                
                print(f"\n📈 Areas to Develop:")
                for area in parent.get('areas_to_develop', []):
                    print(f"   • {area}")
                
                print(f"\n💡 Recommendation:")
                print(f"   {parent.get('recommendation')}")
                
                print(f"\n⚠️  Note: {parent.get('note')}")
                
                if 'behavioral_signals' in data:
                    print(f"\n🔍 Behavioral Signals:")
                    signals = data.get('behavioral_signals', {})
                    print(f"   - Reasoning Under Load: {signals.get('reasoning_under_load')}")
                    print(f"   - Trial and Error: {signals.get('trial_and_error')}")
                    print(f"   - Strategy Shift Difficulty: {signals.get('strategy_shift_difficulty')}")
                
                print(f"\n🎯 Available Actions:")
                for action in data.get('actions', []):
                    print(f"   • {action.get('label')} ({action.get('type')})")
                
                return True
            else:
                print(f"❌ Failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def run_full_test_suite(self, child_id: str, grade: str):
        """Run complete test suite for all logic APIs"""
        print("\n" + "🧪"*40)
        print("COMPREHENSIVE LOGIC API TEST SUITE")
        print("🧪"*40)
        print(f"\nConfiguration:")
        print(f"  Base URL: {self.base_url}")
        print(f"  Email: {self.email}")
        print(f"  Child ID: {child_id}")
        print(f"  Grade: {grade}")
        
        results = {
            "login": False,
            "get_test": False,
            "submit_single": False,
            "submit_test": False,
            "complete_result": False
        }
        
        # Step 1: Login
        if not self.login():
            print("\n❌ Test suite aborted: Login failed")
            return results
        results["login"] = True
        
        time.sleep(1)
        
        # Step 2: Get Logic Test
        if not self.test_get_logic_test(child_id, grade):
            print("\n❌ Test suite aborted: Get test failed")
            return results
        results["get_test"] = True
        
        time.sleep(1)
        
        # Step 3: Submit Single Response (test first item)
        if self.test_submit_single_response(child_id, 0):
            results["submit_single"] = True
        
        time.sleep(1)
        
        # Step 4: Submit Complete Test
        if self.test_submit_complete_test(child_id, grade):
            results["submit_test"] = True
        
        time.sleep(1)
        
        # Step 5: Get Complete Result
        if self.test_complete_result(child_id, grade):
            results["complete_result"] = True
        
        # Print Summary
        print("\n" + "="*80)
        print("TEST SUITE SUMMARY")
        print("="*80)
        
        total_tests = len(results)
        passed_tests = sum(1 for v in results.values() if v)
        
        print(f"\n📊 Results: {passed_tests}/{total_tests} tests passed")
        print("\nDetailed Results:")
        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status} - {test_name.replace('_', ' ').title()}")
        
        if passed_tests == total_tests:
            print("\n🎉 ALL TESTS PASSED! 🎉")
        else:
            print(f"\n⚠️  {total_tests - passed_tests} test(s) failed")
        
        return results


def main():
    """Main test execution"""
    tester = LogicAPITester(BASE_URL, EMAIL, PASSWORD)
    results = tester.run_full_test_suite(CHILD_ID, GRADE)
    
    # Return exit code based on results
    all_passed = all(results.values())
    exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
