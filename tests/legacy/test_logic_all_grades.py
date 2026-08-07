"""
Logic API Testing - All Grade Levels
Tests logic assessment for all supported grades
"""

import requests
import json
import time
from typing import Dict, List

# Configuration
BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"

# All supported grades
GRADES = ["Kindergarten", "First", "Second", "Third", "K-1", "1-2", "2-3", "3-4"]


class MultiGradeLogicTester:
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
                print(f"✅ Logged in successfully")
                return True
            else:
                print(f"❌ Login failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False
    
    def test_grade(self, child_id: str, grade: str) -> Dict:
        """Test logic API for a specific grade"""
        print(f"\n{'='*80}")
        print(f"Testing Grade: {grade}")
        print(f"{'='*80}")
        
        result = {
            "grade": grade,
            "get_test": False,
            "submit_test": False,
            "complete_result": False,
            "test_details": {}
        }
        
        # 1. Get Test
        print(f"\n1️⃣  Getting test for {grade}...")
        url = f"{self.base_url}/logic/get_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": child_id,
            "grade": grade
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                result["get_test"] = True
                result["test_details"] = {
                    "test_id": data.get("test_id"),
                    "total_items": data.get("total_items"),
                    "items": data.get("items", [])
                }
                print(f"   ✅ Retrieved {data.get('total_items')} items")
                
                # Display item types
                items = data.get("items", [])
                item_types = {}
                for item in items:
                    item_type = item.get("item_type")
                    item_types[item_type] = item_types.get(item_type, 0) + 1
                
                print(f"   📝 Item Types:")
                for itype, count in item_types.items():
                    print(f"      - {itype}: {count} items")
                
            else:
                print(f"   ❌ Failed to get test: {response.status_code}")
                return result
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            return result
        
        time.sleep(0.5)
        
        # 2. Submit Test with simulated responses
        print(f"\n2️⃣  Submitting test responses...")
        import random
        
        items = result["test_details"]["items"]
        responses = []
        
        for item in items:
            responses.append({
                "item_id": item["item_id"],
                "selected_answer_index": random.randint(0, len(item["options"]) - 1),
                "response_time_seconds": random.randint(5, 40),
                "attempts": 1,
                "self_corrected": False
            })
        
        url = f"{self.base_url}/logic/submit_test/"
        payload = {
            "idToken": self.id_token,
            "child_id": child_id,
            "grade": grade,
            "responses": responses
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                result["submit_test"] = True
                result["test_details"]["score"] = {
                    "correct": data.get("correct_answers"),
                    "total": data.get("total_items"),
                    "percentage": data.get("percentage"),
                    "level": data.get("level")
                }
                print(f"   ✅ Test submitted")
                print(f"   📊 Score: {data.get('correct_answers')}/{data.get('total_items')} ({data.get('percentage'):.1f}%)")
                print(f"   🎯 Level: {data.get('level')}")
            else:
                print(f"   ❌ Failed to submit: {response.status_code}")
                return result
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            return result
        
        time.sleep(0.5)
        
        # 3. Get Complete Result
        print(f"\n3️⃣  Getting complete result...")
        url = f"{self.base_url}/logic/complete_result/"
        payload = {
            "idToken": self.id_token,
            "child_id": child_id,
            "grade": grade
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                result["complete_result"] = True
                print(f"   ✅ Complete result retrieved")
                
                parent_summary = data.get("parent_summary", {})
                print(f"   👨‍👩‍👧 Parent Summary:")
                print(f"      - Performance: {parent_summary.get('performance_level')}")
                print(f"      - Grade Placement: {parent_summary.get('grade_placement')}")
                print(f"      - Strengths: {len(parent_summary.get('strengths', []))} identified")
                print(f"      - Areas to Develop: {len(parent_summary.get('areas_to_develop', []))} identified")
            else:
                print(f"   ❌ Failed to get result: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        return result
    
    def test_all_grades(self, child_id: str):
        """Test all grade levels"""
        print("\n" + "🎓"*40)
        print("MULTI-GRADE LOGIC API TEST")
        print("🎓"*40)
        print(f"\nTesting {len(GRADES)} grade levels")
        print(f"Child ID: {child_id}")
        
        if not self.login():
            print("\n❌ Cannot proceed without authentication")
            return
        
        results = []
        
        for grade in GRADES:
            result = self.test_grade(child_id, grade)
            results.append(result)
            time.sleep(1)
        
        # Summary
        print("\n" + "="*80)
        print("MULTI-GRADE TEST SUMMARY")
        print("="*80)
        
        print(f"\n{'Grade':<15} {'Get Test':<12} {'Submit':<12} {'Result':<12} {'Items':<8} {'Score'}")
        print("-" * 80)
        
        for result in results:
            grade = result["grade"]
            get_test = "✅" if result["get_test"] else "❌"
            submit = "✅" if result["submit_test"] else "❌"
            complete = "✅" if result["complete_result"] else "❌"
            
            items = result["test_details"].get("total_items", "-")
            score = result["test_details"].get("score", {})
            score_str = f"{score.get('correct', '-')}/{score.get('total', '-')}" if score else "-"
            
            print(f"{grade:<15} {get_test:<12} {submit:<12} {complete:<12} {items:<8} {score_str}")
        
        # Statistics
        total_tests = len(results)
        successful_get = sum(1 for r in results if r["get_test"])
        successful_submit = sum(1 for r in results if r["submit_test"])
        successful_result = sum(1 for r in results if r["complete_result"])
        
        print("\n" + "="*80)
        print(f"📊 Statistics:")
        print(f"   - Total Grades Tested: {total_tests}")
        print(f"   - Successful Get Test: {successful_get}/{total_tests}")
        print(f"   - Successful Submit: {successful_submit}/{total_tests}")
        print(f"   - Successful Result: {successful_result}/{total_tests}")
        
        if successful_get == total_tests and successful_submit == total_tests:
            print(f"\n🎉 ALL GRADES TESTED SUCCESSFULLY! 🎉")
        else:
            print(f"\n⚠️  Some tests failed")


def main():
    tester = MultiGradeLogicTester(BASE_URL, EMAIL, PASSWORD)
    tester.test_all_grades(CHILD_ID)


if __name__ == "__main__":
    main()
