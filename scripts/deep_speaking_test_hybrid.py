"""Deep speaking test with hybrid provider: TTS audio through real Whisper + GPT-4o audio.

This tests whether the new hybrid scoring discriminates between different
speech quality levels, unlike the old GPT-4o-only approach that always gave ~95.

GPT-4o listens to the audio directly and identifies mispronunciations
WITHOUT auto-correcting (unlike Whisper which corrects "kat" → "cat").

Usage:
    $env:PYTHONIOENCODING="utf-8"; python scripts/deep_speaking_test_hybrid.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.tts import TTSProvider
from app.infrastructure.hybrid_speech import HybridSpeechProvider
from app.engines.registry import speaking_engine
from app.domain.enums import Grade


async def run_test():
    tts = TTSProvider()
    speech = HybridSpeechProvider()

    if not speech.is_configured:
        print("ERROR: OpenAI not configured.")
        return

    for grade_name in ["Kindergarten", "First", "Second", "Third"]:
        grade = Grade.parse(grade_name)
        engine = speaking_engine()
        sentences = engine.get_items(grade)

        print(f"\n{'='*80}")
        print(f"  HYBRID SPEAKING TEST -- Grade: {grade_name}  ({len(sentences)} sentences)")
        print(f"{'='*80}")

        all_results = []
        total_score = 0.0
        answered_count = 0

        for sent in sentences:
            print(f"\n  Sentence {sent.sentence_id}: \"{sent.sentence}\"")

            # Generate TTS audio (perfect adult speech)
            audio_b64 = await tts.synthesize(sent.sentence)
            if not audio_b64:
                print(f"  ERROR: TTS failed")
                continue

            # Small delay to avoid rate limiting on GPT-audio
            import time as _time
            _time.sleep(3)

            # Run full hybrid analysis
            result = await speech.analyze_with_audio(
                audio_b64, "mp3", sent.sentence, grade_name
            )

            if not result["success"] or not result["analysis"]:
                print(f"  ERROR: {result.get('error', 'Unknown')}")
                continue

            analysis = result["analysis"]
            overall = analysis.get("overall", {})
            overall_score = overall.get("score", 0)
            total_score += overall_score
            answered_count += 1

            pron = analysis.get("pronunciation", {})
            fluency = analysis.get("fluency", {})
            prosody = analysis.get("prosody", {})
            grammar = analysis.get("grammar", {})
            rate = analysis.get("speaking_rate", {})

            print(f"  Raw transcription (GPT-audio): \"{pron.get('raw_transcription', '')}\"")
            print(f"  Duration: {result.get('duration', 0):.1f}s")
            print(f"\n  SCORES (GPT-audio only — no Whisper):")
            print(f"    Pronunciation: {pron.get('score', 0)}/100  (correct: {pron.get('correct_phonemes', 0)}/{pron.get('total_phonemes', 0)}, mispronounced: {pron.get('mispronounced', 0)}, omitted: {pron.get('omitted', 0)})")
            if pron.get("mispronounced_words"):
                print(f"    Mispronounced words: {pron['mispronounced_words']}")
            if pron.get("per_word"):
                for w in pron["per_word"]:
                    status_icon = "OK" if w.get("status") == "correct" else w.get("status", "?").upper()
                    note = f" -- {w.get('note', '')}" if w.get("note") else ""
                    print(f"      [{status_icon}] {w.get('word', '?')}{note}")
            print(f"    Fluency:       {fluency.get('score', 0)}/100  (pauses: {fluency.get('long_pauses_count', 0)}, pause_ratio: {fluency.get('pause_ratio', 0)})")
            print(f"    Speaking rate: {rate.get('score', 0)}/100  ({rate.get('wpm', 0)} WPM, {rate.get('status', '')})")
            print(f"    Prosody:       {prosody.get('score', 0)}/100  ({prosody.get('notes', 'N/A')})")
            print(f"    Grammar:       {grammar.get('score', 0)}/100  (issues: {len(grammar.get('issues', []))})")
            print(f"    OVERALL:       {overall_score}/100  ({overall.get('level', '')})")

            if overall.get("strengths"):
                print(f"    Strengths:     {overall['strengths']}")
            if overall.get("areas_to_improve"):
                print(f"    Areas to improve: {overall['areas_to_improve']}")

            all_results.append({
                "sentence_id": sent.sentence_id,
                "original": sent.sentence,
                "transcribed": result.get("transcribed_text", ""),
                "overall_score": overall_score,
                "pronunciation": pron.get("score", 0),
                "fluency": fluency.get("score", 0),
                "prosody": prosody.get("score", 0),
                "grammar": grammar.get("score", 0),
                "speaking_rate": rate.get("score", 0),
            })

        # Summary
        max_score = len(sentences) * 100
        percentage = round((total_score / max_score) * 100, 1) if max_score else 0
        avg_score = round(total_score / answered_count, 1) if answered_count else 0

        print(f"\n  {'-'*60}")
        print(f"  SUMMARY -- Grade: {grade_name}")
        print(f"  Answered:      {answered_count}/{len(sentences)}")
        print(f"  Total score:   {total_score:.1f}/{max_score}")
        print(f"  Average score: {avg_score}")
        print(f"  Percentage:    {percentage}%")

        # Per-sentence table
        print(f"\n  PER-SENTENCE SCORES:")
        print(f"  {'ID':6s} {'Pron':>6s} {'Flu':>6s} {'Pros':>6s} {'Gram':>6s} {'Rate':>6s} {'Overall':>8s}")
        print(f"  {'-'*55}")
        for r in all_results:
            print(f"  {r['sentence_id']:6s} {r['pronunciation']:6.1f} {r['fluency']:6.1f} {r['prosody']:6.1f} {r['grammar']:6.1f} {r['speaking_rate']:6.1f} {r['overall_score']:8.1f}")


if __name__ == "__main__":
    asyncio.run(run_test())
