"""
Test generate_all_grade_audio API
"""
import requests
import time

BASE_URL = 'http://localhost:8000'

print('='*60)
print('  TESTING: generate_all_grade_audio API')
print('='*60)

# Wait for server
time.sleep(2)

grades = ['Kindergarten', 'First', 'Second', 'Third']

for grade in grades:
    print(f'\n✅ Testing {grade} grade...')
    try:
        response = requests.post(f'{BASE_URL}/generate_all_grade_audio/', json={'grade': grade}, timeout=120)
        if response.status_code == 200:
            data = response.json()
            audio_files = data.get('audio_files', [])
            print(f'   📚 Grade: {data.get("grade")}')
            print(f'   📝 Total words: {len(audio_files)}')
            
            # Count by type
            regular = [a for a in audio_files if a.get('word_type') == 'regular']
            sight = [a for a in audio_files if a.get('word_type') == 'sight']
            print(f'   🔤 Regular words: {len(regular)}')
            print(f'   👁️ Sight words: {len(sight)}')
            
            if audio_files:
                first = audio_files[0]
                print(f'   🎵 Sample: "{first.get("word")}" ({first.get("word_type")})')
                print(f'      Word audio: {len(first.get("word_audio", ""))} chars base64')
                print(f'      Sentence audio: {len(first.get("sentence_audio", ""))} chars base64')
        else:
            print(f'   ❌ FAILED: {response.status_code} - {response.text[:100]}')
    except Exception as e:
        print(f'   ❌ ERROR: {e}')

print('\n' + '='*60)
print('  ✅ TEST COMPLETE')
print('='*60)
