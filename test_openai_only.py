"""
Test OpenAI Whisper and GPT-4o directly
This tests ONLY the OpenAI APIs - no server needed
"""
import openai
import os
import wave
import struct
import math
import tempfile
import os

# Your OpenAI API Key - set via environment variable
API_KEY = os.getenv('OPENAI_API_KEY')

# Initialize OpenAI client
client = openai.OpenAI(api_key=API_KEY)

def create_test_audio(filename="test_speech.wav", duration=3.0):
    """Create a simple test audio file"""
    sample_rate = 16000
    n_samples = int(sample_rate * duration)
    audio_data = []
    
    for i in range(n_samples):
        t = i / sample_rate
        # Create a tone (simulating speech-like audio)
        sample = int(32767 * 0.3 * math.sin(2 * math.pi * 440 * t))
        audio_data.append(sample)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for sample in audio_data:
            wav_file.writeframes(struct.pack('<h', sample))
    
    return filename

def test_whisper():
    """Test OpenAI Whisper (Speech-to-Text)"""
    print("=" * 50)
    print("🎤 TEST 1: OpenAI Whisper (Speech-to-Text)")
    print("=" * 50)
    
    # Create test audio
    print("\n1. Creating test audio file...")
    audio_file = create_test_audio()
    print(f"   ✅ Created: {audio_file}")
    
    # Test Whisper
    print("\n2. Sending to Whisper API...")
    try:
        with open(audio_file, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
        
        print(f"   ✅ WHISPER WORKING!")
        print(f"   Transcribed text: '{transcript.text}'")
        print(f"   Duration: {transcript.duration}s")
        
        if hasattr(transcript, 'words') and transcript.words:
            print(f"   Word timestamps: {len(transcript.words)} words")
            for w in transcript.words[:5]:
                print(f"      - '{w.word}' ({w.start}s - {w.end}s)")
        
        # Cleanup
        os.remove(audio_file)
        return True, transcript.text
        
    except openai.RateLimitError as e:
        print(f"   ❌ RATE LIMIT ERROR (No credits!)")
        print(f"   Message: {e}")
        os.remove(audio_file)
        return False, str(e)
        
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        os.remove(audio_file)
        return False, str(e)

def test_gpt4o():
    """Test OpenAI GPT-4o (Chat/Analysis)"""
    print("\n" + "=" * 50)
    print("🧠 TEST 2: OpenAI GPT-4o (Analysis)")
    print("=" * 50)
    
    test_prompt = """You are a speech analyst for children. 
    
A First grade student was asked to read: "The cat sat on the mat."
The student said: "The cat sat on da mat."

Analyze this and provide:
1. Pronunciation score (0-100)
2. Errors found
3. Feedback for the child

Respond in JSON format."""

    print("\n1. Sending analysis request to GPT-4o...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful speech therapist for children."},
                {"role": "user", "content": test_prompt}
            ],
            max_tokens=500
        )
        
        print(f"   ✅ GPT-4o WORKING!")
        print(f"\n   Response:")
        print("-" * 40)
        print(response.choices[0].message.content)
        print("-" * 40)
        print(f"\n   Tokens used: {response.usage.total_tokens}")
        
        return True, response.choices[0].message.content
        
    except openai.RateLimitError as e:
        print(f"   ❌ RATE LIMIT ERROR (No credits!)")
        print(f"   Message: {e}")
        return False, str(e)
        
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False, str(e)

def test_gpt4o_mini():
    """Test OpenAI GPT-4o-mini (Cheaper alternative)"""
    print("\n" + "=" * 50)
    print("🧠 TEST 3: OpenAI GPT-4o-mini (Cheaper)")
    print("=" * 50)
    
    test_prompt = "Say 'Hello, I am working!' if you can read this."
    
    print("\n1. Sending test to GPT-4o-mini...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": test_prompt}
            ],
            max_tokens=50
        )
        
        print(f"   ✅ GPT-4o-mini WORKING!")
        print(f"   Response: {response.choices[0].message.content}")
        print(f"   Tokens used: {response.usage.total_tokens}")
        
        return True, response.choices[0].message.content
        
    except openai.RateLimitError as e:
        print(f"   ❌ RATE LIMIT ERROR (No credits!)")
        print(f"   Message: {e}")
        return False, str(e)
        
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False, str(e)

def main():
    print("\n" + "🔬" * 25)
    print("   OPENAI API DIRECT TEST")
    print("🔬" * 25 + "\n")
    
    # Check API key
    print("📋 API Key:", API_KEY[:20] + "..." + API_KEY[-10:])
    print()
    
    # Run tests
    results = {}
    
    # Test 1: Whisper
    whisper_ok, whisper_result = test_whisper()
    results["Whisper"] = "✅ Working" if whisper_ok else "❌ Failed"
    
    # Test 2: GPT-4o
    gpt4o_ok, gpt4o_result = test_gpt4o()
    results["GPT-4o"] = "✅ Working" if gpt4o_ok else "❌ Failed"
    
    # Test 3: GPT-4o-mini
    gpt4o_mini_ok, gpt4o_mini_result = test_gpt4o_mini()
    results["GPT-4o-mini"] = "✅ Working" if gpt4o_mini_ok else "❌ Failed"
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    for api, status in results.items():
        print(f"   {api}: {status}")
    
    if not any([whisper_ok, gpt4o_ok, gpt4o_mini_ok]):
        print("\n⚠️  ALL TESTS FAILED!")
        print("   The API key is valid but has NO CREDITS.")
        print("   Add credits at: https://platform.openai.com/account/billing")
    elif all([whisper_ok, gpt4o_ok, gpt4o_mini_ok]):
        print("\n🎉 ALL TESTS PASSED! OpenAI APIs are fully working!")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")

if __name__ == "__main__":
    main()
