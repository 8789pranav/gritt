"""Deep speaking test: generate TTS audio and run through real Whisper + GPT-4o pipeline.

This tests the actual scoring to see if it's always giving ~95% or if it
discriminates between good and bad speech.

Usage:
    $env:PYTHONIOENCODING="utf-8"; python scripts/deep_speaking_test.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.tts import TTSProvider
from app.infrastructure.speech import SpeechProvider
from app.engines.registry import speaking_engine
from app.domain.enums import Grade
from app.engines.speaking.analyzer import SpeechAnalysis


async def run_test():
    tts = TTSProvider()
    speech = SpeechProvider()

    if not speech.is_configured:
        print("ERROR: OpenAI not configured. Cannot run real speech analysis.")
        return

    for grade_name in ["Kindergarten", "First", "Second", "Third"]:
        grade = Grade.parse(grade_name)
        engine = speaking_engine()
        sentences = engine.get_items(grade)

        print(f"\n{'='*80}")
        print(f"  SPEAKING TEST -- Grade: {grade_name}  ({len(sentences)} sentences)")
        print(f"{'='*80}")

        all_analyses: Dict[str, SpeechAnalysis] = {}
        all_results: List[Dict[str, Any]] = []
        total_score = 0.0
        answered_count = 0

        for sent in sentences:
            print(f"\n  Sentence {sent.sentence_id}: \"{sent.sentence}\"")
            print(f"  Difficulty: {sent.difficulty.value}")

            # Step 1: Generate TTS audio (perfect adult speech)
            audio_b64 = await tts.synthesize(sent.sentence)
            if not audio_b64:
                print(f"  ERROR: TTS failed for {sent.sentence_id}")
                continue

            print(f"  Audio generated: {len(base64.b64decode(audio_b64))} bytes")

            # Step 2: Transcribe with Whisper
            trans_result = await speech.transcribe(audio_b64, "mp3")
            if not trans_result["success"]:
                print(f"  ERROR: Transcription failed: {trans_result.get('error')}")
                continue

            transcribed = trans_result["transcribed_text"]
            duration = trans_result.get("duration", 0)
            word_ts = trans_result.get("word_timestamps", [])

            print(f"  Transcribed: \"{transcribed}\"")
            print(f"  Duration: {duration:.1f}s, Words: {len(transcribed.split())}")

            # Step 3: Analyze with GPT-4o
            ai_result = await speech.analyze(
                sent.sentence, transcribed, word_ts, duration, grade_name
            )

            if not ai_result["success"] or not ai_result["analysis"]:
                print(f"  ERROR: Analysis failed: {ai_result.get('error')}")
                continue

            analysis = ai_result["analysis"]
            speech_analysis = SpeechAnalysis.from_provider_payload(analysis)
            all_analyses[sent.sentence_id] = speech_analysis

            overall = analysis.get("overall", {})
            overall_score = overall.get("score", 0)
            total_score += overall_score
            answered_count += 1

            pron = analysis.get("pronunciation", {})
            fluency = analysis.get("fluency", {})
            grammar = analysis.get("grammar", {})
            rate = analysis.get("speaking_rate", {})

            print(f"\n  SCORES:")
            print(f"    Pronunciation: {pron.get('score', 0)}/100  (normalised: {speech_analysis.pronunciation.normalised})")
            print(f"    Fluency:       {fluency.get('score', 0)}/100  (normalised: {speech_analysis.fluency.normalised})")
            print(f"    Grammar:       {grammar.get('score', 0)}/100  (normalised: {speech_analysis.grammar.normalised})")
            print(f"    Speaking rate: {rate.get('score', 0)}/100  ({rate.get('wpm', 0)} WPM, {rate.get('status', '')})")
            print(f"    OVERALL:       {overall_score}/100  ({overall.get('level', '')})")
            print(f"    Status:        {overall.get('status', '')}")

            if overall.get("strengths"):
                print(f"    Strengths:     {overall['strengths']}")
            if overall.get("areas_to_improve"):
                print(f"    Areas to improve: {overall['areas_to_improve']}")
            if overall.get("parent_tip"):
                print(f"    Parent tip:    {overall['parent_tip']}")

            # Per-sentence tags
            tags: List[str] = []
            dimensions = {
                "pronunciation": speech_analysis.pronunciation.normalised,
                "fluency": speech_analysis.fluency.normalised,
                "prosody": speech_analysis.prosody.normalised,
                "grammar": speech_analysis.grammar.normalised,
            }
            for name, value in dimensions.items():
                if value >= 0.85:
                    tags.append(f"{name}_strong")
                elif value < 0.6:
                    tags.append(f"{name}_needs_work")

            print(f"    Tags:          {tags}")

            all_results.append({
                "sentence_id": sent.sentence_id,
                "original": sent.sentence,
                "transcribed": transcribed,
                "overall_score": overall_score,
                "pronunciation": pron.get("score", 0),
                "fluency": fluency.get("score", 0),
                "grammar": grammar.get("score", 0),
                "tags": tags,
            })

        # Summary
        max_score = len(sentences) * 100
        percentage = round((total_score / max_score) * 100, 1) if max_score else 0
        avg_score = round(total_score / answered_count, 1) if answered_count else 0

        if percentage >= 90:
            level = "Excellent Speaker"
        elif percentage >= 75:
            level = "Good Speaker"
        elif percentage >= 50:
            level = "Developing Speaker"
        else:
            level = "Needs Improvement"

        print(f"\n  {'-'*60}")
        print(f"  SUMMARY -- Grade: {grade_name}")
        print(f"  Answered:      {answered_count}/{len(sentences)}")
        print(f"  Total score:   {total_score:.1f}/{max_score}")
        print(f"  Average score: {avg_score}")
        print(f"  Percentage:    {percentage}%")
        print(f"  Level:         {level}")

        # Show all per-sentence scores in a table
        print(f"\n  PER-SENTENCE SCORES:")
        print(f"  {'ID':6s} {'Pron':>6s} {'Flu':>6s} {'Gram':>6s} {'Overall':>8s}  Tags")
        print(f"  {'-'*50}")
        for r in all_results:
            tags_str = ", ".join(r["tags"]) if r["tags"] else "(none)"
            print(f"  {r['sentence_id']:6s} {r['pronunciation']:6.1f} {r['fluency']:6.1f} {r['grammar']:6.1f} {r['overall_score']:8.1f}  [{tags_str}]")


if __name__ == "__main__":
    asyncio.run(run_test())
