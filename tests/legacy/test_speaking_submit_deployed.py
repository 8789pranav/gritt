"""
Test Speaking Submit API on Deployed Server
"""
import requests
import base64
import struct
import math

BASE_URL = 'https://nvupmmyd66.us-east-1.awsapprunner.com'

# Login
print("Logging in...")
login = requests.post(f'{BASE_URL}/login', json={'email': 'rajdandeepak@gmail.com', 'password': 'Test@123'})
token = login.json()['id_token']
child_id = '2715cf08-1b5e-46dc-8c3b-a2bab5ecdcec'
print("✅ Logged in!")

# Create test audio (sine wave)
print("\nCreating test audio...")
sample_rate = 16000
duration = 2.0
num_samples = int(sample_rate * duration)
audio_data = []
for i in range(num_samples):
    t = i / sample_rate
    value = int(32767 * 0.1 * math.sin(2 * math.pi * 440 * t))
    audio_data.append(struct.pack('<h', value))
audio_bytes = b''.join(audio_data)
wav_header = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + len(audio_bytes), b'WAVE', b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16, b'data', len(audio_bytes))
audio_base64 = base64.b64encode(wav_header + audio_bytes).decode('utf-8')
print(f"✅ Audio created: {len(audio_base64)} chars base64")

# Test Single Submit
print("\n" + "="*60)
print("  TESTING: /speaking/submit/ (SINGLE)")
print("="*60)

response = requests.post(f'{BASE_URL}/speaking/submit/', json={
    'idToken': token,
    'child_id': child_id,
    'grade': 'First',
    'sentence_id': 'f1',
    'original_sentence': 'The brown dog likes to play with the ball.',
    'audio_base64': audio_base64,
    'audio_format': 'wav'
}, timeout=120)

if response.status_code == 200:
    data = response.json()
    print("✅ SPEAKING SUBMIT OK!")
    print(f"   Score ID: {data.get('score_id')}")
    print(f"   Transcribed: {data.get('transcribed_text', 'N/A')}")
    overall = data.get('overall', {})
    print(f"   Overall Score: {overall.get('score', 'N/A')}")
    print(f"   Level: {overall.get('level', 'N/A')}")
else:
    print(f"❌ FAILED: {response.status_code}")
    print(f"   {response.text[:300]}")

# Test Batch Submit
print("\n" + "="*60)
print("  TESTING: /speaking/submit/ (BATCH - 2 sentences)")
print("="*60)

response = requests.post(f'{BASE_URL}/speaking/submit/', json={
    'idToken': token,
    'child_id': child_id,
    'grade': 'First',
    'submissions': [
        {
            'sentence_id': 'f2',
            'original_sentence': 'She went to the store to buy some apples.',
            'audio_base64': audio_base64,
            'audio_format': 'wav'
        },
        {
            'sentence_id': 'f3',
            'original_sentence': 'The children are playing outside in the rain.',
            'audio_base64': audio_base64,
            'audio_format': 'wav'
        }
    ]
}, timeout=180)

if response.status_code == 200:
    data = response.json()
    print("✅ BATCH SUBMIT OK!")
    print(f"   Total Submitted: {data.get('total_submitted')}")
    print(f"   Average Score: {data.get('average_score')}")
    results = data.get('results', [])
    for r in results:
        print(f"   - {r.get('sentence_id')}: Score {r.get('overall_score', 'N/A')}")
else:
    print(f"❌ FAILED: {response.status_code}")
    print(f"   {response.text[:300]}")

print("\n" + "="*60)
print("  ✅ TEST COMPLETE")
print("="*60)
