"""Test all audio APIs on deployed App Runner"""
import requests, json, time, sys

BASE = "https://nvupmmyd66.us-east-1.awsapprunner.com"

def get_token():
    from dotenv import load_dotenv
    import os
    load_dotenv('.env')
    key = os.getenv('FIREBASE_API_KEY')
    # Try sign in first, if fails try sign up
    for endpoint in ['signInWithPassword', 'signUp']:
        r = requests.post(f'https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={key}',
                          json={'email':'testuser@grittt.com','password':'Test1234!','returnSecureToken':True})
        data = r.json()
        if 'idToken' in data:
            return data['idToken'], data['localId']
    raise Exception(f"Auth failed: {data}")

def test_endpoint(name, url, payload):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    start = time.time()
    r = requests.post(f"{BASE}{url}", json=payload, timeout=120)
    elapsed = time.time() - start
    print(f"Status: {r.status_code} | Time: {elapsed:.2f}s")
    try:
        data = r.json()
        if 'items' in data:
            print(f"Items: {len(data['items'])}")
            for item in data['items'][:3]:
                audio = item.get('question_audio_base64') or item.get('audio_base64')
                print(f"  - {item.get('item_number','?')}: q='{item.get('question_text','')[:50]}' audio={'YES' if audio else 'NO'}")
                if 'options' in item:
                    for opt in item['options'][:2]:
                        oa = opt.get('audio_base64')
                        print(f"      opt {opt['index']}: '{opt['text'][:30]}' audio={'YES' if oa else 'NO'}")
        elif 'sentences' in data:
            print(f"Sentences: {len(data['sentences'])}")
            for s in data['sentences'][:3]:
                print(f"  - {s['sentence_id']}: '{s['sentence'][:40]}' audio={'YES' if s.get('audio_base64') else 'NO'}")
        elif 'audio_files' in data:
            print(f"Audio files: {len(data['audio_files'])}")
            for f in data['audio_files'][:3]:
                print(f"  - word='{f['word']}' audio={'YES' if f.get('word_audio') else 'NO'} sent_audio={'YES' if f.get('sentence_audio') else 'NO'}")
        elif 'stories' in data:
            print(f"Stories: {len(data['stories'])}")
            for s in data['stories'][:2]:
                print(f"  - {s.get('story_id','?')}: '{s.get('title','')[:30]}' audio={'YES' if s.get('audio_base64') else 'NO'}")
        elif 'base64_audio' in data:
            print(f"Audio: {'YES' if data['base64_audio'] else 'NO'}")
        else:
            for k, v in data.items():
                if isinstance(v, str) and len(v) > 100:
                    print(f"  {k}: [{len(v)} chars]")
                elif isinstance(v, list):
                    print(f"  {k}: [{len(v)} items]")
                else:
                    print(f"  {k}: {v}")
    except:
        print(f"Raw: {r.text[:300]}")

print("Getting Firebase token...")
token, uid = get_token()
print(f"Token OK, UID: {uid}")

# Register
print("\nRegistering user...")
r = requests.post(f"{BASE}/register/", json={"idToken": token, "name": "Test", "email": "testuser@grittt.com"})
print(f"Register: {r.status_code}")

# Add child
print("Adding child...")
r = requests.post(f"{BASE}/add_child/", json={"idToken": token, "name": "Test Child", "grade": "Kindergarten", "age": 5})
print(f"Add child: {r.status_code} {r.text[:100]}")

# Get children
r = requests.post(f"{BASE}/get_children/", json={"idToken": token})
children = r.json()
print(f"Children response: {json.dumps(children, indent=2)[:300]}")
child_id = None
if isinstance(children, dict):
    # Could be {"children": [{"child_id": "..."}]} or {"child_id": "..."}
    if 'children' in children:
        for c in children['children']:
            if isinstance(c, dict):
                child_id = c.get('child_id') or c.get('id')
                break
    elif 'child_id' in children:
        child_id = children['child_id']
    else:
        # Keys that look like UUIDs
        for k in children:
            if k not in ('message',) and isinstance(children[k], dict):
                child_id = k
                break
if not child_id:
    child_id = "c6b6f9c4-8a4e-4c38-b50e-99bb7c7d1cac"  # from add_child response
print(f"Child ID: {child_id}")

# Test all audio APIs
test_endpoint("Logic Test with Audio (K-1)", "/logic/get_test_with_audio/", {
    "idToken": token, "child_id": child_id, "grade": "Kindergarten"
})

test_endpoint("Speaking All Sentences (K)", "/speaking/get_all_sentences/", {
    "idToken": token, "child_id": child_id, "grade": "Kindergarten"
})

test_endpoint("Speaking Single Sentence (K)", "/speaking/get_sentence/", {
    "idToken": token, "child_id": child_id, "grade": "Kindergarten"
})

test_endpoint("Comprehension Stories (K)", "/comprehension/get_stories/", {
    "idToken": token, "child_id": child_id, "grade": "Kindergarten"
})

test_endpoint("Spelling All Grade Audio (K)", "/generate_all_grade_audio/", {
    "idToken": token, "grade": "Kindergarten"
})

test_endpoint("Spelling Single Word", "/generate_text_audio/", {
    "idToken": token, "text": "cat"
})

print("\n\n" + "="*60)
print("ALL TESTS COMPLETE")
print("="*60)
