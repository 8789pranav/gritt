"""Test pronounce-assess with TTS audio."""
import asyncio
import base64
import tempfile
import os
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.tts import TTSProvider
from pronounce_assess import PronounceAssessModel


async def test():
    tts = TTSProvider()
    audio_b64 = await tts.synthesize("The cat sat on the mat")
    if not audio_b64:
        print("TTS failed")
        return

    import librosa
    audio_bytes = base64.b64decode(audio_b64)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        y, sr = librosa.load(tmp_path, sr=16000)
        print(f"Audio: {len(y)} samples, sr={sr}, duration={len(y)/sr:.2f}s")

        model = PronounceAssessModel(sentence="The cat sat on the mat")

        # Chunk audio into 8000-sample chunks (0.5s at 16kHz)
        chunk_len = 8000
        chunks = [y[i:i+chunk_len].astype(np.float32) for i in range(0, len(y), chunk_len)]
        print(f"Chunks: {len(chunks)}")

        events = list(model.stream_decode(chunks, sample_rate=16000))
        print(f"Events: {len(events)}")

        correct = sum(1 for e in events if e.label == "correct")
        mispronounced = sum(1 for e in events if e.label == "mispronounced")
        omitted = sum(1 for e in events if e.label == "omitted")
        insertion = sum(1 for e in events if e.label == "insertion")
        print(f"Correct: {correct}, Mispronounced: {mispronounced}, Omitted: {omitted}, Insertion: {insertion}")

        for e in events:
            print(f"  phoneme={e.phoneme}  label={e.label}  gop={e.gop}  mono={e.monotony_score}  rhythm={e.rhythm_score}  rate={e.speaking_rate}")

        total = len(events)
        if total > 0:
            pron_score = round((correct / total) * 100, 1)
            print(f"\nPronunciation score: {pron_score}/100")

        # Prosody scores
        mono_scores = [e.monotony_score for e in events if e.monotony_score is not None]
        rhythm_scores = [e.rhythm_score for e in events if e.rhythm_score is not None]
        rate_scores = [e.speaking_rate for e in events if e.speaking_rate is not None]
        if mono_scores:
            print(f"Monotony avg: {sum(mono_scores)/len(mono_scores):.3f}")
        if rhythm_scores:
            print(f"Rhythm avg: {sum(rhythm_scores)/len(rhythm_scores):.3f}")
        if rate_scores:
            print(f"Speaking rate avg: {sum(rate_scores)/len(rate_scores):.3f}")

    finally:
        os.unlink(tmp_path)


asyncio.run(test())
