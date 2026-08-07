"""
Deep API Testing Script
Tests all endpoints including Comprehension APIs
"""
import requests
import json
import time
import base64

BASE_URL = "http://localhost:8000"

# Test credentials
TEST_EMAIL = "rajdandeepak@gmail.com"
TEST_PASSWORD = "Test@123"

class APITester:
    def __init__(self):
        self.id_token = None
        self.user_id = None
        self.child_id = None
        self.results = []
    
    def log(self, test_name, success, details=""):
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} | {test_name}")
        if details:
            print(f"       {details}")
        self.results.append({"test": test_name, "success": success, "details": details})
    
    def test_health(self):
        """Test if server is running"""
        try:
            resp = requests.get(f"{BASE_URL}/docs", timeout=5)
            self.log("Server Health Check", resp.status_code == 200, f"Status: {resp.status_code}")
            return resp.status_code == 200
        except Exception as e:
            self.log("Server Health Check", False, str(e))
            return False
    
    def test_login(self):
        """Test login endpoint"""
        try:
            resp = requests.post(f"{BASE_URL}/login", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            })
            if resp.status_code == 200:
                data = resp.json()
                self.id_token = data.get("id_token")
                self.user_id = data.get("user_id")
                self.log("Login", True, f"User ID: {self.user_id[:20]}...")
                return True
            else:
                self.log("Login", False, f"Status: {resp.status_code}, {resp.text[:100]}")
                return False
        except Exception as e:
            self.log("Login", False, str(e))
            return False
    
    def test_get_children(self):
        """Test get_children endpoint"""
        try:
            resp = requests.post(f"{BASE_URL}/get_children/", json={
                "idToken": self.id_token
            })
            if resp.status_code == 200:
                data = resp.json()
                children = data.get("children", [])
                if children:
                    self.child_id = children[0]["child_id"]
                    self.log("Get Children", True, f"Found {len(children)} children. Using: {children[0]['name']}")
                else:
                    self.log("Get Children", True, "No children found - will create one")
                return True
            else:
                self.log("Get Children", False, f"Status: {resp.status_code}")
                return False
        except Exception as e:
            self.log("Get Children", False, str(e))
            return False
    
    def test_add_child(self):
        """Test add_child endpoint if no children exist"""
        if self.child_id:
            self.log("Add Child", True, "Skipped - child already exists")
            return True
        try:
            resp = requests.post(f"{BASE_URL}/add_child/", json={
                "idToken": self.id_token,
                "name": "Test Child",
                "age": 6,
                "grade": "Kindergarten"
            })
            if resp.status_code == 200:
                data = resp.json()
                self.child_id = data.get("child_id")
                self.log("Add Child", True, f"Created child ID: {self.child_id[:20]}...")
                return True
            else:
                self.log("Add Child", False, f"Status: {resp.status_code}")
                return False
        except Exception as e:
            self.log("Add Child", False, str(e))
            return False
    
    def test_grade_words(self):
        """Test grade endpoint"""
        for grade in ["Kindergarten", "First", "Second", "Third"]:
            try:
                resp = requests.post(f"{BASE_URL}/grade/", json={"grade": grade})
                if resp.status_code == 200:
                    data = resp.json()
                    words = data.get("words", [])
                    self.log(f"Grade Words ({grade})", True, f"Got {len(words)} words")
                else:
                    self.log(f"Grade Words ({grade})", False, f"Status: {resp.status_code}")
            except Exception as e:
                self.log(f"Grade Words ({grade})", False, str(e))
    
    def test_speaking_get_sentences(self):
        """Test speaking get_all_sentences endpoint"""
        try:
            resp = requests.post(f"{BASE_URL}/speaking/get_all_sentences/", json={
                "idToken": self.id_token,
                "child_id": self.child_id,
                "grade": "Kindergarten"
            })
            if resp.status_code == 200:
                data = resp.json()
                sentences = data.get("sentences", [])
                has_audio = any(s.get("audio_base64") for s in sentences)
                self.log("Speaking Get Sentences", True, f"Got {len(sentences)} sentences, Audio: {has_audio}")
                return True
            else:
                self.log("Speaking Get Sentences", False, f"Status: {resp.status_code}, {resp.text[:100]}")
                return False
        except Exception as e:
            self.log("Speaking Get Sentences", False, str(e))
            return False
    
    def test_comprehension_get_stories(self):
        """Test comprehension get_stories endpoint"""
        print("\n" + "="*60)
        print("COMPREHENSION API TESTS")
        print("="*60)
        
        for grade in ["Kindergarten", "First", "Second", "Third"]:
            try:
                start = time.time()
                resp = requests.post(f"{BASE_URL}/comprehension/get_stories/", json={
                    "idToken": self.id_token,
                    "child_id": self.child_id,
                    "grade": grade
                }, timeout=120)  # Long timeout for TTS generation
                elapsed = time.time() - start
                
                if resp.status_code == 200:
                    data = resp.json()
                    stories = data.get("stories", [])
                    total_q = data.get("total_questions", 0)
                    
                    # Check audio
                    audio_sizes = []
                    for story in stories:
                        audio = story.get("story_audio_base64", "")
                        if audio:
                            audio_sizes.append(len(audio) // 1024)  # KB
                    
                    self.log(
                        f"Comprehension Get Stories ({grade})", 
                        True, 
                        f"Stories: {len(stories)}, Questions: {total_q}, Audio: {audio_sizes}KB, Time: {elapsed:.1f}s"
                    )
                else:
                    self.log(f"Comprehension Get Stories ({grade})", False, f"Status: {resp.status_code}")
            except Exception as e:
                self.log(f"Comprehension Get Stories ({grade})", False, str(e))
    
    def test_comprehension_submit(self):
        """Test comprehension submit endpoint"""
        try:
            # Submit test answers for Kindergarten
            resp = requests.post(f"{BASE_URL}/comprehension/submit/", json={
                "idToken": self.id_token,
                "child_id": self.child_id,
                "grade": "Kindergarten",
                "story_answers": [
                    {
                        "story_id": "k_story1",
                        "answers": [
                            {"question_id": "k1_q1", "selected_index": 1},  # Brown - correct
                            {"question_id": "k1_q2", "selected_index": 2},  # Yellow ball - correct
                            {"question_id": "k1_q3", "selected_index": 0},  # Fluffy - correct
                            {"question_id": "k1_q4", "selected_index": 2}   # Near window - correct
                        ]
                    },
                    {
                        "story_id": "k_story2",
                        "answers": [
                            {"question_id": "k2_q1", "selected_index": 2},  # Blue - correct
                            {"question_id": "k2_q2", "selected_index": 1},  # Butterfly - correct
                            {"question_id": "k2_q3", "selected_index": 1},  # Water - correct
                            {"question_id": "k2_q4", "selected_index": 0}   # Wrong answer
                        ]
                    }
                ]
            })
            
            if resp.status_code == 200:
                data = resp.json()
                score = data.get("correct_answers", 0)
                max_score = data.get("max_score", 8)
                pct = data.get("percentage", 0)
                level = data.get("level", "")
                self.log(
                    "Comprehension Submit", 
                    True, 
                    f"Score: {score}/{max_score} ({pct}%), Level: {level}"
                )
                return True
            else:
                self.log("Comprehension Submit", False, f"Status: {resp.status_code}, {resp.text[:200]}")
                return False
        except Exception as e:
            self.log("Comprehension Submit", False, str(e))
            return False
    
    def test_comprehension_result(self):
        """Test comprehension complete_result endpoint"""
        try:
            resp = requests.post(f"{BASE_URL}/comprehension/complete_result/", json={
                "idToken": self.id_token,
                "child_id": self.child_id,
                "grade": "Kindergarten"
            })
            
            if resp.status_code == 200:
                data = resp.json()
                summary = data.get("parent_summary", {})
                breakdown = data.get("story_breakdown", [])
                self.log(
                    "Comprehension Result", 
                    True, 
                    f"Level: {summary.get('level')}, Placement: {summary.get('grade_placement')}, Stories: {len(breakdown)}"
                )
                return True
            else:
                self.log("Comprehension Result", False, f"Status: {resp.status_code}")
                return False
        except Exception as e:
            self.log("Comprehension Result", False, str(e))
            return False
    
    def test_generate_audio(self):
        """Test audio generation endpoint"""
        try:
            resp = requests.post(f"{BASE_URL}/generate_text_audio/", json={
                "idToken": self.id_token,
                "text": "Hello, this is a test."
            })
            if resp.status_code == 200:
                data = resp.json()
                audio = data.get("base64_audio", "")
                self.log("Generate Audio", True, f"Audio size: {len(audio)//1024}KB")
                return True
            else:
                self.log("Generate Audio", False, f"Status: {resp.status_code}")
                return False
        except Exception as e:
            self.log("Generate Audio", False, str(e))
            return False
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        passed = sum(1 for r in self.results if r["success"])
        total = len(self.results)
        print(f"Passed: {passed}/{total} ({100*passed//total if total else 0}%)")
        
        failed = [r for r in self.results if not r["success"]]
        if failed:
            print("\nFailed Tests:")
            for f in failed:
                print(f"  - {f['test']}: {f['details']}")
    
    def run_all(self):
        """Run all tests"""
        print("="*60)
        print("DEEP API TESTING")
        print("="*60 + "\n")
        
        # Basic tests
        if not self.test_health():
            print("Server not running! Start with: uvicorn main:app --port 8000")
            return
        
        if not self.test_login():
            print("Login failed! Check credentials.")
            return
        
        self.test_get_children()
        self.test_add_child()
        
        if not self.child_id:
            print("No child available for testing!")
            return
        
        # Core tests
        self.test_grade_words()
        self.test_generate_audio()
        self.test_speaking_get_sentences()
        
        # Comprehension tests
        self.test_comprehension_get_stories()
        self.test_comprehension_submit()
        self.test_comprehension_result()
        
        self.print_summary()


if __name__ == "__main__":
    tester = APITester()
    tester.run_all()
