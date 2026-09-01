"""Hybrid speech analysis provider.

Combines:
- GPT-audio for everything: pronunciation, fluency, prosody, raw transcription
- Computed completeness from GPT-audio's raw transcription (what child actually said)
- GPT-4o for parent-friendly feedback

Key insight: Whisper auto-corrects mispronunciation ("kat" → "cat"), making it
useless for pronunciation detection. GPT-audio listens to the audio directly and
transcribes what was ACTUALLY said, identifies mispronunciations, scores
pronunciation, fluency, and prosody — all in one API call.
Zero extra dependencies, zero extra RAM, zero deployment cost increase.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Comfortable WPM band for children by grade
_GRADE_WPM = {
    "Kindergarten": (80, 130),
    "First": (90, 140),
    "Second": (100, 150),
    "Third": (110, 160),
}
_DEFAULT_WPM = (100, 150)

# Pause threshold in seconds — gaps longer than this count as disfluency
_PAUSE_THRESHOLD = 0.5


class HybridSpeechProvider:
    """Speech analysis using Whisper + GPT-4o audio input. No heavy ML deps."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._openai: Optional[Any] = None
        if self._settings.openai.is_configured:
            import openai
            self._openai = openai.OpenAI(api_key=self._settings.openai.api_key)

    @property
    def is_configured(self) -> bool:
        return self._openai is not None

    def _analyze_audio_with_gpt4o(
        self,
        audio_bytes: bytes,
        audio_format: str,
        original_sentence: str,
        grade: str,
    ) -> Dict[str, Any]:
        """Use GPT-audio to analyze everything: pronunciation, fluency, prosody.

        GPT-audio listens to the audio natively and returns:
        - Raw transcription (what child ACTUALLY said — no auto-correction)
        - Per-word pronunciation analysis
        - Prosody score
        - Fluency data (WPM, pauses, duration estimate)

        This replaces both Whisper AND wav2vec2 with a single API call.
        Zero extra dependencies — just the openai package.

        Returns dict with pronunciation, fluency, prosody, and transcription data.
        """
        if not self._openai:
            return self._empty_audio_analysis()

        import time

        valid_format = audio_format if audio_format in ("mp3", "wav") else "mp3"
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        prompt = f"""You are a speech assessment expert for {grade} grade students.

The child was supposed to say: "{original_sentence}"

Listen to the audio carefully and analyze the child's speech.

IMPORTANT: Do NOT auto-correct what the child said. Transcribe EXACTLY what you hear,
including mispronunciations. If the child said "kat" instead of "cat", write "kat".

Return your analysis as JSON with this exact structure:
{{
    "raw_transcription": "what the child ACTUALLY said (not corrected)",
    "pronunciation_score": 0-100 number,
    "mispronounced_words": [{{"word": "cat", "said_as": "kat", "issue": "vowel sound"}}],
    "omitted_words": ["words the child skipped"],
    "inserted_words": ["extra words not in original"],
    "per_word": [
        {{"word": "The", "status": "correct", "note": "", "start_time": 0.0, "end_time": 0.3}},
        {{"word": "cat", "status": "mispronounced", "note": "said as kat", "start_time": 0.4, "end_time": 0.7}}
    ],
    "prosody_score": 0-100 number,
    "prosody_notes": "brief note about intonation/rhythm",
    "estimated_duration_seconds": number (total audio duration in seconds),
    "wpm": number (words per minute — word count / duration in minutes),
    "pause_count": number (gaps between words > 0.15 seconds),
    "long_pause_count": number (gaps between words > 0.5 seconds),
    "total_pause_duration": number (sum of all pause durations in seconds),
    "hesitation_count": number (filled pauses like "um", "uh", "er" or false starts),
    "repetition_count": number (words repeated by the child),
    "fluency_score": 0-100 number (smoothness: 100=no pauses/hesitation/repetition)
}}

For per_word timing: estimate when each word starts and ends in seconds from the beginning of the audio.
Be as precise as possible — these timestamps will be used to calculate exact pauses between words.

Scoring guides:
- Pronunciation: 90-100 excellent, 75-89 good, 60-74 fair, 40-59 needs work, 0-39 poor
- Fluency: 90-100 smooth & natural, 75-89 minor pauses, 60-74 some hesitation, 40-59 choppy, 0-39 very choppy
- Prosody: 90-100 expressive, 75-89 good intonation, 60-74 somewhat flat, 40-59 monotone, 0-39 no expression

Fluency scoring factors:
- Deduct 5-10 points per pause > 0.3s between words
- Deduct 10-15 points per long pause > 0.5s
- Deduct 10 points per hesitation ("um", "uh")
- Deduct 10 points per word repetition
- A child who reads smoothly with no pauses should score 90-100

WPM reference for {grade} grade: comfortable range is {_GRADE_WPM.get(grade, _DEFAULT_WPM)[0]}-{_GRADE_WPM.get(grade, _DEFAULT_WPM)[1]} WPM.

Respond with valid JSON only, no markdown."""

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                response = self._openai.chat.completions.create(
                    model="gpt-audio",
                    modalities=["text"],
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a child speech assessment expert. "
                                "You listen to audio and analyze pronunciation precisely. "
                                "Always respond with valid JSON only, no markdown."
                            ),
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt,
                                },
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": audio_b64,
                                        "format": valid_format,
                                    },
                                },
                            ],
                        },
                    ],
                    temperature=0.2,
                    max_tokens=1500,
                )

                result_text = response.choices[0].message.content
                if not result_text:
                    logger.warning("GPT-audio returned empty content (attempt %d/%d)", attempt + 1, max_retries)
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return self._empty_audio_analysis()

                result_text = result_text.strip()
                if result_text.startswith("```"):
                    result_text = re.sub(r"^```json?\s*", "", result_text)
                    result_text = re.sub(r"\s*```$", "", result_text)

                try:
                    result = json.loads(result_text)
                except json.JSONDecodeError:
                    json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                        except json.JSONDecodeError:
                            logger.warning("GPT-audio unparseable JSON (attempt %d): %s", attempt + 1, result_text[:200])
                            if attempt < max_retries - 1:
                                time.sleep(2)
                                continue
                            return self._empty_audio_analysis()
                    else:
                        logger.warning("GPT-audio no JSON (attempt %d): %s", attempt + 1, result_text[:200])
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        return self._empty_audio_analysis()

                return {
                    "pronunciation_score": float(result.get("pronunciation_score", 0)),
                    "raw_transcription": result.get("raw_transcription", ""),
                    "mispronounced_words": result.get("mispronounced_words", []),
                    "omitted_words": result.get("omitted_words", []),
                    "inserted_words": result.get("inserted_words", []),
                    "per_word": result.get("per_word", []),
                    "prosody_score": float(result.get("prosody_score", 50)),
                    "prosody_notes": result.get("prosody_notes", ""),
                    "estimated_duration": float(result.get("estimated_duration_seconds", 0)),
                    "wpm": float(result.get("wpm", 0)),
                    "pause_count": int(result.get("pause_count", 0)),
                    "long_pause_count": int(result.get("long_pause_count", 0)),
                    "total_pause_duration": float(result.get("total_pause_duration", 0)),
                    "hesitation_count": int(result.get("hesitation_count", 0)),
                    "repetition_count": int(result.get("repetition_count", 0)),
                    "fluency_score": float(result.get("fluency_score", 0)),
                }

            except Exception as exc:
                last_error = exc
                logger.warning("GPT-audio error (attempt %d/%d): %s", attempt + 1, max_retries, exc)
                if attempt < max_retries - 1:
                    time.sleep(2)

        logger.warning("GPT-audio failed after %d retries: %s", max_retries, last_error)
        return self._empty_audio_analysis()

    @staticmethod
    def _empty_audio_analysis() -> Dict[str, Any]:
        """Empty result when audio analysis is unavailable."""
        return {
            "pronunciation_score": 0,
            "raw_transcription": "",
            "mispronounced_words": [],
            "omitted_words": [],
            "inserted_words": [],
            "per_word": [],
            "prosody_score": 0,
            "prosody_notes": "",
            "estimated_duration": 0,
            "wpm": 0,
            "pause_count": 0,
            "long_pause_count": 0,
            "total_pause_duration": 0,
            "hesitation_count": 0,
            "repetition_count": 0,
            "fluency_score": 0,
        }

    # ------------------------------------------------------------------
    # Transcription (Whisper)
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        audio_base64: str,
        audio_format: str = "mp3",
    ) -> Dict[str, Any]:
        """Transcribe audio using OpenAI Whisper API."""
        if not self._openai:
            return {
                "success": False,
                "error": "OpenAI API key not configured",
                "transcribed_text": "",
                "word_timestamps": [],
            }

        temp_path = None
        try:
            audio_bytes = base64.b64decode(audio_base64)
            with tempfile.NamedTemporaryFile(
                suffix=f".{audio_format}", delete=False
            ) as tmp:
                tmp.write(audio_bytes)
                temp_path = tmp.name

            with open(temp_path, "rb") as audio_file:
                transcript = self._openai.audio.transcriptions.create(
                    model=self._settings.openai.transcription_model,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                )

            word_timestamps: List[Dict[str, Any]] = []
            if hasattr(transcript, "words") and transcript.words:
                for word_info in transcript.words:
                    word_timestamps.append(
                        {
                            "word": word_info.word,
                            "start": word_info.start,
                            "end": word_info.end,
                        }
                    )

            return {
                "success": True,
                "transcribed_text": transcript.text,
                "word_timestamps": word_timestamps,
                "duration": getattr(transcript, "duration", 0),
            }
        except Exception as exc:
            logger.warning("Whisper transcription error: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "transcribed_text": "",
                "word_timestamps": [],
            }
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Core analysis (GPT-audio only — no Whisper)
    # ------------------------------------------------------------------

    async def analyze(
        self,
        original_sentence: str,
        transcribed_text: str,
        word_timestamps: List[Dict[str, Any]],
        duration_seconds: float,
        grade: str,
    ) -> Dict[str, Any]:
        """Analyze speech from text + timestamps only (no audio for GPT-audio)."""
        try:
            return await self._analyze_from_text(
                original_sentence, transcribed_text,
                word_timestamps, duration_seconds, grade,
            )
        except Exception as exc:
            logger.warning("Hybrid analysis error: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "analysis": None,
            }

    async def analyze_with_audio(
        self,
        audio_base64: str,
        audio_format: str,
        original_sentence: str,
        grade: str,
    ) -> Dict[str, Any]:
        """Full analysis pipeline using GPT-audio only.

        GPT-audio listens to the audio and returns everything:
        - Pronunciation score + per-word analysis (no auto-correction)
        - Fluency score, WPM, pauses
        - Prosody score
        - Raw transcription (what child actually said)

        No Whisper needed. Single API call. Zero extra dependencies.
        """
        if not self._openai:
            return {
                "success": False,
                "error": "OpenAI API key not configured",
                "analysis": None,
            }

        # Step 1: GPT-audio analysis — everything in one call
        audio_bytes = base64.b64decode(audio_base64)
        audio_analysis = self._analyze_audio_with_gpt4o(
            audio_bytes, audio_format, original_sentence, grade
        )

        pron_score = audio_analysis["pronunciation_score"]
        raw_transcription = audio_analysis.get("raw_transcription", "")

        # If GPT-audio failed (no speech detected), keep scores at 0
        if pron_score == 0 and not raw_transcription:
            logger.warning("GPT-audio analysis failed — no speech detected, scoring 0")

        # Step 2: Fluency — compute precise pauses from per-word timestamps
        per_word = audio_analysis.get("per_word", [])
        wpm = audio_analysis.get("wpm", 0)
        duration = audio_analysis.get("estimated_duration", 0)
        hesitation_count = audio_analysis.get("hesitation_count", 0)
        repetition_count = audio_analysis.get("repetition_count", 0)

        # Compute exact pauses from per-word start/end timestamps
        exact_pauses = []
        for i in range(1, len(per_word)):
            prev_end = per_word[i - 1].get("end_time")
            curr_start = per_word[i].get("start_time")
            if prev_end is not None and curr_start is not None:
                gap = round(curr_start - prev_end, 2)
                if gap > 0.15:
                    exact_pauses.append(gap)

        if exact_pauses:
            pause_count = len(exact_pauses)
            long_pause_count = sum(1 for p in exact_pauses if p > 0.5)
            total_pause_duration = round(sum(exact_pauses), 2)
        else:
            pause_count = audio_analysis.get("pause_count", 0)
            long_pause_count = audio_analysis.get("long_pause_count", 0)
            total_pause_duration = audio_analysis.get("total_pause_duration", 0)

        # Compute fluency score from exact data
        computed_fluency = 100.0
        for p in exact_pauses:
            if p > 0.5:
                computed_fluency -= min(15, p * 20)
            elif p > 0.3:
                computed_fluency -= min(8, p * 15)
            else:
                computed_fluency -= 3
        computed_fluency -= hesitation_count * 10
        computed_fluency -= repetition_count * 10
        computed_fluency = max(0, min(100, round(computed_fluency, 1)))

        # Use GPT-audio's fluency score if provided, otherwise use computed
        gpt_fluency = audio_analysis.get("fluency_score", 0)
        if gpt_fluency > 0:
            # Blend: 60% GPT-audio, 40% computed for more accuracy
            fluency_score = round(gpt_fluency * 0.6 + computed_fluency * 0.4, 1)
        else:
            fluency_score = computed_fluency

        # Compute rate score from WPM
        low, high = _GRADE_WPM.get(grade, _DEFAULT_WPM)
        if wpm > 0:
            if low <= wpm <= high:
                rate_score = 100.0
                rate_status = "Perfect"
            elif wpm < low:
                ratio = wpm / low if low > 0 else 0
                rate_score = round(max(40, ratio * 100), 1)
                rate_status = "Too Slow" if wpm < low * 0.6 else "Slightly Slow"
            else:
                ratio = high / wpm if wpm > 0 else 0
                rate_score = round(max(40, ratio * 100), 1)
                rate_status = "Too Fast" if wpm > high * 1.5 else "Slightly Fast"
        else:
            rate_score = 0
            rate_status = "Unknown"

        word_count = len(raw_transcription.split()) if raw_transcription else 0
        pause_ratio = round(total_pause_duration / max(0.1, duration), 2) if duration > 0 else 0

        fluency_result = {
            "fluency_score": fluency_score,
            "rate_score": rate_score,
            "wpm": wpm,
            "rate_status": rate_status,
            "long_pauses": long_pause_count,
            "total_pauses": pause_count,
            "pause_ratio": pause_ratio,
            "total_pause_duration": total_pause_duration,
            "hesitation_count": hesitation_count,
            "repetition_count": repetition_count,
            "per_word_timing": per_word,
        }

        # Step 3: Completeness from GPT-audio's raw transcription
        if raw_transcription:
            completeness_result = self._compute_completeness(
                original_sentence, raw_transcription
            )
        else:
            # No speech detected — completeness is 0
            completeness_result = {
                "completeness_score": 0,
                "expected_words": len(original_sentence.split()),
                "spoken_words": 0,
                "missing_words": original_sentence.lower().split(),
                "extra_words": [],
            }

        # Add GPT-audio's omitted words to completeness
        omitted = audio_analysis.get("omitted_words", [])
        if omitted:
            existing_missing = set(completeness_result.get("missing_words", []))
            existing_missing.update(omitted)
            completeness_result["missing_words"] = list(existing_missing)
            expected = completeness_result.get("expected_words", 1)
            spoken = expected - len(completeness_result["missing_words"])
            completeness_result["spoken_words"] = max(0, spoken)
            completeness_result["completeness_score"] = round(
                max(0, spoken) / expected * 100, 1
            ) if expected > 0 else 0

        # Step 4: Prosody from GPT-audio
        prosody_score = audio_analysis.get("prosody_score", 0)
        prosody_result = {
            "score": prosody_score,
            "notes": audio_analysis.get("prosody_notes", ""),
        }

        # Step 5: Grammar analysis — use raw transcription (not auto-corrected)
        # If no speech was detected, grammar score is 0
        if raw_transcription:
            grammar_result = self._analyze_grammar(
                original_sentence, raw_transcription, grade,
                phoneme_result=completeness_result,
            )
        else:
            grammar_result = {"grammar_score": 0, "issues": []}

        # Step 6: Compute overall score
        grammar_score = grammar_result.get("grammar_score", 0)
        completeness_score = completeness_result.get("completeness_score", 0)

        # If no speech was detected (empty transcription), score everything 0
        if not raw_transcription or not raw_transcription.strip():
            overall_score = 0.0
            pron_score = 0.0
            fluency_score = 0.0
            prosody_score = 0.0
            grammar_score = 0.0
            completeness_score = 0.0
        else:
            overall_score = round(
                pron_score * 0.35 +
                fluency_score * 0.25 +
                prosody_score * 0.15 +
                grammar_score * 0.15 +
                completeness_score * 0.10,
                1,
            )

        # Step 7: Generate parent-friendly feedback with GPT-4o
        pron_detail = {
            "correct_count": sum(
                1 for w in audio_analysis.get("per_word", [])
                if w.get("status") == "correct"
            ),
            "total_count": len(audio_analysis.get("per_word", [])),
            "mispronounced_count": len(audio_analysis.get("mispronounced_words", [])),
            "omitted_count": len(audio_analysis.get("omitted_words", [])),
            "insertion_count": len(audio_analysis.get("inserted_words", [])),
            "per_word": audio_analysis.get("per_word", []),
            "raw_transcription": raw_transcription,
        }

        feedback = self._generate_feedback(
            original_sentence, raw_transcription or original_sentence, grade,
            pron_score, fluency_score, prosody_score,
            grammar_score, completeness_score,
            pron_detail, fluency_result, prosody_result,
            grammar_result, completeness_result,
            overall_score,
        )

        analysis = {
            "pronunciation": {
                "score": pron_score,
                "correct_phonemes": pron_detail["correct_count"],
                "total_phonemes": pron_detail["total_count"],
                "mispronounced": pron_detail["mispronounced_count"],
                "omitted": pron_detail["omitted_count"],
                "inserted": pron_detail["insertion_count"],
                "per_word": pron_detail["per_word"],
                "raw_transcription": raw_transcription,
                "mispronounced_words": audio_analysis.get("mispronounced_words", []),
                "feedback": feedback.get("pronunciation_feedback", ""),
            },
            "speaking_rate": {
                "score": rate_score,
                "wpm": wpm,
                "status": rate_status,
                "feedback": feedback.get("rate_feedback", ""),
            },
            "fluency": {
                "score": fluency_score,
                "long_pauses_count": long_pause_count,
                "total_pauses": pause_count,
                "pause_ratio": pause_ratio,
                "total_pause_duration": total_pause_duration,
                "hesitation_count": hesitation_count,
                "repetition_count": repetition_count,
                "per_word_timing": per_word,
                "feedback": feedback.get("fluency_feedback", ""),
            },
            "prosody": {
                "score": prosody_score,
                "notes": audio_analysis.get("prosody_notes", ""),
                "feedback": feedback.get("prosody_feedback", ""),
            },
            "grammar": {
                "score": grammar_score,
                "issues": grammar_result.get("issues", []),
                "feedback": feedback.get("grammar_feedback", ""),
            },
            "completeness": {
                "score": completeness_score,
                "expected_words": completeness_result.get("expected_words", 0),
                "spoken_words": completeness_result.get("spoken_words", 0),
                "missing_words": completeness_result.get("missing_words", []),
            },
            "overall": {
                "score": overall_score,
                "status": self._overall_status(overall_score),
                "level": self._overall_level(overall_score),
                "strengths": feedback.get("strengths", []),
                "areas_to_improve": feedback.get("areas_to_improve", []),
                "recommendation": feedback.get("recommendation", ""),
                "parent_tip": feedback.get("parent_tip", ""),
            },
        }

        return {
            "success": True,
            "analysis": analysis,
            "transcribed_text": raw_transcription,
            "word_timestamps": [],
            "duration": duration,
        }

    # ------------------------------------------------------------------
    # Fluency scoring (from word timestamps)
    # ------------------------------------------------------------------

    def _compute_fluency(
        self,
        word_timestamps: List[Dict[str, Any]],
        duration: float,
        grade: str,
    ) -> Dict[str, Any]:
        """Compute fluency score from word timestamps."""
        if not word_timestamps or duration <= 0:
            return {
                "fluency_score": 0,
                "rate_score": 0,
                "wpm": 0,
                "rate_status": "Unknown",
                "long_pauses": 0,
                "total_pauses": 0,
                "pause_ratio": 0,
            }

        # Speaking rate (WPM)
        word_count = len(word_timestamps)
        wpm = round(word_count / duration * 60, 1)

        # Rate score based on grade-appropriate WPM band
        low, high = _GRADE_WPM.get(grade, _DEFAULT_WPM)
        if low <= wpm <= high:
            rate_score = 100.0
            rate_status = "Perfect"
        elif wpm < low:
            # Too slow — penalize proportionally
            ratio = wpm / low if low > 0 else 0
            rate_score = round(max(40, ratio * 100), 1)
            rate_status = "Too Slow" if wpm < low * 0.6 else "Slightly Slow"
        else:
            # Too fast — penalize proportionally
            ratio = high / wpm if wpm > 0 else 0
            rate_score = round(max(40, ratio * 100), 1)
            rate_status = "Too Fast" if wpm > high * 1.5 else "Slightly Fast"

        # Pause analysis
        pauses = []
        for i in range(1, len(word_timestamps)):
            prev_end = word_timestamps[i - 1].get("end", 0)
            curr_start = word_timestamps[i].get("start", 0)
            gap = curr_start - prev_end
            if gap > 0.1:  # any gap > 100ms
                pauses.append(gap)

        long_pauses = sum(1 for p in pauses if p > _PAUSE_THRESHOLD)
        total_pause_time = sum(pauses)
        speaking_time = duration - total_pause_time
        pause_ratio = total_pause_time / duration if duration > 0 else 0

        # Fluency score: start from rate_score, penalize for pauses
        # Each long pause deducts 10 points, pause_ratio > 0.3 is bad
        fluency_score = rate_score
        fluency_score -= long_pauses * 10
        if pause_ratio > 0.3:
            fluency_score -= (pause_ratio - 0.3) * 100
        fluency_score = max(0, min(100, round(fluency_score, 1)))

        return {
            "fluency_score": fluency_score,
            "rate_score": rate_score,
            "wpm": wpm,
            "rate_status": rate_status,
            "long_pauses": long_pauses,
            "total_pauses": len(pauses),
            "pause_ratio": round(pause_ratio, 3),
        }

    # ------------------------------------------------------------------
    # Completeness scoring
    # ------------------------------------------------------------------

    def _compute_completeness(
        self,
        original_sentence: str,
        transcribed_text: str,
    ) -> Dict[str, Any]:
        """Compute completeness — did the child say all the words?"""
        expected_words = original_sentence.lower().split()
        spoken_words = transcribed_text.lower().split()

        # Simple word set comparison
        expected_set = set(w.strip(".,!?") for w in expected_words)
        spoken_set = set(w.strip(".,!?") for w in spoken_words)

        missing = expected_set - spoken_set
        extra = spoken_set - expected_set

        if len(expected_words) > 0:
            completeness_score = round(
                (len(expected_set - missing) / len(expected_set)) * 100, 1
            )
        else:
            completeness_score = 0

        return {
            "completeness_score": completeness_score,
            "expected_words": len(expected_words),
            "spoken_words": len(spoken_words),
            "missing_words": list(missing),
            "extra_words": list(extra),
        }

    # ------------------------------------------------------------------
    # Grammar analysis (text comparison)
    # ------------------------------------------------------------------

    def _analyze_grammar(
        self,
        original_sentence: str,
        transcribed_text: str,
        grade: str,
        phoneme_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyze grammar by comparing original vs transcribed text.

        Uses phoneme-level data when available to detect missing words that
        Whisper's auto-correction would hide. For example, if a child skips
        "the" entirely, Whisper might still output "the" from context, but
        wav2vec2 phoneme data will show the phonemes as omitted.
        """
        original_words = original_sentence.lower().strip(".,!?").split()
        transcribed_words = transcribed_text.lower().strip(".,!?").split()

        issues = []

        # Missing words — use phoneme data if available for accuracy
        original_set = set(original_words)
        transcribed_set = set(transcribed_words)
        missing = original_set - transcribed_set
        extra = transcribed_set - original_set

        # If we have phoneme completeness data, use it instead of Whisper
        if phoneme_result and phoneme_result.get("missing_words"):
            phoneme_missing = set(phoneme_result["missing_words"])
            # Merge: phoneme-detected missing words are more reliable
            # but keep Whisper-detected ones too (in case phoneme missed something)
            missing = missing | phoneme_missing

        for word in missing:
            issues.append({
                "type": "missing_word",
                "detail": f"Missing word: '{word}'",
            })

        for word in extra:
            issues.append({
                "type": "extra_word",
                "detail": f"Extra word: '{word}'",
            })

        # Check word order (simple sequence comparison)
        if original_words and transcribed_words:
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, original_words, transcribed_words).ratio()
            if ratio < 1.0 and ratio >= 0.8:
                issues.append({
                    "type": "wrong_order",
                    "detail": "Some words may be in the wrong order",
                })

        # Grammar score: start at 100, deduct for issues
        grammar_score = 100.0
        grammar_score -= len(missing) * 15
        grammar_score -= len(extra) * 10
        if any(i["type"] == "wrong_order" for i in issues):
            grammar_score -= 10
        grammar_score = max(0, min(100, round(grammar_score, 1)))

        return {
            "grammar_score": grammar_score,
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # GPT-4o feedback generation
    # ------------------------------------------------------------------

    def _generate_feedback(
        self,
        original_sentence: str,
        transcribed_text: str,
        grade: str,
        pron_score: float,
        fluency_score: float,
        prosody_score: float,
        grammar_score: float,
        completeness_score: float,
        pron_detail: Dict[str, Any],
        fluency_detail: Dict[str, Any],
        prosody_detail: Dict[str, Any],
        grammar_detail: Dict[str, Any],
        completeness_detail: Dict[str, Any],
        overall_score: float,
    ) -> Dict[str, Any]:
        """Use GPT-4o to generate parent-friendly feedback from computed scores."""
        if not self._openai:
            return {
                "pronunciation_feedback": "",
                "rate_feedback": "",
                "fluency_feedback": "",
                "prosody_feedback": "",
                "grammar_feedback": "",
                "strengths": [],
                "areas_to_improve": [],
                "recommendation": "",
                "parent_tip": "",
            }

        prompt = f"""You are a child speech analysis expert. Below are pre-computed scores for a {grade} grade student's speech sample. Your job is to generate parent-friendly feedback ONLY — do not change or question the scores.

ORIGINAL SENTENCE: "{original_sentence}"
TRANSCRIBED SPEECH: "{transcribed_text}"

PRE-COMPUTED SCORES (do not change these):
- Pronunciation: {pron_score}/100 ({pron_detail.get('correct_count', 0)}/{pron_detail.get('total_count', 0)} phonemes correct, {pron_detail.get('mispronounced_count', 0)} mispronounced, {pron_detail.get('omitted_count', 0)} omitted)
- Fluency: {fluency_score}/100 (WPM: {fluency_detail.get('wpm', 0)}, {fluency_detail.get('long_pauses', 0)} long pauses, pause ratio: {fluency_detail.get('pause_ratio', 0)})
- Speaking Rate: {fluency_detail.get('rate_score', 0)}/100 ({fluency_detail.get('rate_status', 'Unknown')})
- Prosody: {prosody_score}/100 (monotony: {prosody_detail.get('monotony_score', 'N/A')}, rhythm: {prosody_detail.get('rhythm_score', 'N/A')})
- Grammar: {grammar_score}/100 ({len(grammar_detail.get('issues', []))} issues)
- Completeness: {completeness_score}/100 ({completeness_detail.get('spoken_words', 0)}/{completeness_detail.get('expected_words', 0)} words spoken)
- OVERALL: {overall_score}/100

Generate feedback in this exact JSON format:
{{
    "pronunciation_feedback": "child-friendly feedback about pronunciation",
    "rate_feedback": "feedback about speaking pace",
    "fluency_feedback": "feedback about smoothness and pauses",
    "prosody_feedback": "feedback about intonation and expression",
    "grammar_feedback": "feedback about word accuracy and order",
    "strengths": ["list of 1-3 specific strengths"],
    "areas_to_improve": ["list of 1-3 specific areas"],
    "recommendation": "personalized recommendation for the child",
    "parent_tip": "specific tip for parents to help at home"
}}

Rules:
- Be encouraging but honest
- Use simple, parent-friendly language
- Reference specific scores and data points
- Do not invent issues not shown in the data
- Keep feedback concise (1-2 sentences each)
"""

        try:
            response = self._openai.chat.completions.create(
                model=self._settings.openai.analysis_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a child speech analysis expert. "
                            "Always respond with valid JSON only, "
                            "no markdown formatting."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```"):
                result_text = re.sub(r"^```json?\s*", "", result_text)
                result_text = re.sub(r"\s*```$", "", result_text)

            return json.loads(result_text)

        except Exception as exc:
            logger.warning("GPT-4o feedback generation error: %s", exc)
            return {
                "pronunciation_feedback": "",
                "rate_feedback": "",
                "fluency_feedback": "",
                "prosody_feedback": "",
                "grammar_feedback": "",
                "strengths": [],
                "areas_to_improve": [],
                "recommendation": "",
                "parent_tip": "",
            }

    # ------------------------------------------------------------------
    # Fallback: analyze from text only (no audio for GPT-4o)
    # ------------------------------------------------------------------

    async def _analyze_from_text(
        self,
        original_sentence: str,
        transcribed_text: str,
        word_timestamps: List[Dict[str, Any]],
        duration_seconds: float,
        grade: str,
    ) -> Dict[str, Any]:
        """Fallback analysis when raw audio is not available for wav2vec2."""
        # Compute fluency
        fluency_result = self._compute_fluency(word_timestamps, duration_seconds, grade)

        # Compute completeness
        completeness_result = self._compute_completeness(original_sentence, transcribed_text)

        # Grammar
        grammar_result = self._analyze_grammar(original_sentence, transcribed_text, grade)

        # Pronunciation: approximate from word match (no phoneme analysis)
        original_words = set(original_sentence.lower().split())
        spoken_words = set(transcribed_text.lower().split())
        if original_words:
            word_match_ratio = len(original_words & spoken_words) / len(original_words)
        else:
            word_match_ratio = 0
        pron_score = round(word_match_ratio * 100, 1)

        # Prosody: no data without audio
        prosody_score = 0.0
        prosody_result = {}

        # If no transcription, all scores are 0
        if not transcribed_text or not transcribed_text.strip():
            overall_score = 0.0
        else:
            overall_score = round(
                pron_score * 0.35 +
                fluency_result.get("fluency_score", 0) * 0.25 +
                prosody_score * 0.15 +
                grammar_result.get("grammar_score", 0) * 0.15 +
                completeness_result.get("completeness_score", 0) * 0.10,
                1,
            )

        feedback = self._generate_feedback(
            original_sentence, transcribed_text, grade,
            pron_score, fluency_result.get("fluency_score", 0), prosody_score,
            grammar_result.get("grammar_score", 0), completeness_result.get("completeness_score", 0),
            {"correct_count": 0, "total_count": 0, "mispronounced_count": 0, "omitted_count": 0},
            fluency_result, prosody_result, grammar_result, completeness_result,
            overall_score,
        )

        analysis = {
            "pronunciation": {
                "score": pron_score,
                "feedback": feedback.get("pronunciation_feedback", ""),
            },
            "speaking_rate": {
                "score": fluency_result.get("rate_score", 0),
                "wpm": fluency_result.get("wpm", 0),
                "status": fluency_result.get("rate_status", "Unknown"),
                "feedback": feedback.get("rate_feedback", ""),
            },
            "fluency": {
                "score": fluency_result.get("fluency_score", 0),
                "long_pauses_count": fluency_result.get("long_pauses", 0),
                "feedback": feedback.get("fluency_feedback", ""),
            },
            "prosody": {
                "score": prosody_score,
                "feedback": feedback.get("prosody_feedback", ""),
            },
            "grammar": {
                "score": grammar_result.get("grammar_score", 0),
                "issues": grammar_result.get("issues", []),
                "feedback": feedback.get("grammar_feedback", ""),
            },
            "overall": {
                "score": overall_score,
                "status": self._overall_status(overall_score),
                "level": self._overall_level(overall_score),
                "strengths": feedback.get("strengths", []),
                "areas_to_improve": feedback.get("areas_to_improve", []),
                "recommendation": feedback.get("recommendation", ""),
                "parent_tip": feedback.get("parent_tip", ""),
            },
        }

        return {"success": True, "analysis": analysis}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _overall_status(score: float) -> str:
        if score >= 90:
            return "Above"
        elif score >= 75:
            return "At"
        elif score >= 50:
            return "Below"
        return "Well Below"

    @staticmethod
    def _overall_level(score: float) -> str:
        if score >= 90:
            return "Excellent Speaker"
        elif score >= 75:
            return "Good Speaker"
        elif score >= 50:
            return "Developing Speaker"
        return "Needs Improvement"
