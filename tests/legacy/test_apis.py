"""Test all Speaking APIs"""
import requests
import base64

BASE_URL = 'http://localhost:8000'

print('='*60)
print('TESTING ALL SPEAKING APIs')
print('='*60)

# Test 1: Server health
print('\n1. Server Health...')
try:
    r = requests.get(f'{BASE_URL}/docs', timeout=5)
    print(f'   Status: {r.status_code} - Server is running!')
except Exception as e:
    print(f'   ERROR: Server not running - {e}')
    exit(1)

# Test 2: Login
print('\n2. Login...')
r = requests.post(f'{BASE_URL}/login/', json={
    'email': 'rajdandeepak@gmail.com',
    'password': 'Test@123'
})
if r.status_code == 200:
    data = r.json()
    token = data.get('id_token')
    print(f'   SUCCESS!')
else:
    print(f'   FAILED: {r.text}')
    exit(1)

# Test 3: Get children
print('\n3. Get Children...')
r = requests.post(f'{BASE_URL}/get_children/', json={'idToken': token})
child_id = None
if r.status_code == 200:
    children = r.json()
    print(f'   Response type: {type(children).__name__}')
    # Handle both dict and list formats
    if isinstance(children, dict):
        child_id = list(children.keys())[0] if children else None
        if child_id:
            child_info = children[child_id]
            child_name = child_info.get('name', 'Unknown') if isinstance(child_info, dict) else 'Unknown'
    elif isinstance(children, list) and len(children) > 0:
        first_child = children[0]
        if isinstance(first_child, dict):
            child_id = first_child.get('child_id')
            child_name = first_child.get('name', 'Unknown')
        else:
            child_id = str(first_child)
            child_name = 'Unknown'
    
    if child_id:
        print(f'   Found children, using: {child_id[:30]}...')
else:
    print(f'   FAILED: {r.text}')

if not child_id:
    print('   Creating test child...')
    r = requests.post(f'{BASE_URL}/add_child/', json={
        'idToken': token, 'name': 'TestChild', 'age': 6, 'grade': 'Kindergarten'
    })
    if r.status_code == 200:
        child_id = r.json().get('child_id')
        print(f'   Created: {child_id}')

# Test 4: Get Speaking Sentence
print('\n4. GET /speaking/get_sentence/...')
r = requests.post(f'{BASE_URL}/speaking/get_sentence/', json={
    'idToken': token,
    'child_id': child_id,
    'grade': 'Kindergarten'
})
if r.status_code == 200:
    data = r.json()
    print(f'   Sentence: {data.get("sentence")}')
    print(f'   Has Audio: {"Yes" if data.get("audio_base64") else "No"}')
    sentence_id = data.get('sentence_id')
    original = data.get('sentence')
else:
    print(f'   FAILED: {r.text[:200]}')
    sentence_id, original = 'k1', 'The cat sat on the mat.'

# Test 5: Get All Sentences
print('\n5. GET /speaking/get_all_sentences/...')
r = requests.post(f'{BASE_URL}/speaking/get_all_sentences/', json={
    'idToken': token,
    'child_id': child_id,
    'grade': 'First'
})
if r.status_code == 200:
    data = r.json()
    print(f'   Total: {data.get("total_sentences")} sentences for First grade')
else:
    print(f'   FAILED: {r.text[:200]}')

# Test 6: Analyze (without real audio - will fail but tests endpoint)
print('\n6. POST /speaking/analyze/ (testing endpoint)...')
fake_audio = base64.b64encode(b'fake audio data').decode()
r = requests.post(f'{BASE_URL}/speaking/analyze/', json={
    'idToken': token,
    'child_id': child_id,
    'grade': 'Kindergarten',
    'original_sentence': original,
    'audio_base64': fake_audio,
    'audio_format': 'mp3'
})
print(f'   Status: {r.status_code}')
if r.status_code == 200:
    print('   Analysis returned successfully!')
elif r.status_code == 500:
    err = r.json().get('detail', '')
    if 'Transcription failed' in err or 'OpenAI' in err:
        print(f'   Expected error (fake audio): {err[:80]}...')
    else:
        print(f'   Error: {err[:80]}')
else:
    print(f'   Response: {r.text[:150]}')

# Test 7: Complete Result
print('\n7. GET /speaking/complete_result/...')
r = requests.post(f'{BASE_URL}/speaking/complete_result/', json={
    'idToken': token,
    'child_id': child_id,
    'grade': 'Kindergarten'
})
print(f'   Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'   Tests completed: {data.get("tests_completed")}')
elif r.status_code == 404:
    print('   No results yet (expected for new child)')
else:
    print(f'   Response: {r.text[:100]}')

# Test all grades
print('\n8. Testing all grades...')
for grade in ['Kindergarten', 'First', 'Second', 'Third']:
    r = requests.post(f'{BASE_URL}/speaking/get_sentence/', json={
        'idToken': token,
        'child_id': child_id,
        'grade': grade
    })
    if r.status_code == 200:
        sent = r.json().get('sentence', '')[:40]
        print(f'   {grade}: {sent}...')
    else:
        print(f'   {grade}: FAILED')

print('\n' + '='*60)
print('ALL API TESTS COMPLETED!')
print('='*60)
