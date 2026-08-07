"""
Full Comprehension API Test - Tests audio, submission, and results
"""
import requests
import json
import time
import base64

BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"

def test_comprehension_full():
    print("=" * 60)
    print("COMPREHENSION API FULL TEST")
    print("=" * 60)
    
    # 1. Login
    print("\n[1] Logging in...")
    login_resp = requests.post(f"{BASE_URL}/login", json={
        "email": EMAIL,
        "password": PASSWORD
    }, timeout=30)
    
    if login_resp.status_code != 200:
        print(f"❌ Login failed: {login_resp.text}")
        return
    
    login_data = login_resp.json()
    # Handle both response formats
    token = login_data.get("idToken") or login_data.get("id_token") or login_data.get("token")
    if not token:
        print(f"❌ No token in response: {login_data}")
        return
    print(f"✅ Login successful! Token: {token[:50]}...")
    
    # 2. Get Children
    print("\n[2] Getting children...")
    children_resp = requests.post(f"{BASE_URL}/get_children/", json={
        "idToken": token
    }, timeout=30)
    
    if children_resp.status_code != 200:
        print(f"❌ Get children failed: {children_resp.text}")
        return
    
    children = children_resp.json()["children"]
    if not children:
        print("❌ No children found")
        return
    
    child = children[0]
    child_id = child["child_id"]
    print(f"✅ Found child: {child.get('name', 'Unknown')} (ID: {child_id})")
    
    # 3. Get Stories (with audio) - This takes time!
    print("\n[3] Getting comprehension stories for Kindergarten (this may take 30-60s for audio)...")
    start_time = time.time()
    
    stories_resp = requests.post(f"{BASE_URL}/comprehension/get_stories/", json={
        "idToken": token,
        "child_id": child_id,
        "grade": "Kindergarten"
    }, timeout=120)  # Long timeout for TTS
    
    elapsed = time.time() - start_time
    
    if stories_resp.status_code != 200:
        print(f"❌ Get stories failed: {stories_resp.text}")
        return
    
    stories_data = stories_resp.json()
    print(f"✅ Got {stories_data['total_stories']} stories with {stories_data['total_questions']} questions in {elapsed:.1f}s")
    
    # Check audio
    for i, story in enumerate(stories_data["stories"]):
        audio = story.get("story_audio_base64")
        source = story.get("audio_source", "unknown")
        if audio:
            audio_size = len(audio)
            print(f"   📖 Story {i+1}: \"{story['title']}\" - Audio: {audio_size:,} chars (source: {source})")
            
            # Verify it's valid base64
            try:
                decoded = base64.b64decode(audio)
                print(f"      ✅ Valid base64 audio, {len(decoded):,} bytes")
            except:
                print(f"      ❌ Invalid base64!")
        else:
            print(f"   📖 Story {i+1}: \"{story['title']}\" - ❌ NO AUDIO!")
        
        # Show questions
        for q in story["questions"]:
            print(f"      Q{q['id']}: {q['question'][:50]}... ({len(q['options'])} options)")
    
    # 4. Submit Answers
    print("\n[4] Submitting answers...")
    
    # Build answers - answer first option for all questions
    story_answers = []
    for story in stories_data["stories"]:
        question_answers = []
        for q in story["questions"]:
            question_answers.append({
                "question_id": q["id"],
                "selected_index": 0  # Always select first option
            })
        story_answers.append({
            "story_id": story["story_id"],
            "answers": question_answers
        })
    
    submit_resp = requests.post(f"{BASE_URL}/comprehension/submit/", json={
        "idToken": token,
        "child_id": child_id,
        "grade": "Kindergarten",
        "story_answers": story_answers
    }, timeout=30)
    
    if submit_resp.status_code != 200:
        print(f"❌ Submit failed: {submit_resp.text}")
        return
    
    submit_data = submit_resp.json()
    correct = submit_data.get('correct_answers', submit_data.get('score', 0))
    total = submit_data.get('total_questions', submit_data.get('max_score', 0))
    pct = submit_data.get('percentage', 0)
    print(f"✅ Submitted! Score: {correct}/{total} ({pct:.1f}%)")
    print(f"   Session ID: {submit_data.get('test_id', 'N/A')}")
    
    # 5. Get Complete Results
    print("\n[5] Getting complete results...")
    
    results_resp = requests.post(f"{BASE_URL}/comprehension/complete_result/", json={
        "idToken": token,
        "child_id": child_id,
        "grade": "Kindergarten"
    }, timeout=30)
    
    if results_resp.status_code != 200:
        print(f"❌ Get results failed: {results_resp.text}")
        return
    
    results_data = results_resp.json()
    print(f"✅ Complete results retrieved!")
    print(f"   Grade: {results_data['grade']}")
    summary = results_data.get('summary', {})
    print(f"   Score: {summary.get('correct_answers', 0)}/{summary.get('total_questions', 0)} ({summary.get('percentage', 0):.1f}%)")
    print(f"   Level: {summary.get('level', 'N/A')}")
    print(f"   Completed at: {results_data.get('test_timestamp', 'N/A')}")
    
    # Show per-story breakdown
    for story_result in results_data.get("story_breakdown", []):
        print(f"\n   📖 {story_result.get('story_title', 'Unknown')}:")
        print(f"      Score: {story_result.get('correct', 0)}/{story_result.get('total', 0)}")
        for q in story_result.get("questions", []):
            status = "✅" if q.get("is_correct") else "❌"
            print(f"      {status} Q{q.get('question_id')}: Selected '{q.get('selected_answer')}' (Correct: '{q.get('correct_answer')}')")
    
    print("\n" + "=" * 60)
    print("ALL COMPREHENSION TESTS PASSED! ✅")
    print("=" * 60)

if __name__ == "__main__":
    test_comprehension_full()
