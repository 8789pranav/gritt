"""Quick test: verify GPT-audio works with input_audio content type."""
import base64
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from openai import OpenAI
from app.infrastructure.tts import TTSProvider

client = OpenAI()


async def test():
    tts = TTSProvider()
    audio_b64 = await tts.synthesize("The cat sat on the mat.")
    audio_bytes = base64.b64decode(audio_b64)
    audio_b64_str = base64.b64encode(audio_bytes).decode("utf-8")

    prompt = (
        'The child should say: "The cat sat on the mat." '
        "Return JSON: "
        '{"raw_transcription": "what you hear", '
        '"pronunciation_score": 90, '
        '"fluency_score": 85, '
        '"wpm": 120, '
        '"prosody_score": 80}'
    )

    response = client.chat.completions.create(
        model="gpt-audio",
        modalities=["text"],
        messages=[
            {
                "role": "system",
                "content": "You are a speech expert. Respond with valid JSON only.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64_str,
                            "format": "mp3",
                        },
                    },
                ],
            },
        ],
        temperature=0.2,
        max_tokens=500,
    )
    print("SUCCESS!")
    print("Response:", response.choices[0].message.content)


if __name__ == "__main__":
    asyncio.run(test())
