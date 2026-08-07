"""Speech analysis provider: Whisper transcription + GPT-4o analysis."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

import openai

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SpeechProvider:
    """Wraps OpenAI Whisper (transcription) and GPT-4o (speech analysis)."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._openai: Optional[openai.OpenAI] = None
        if self._settings.openai.is_configured:
            self._openai = openai.OpenAI(api_key=self._settings.openai.api_key)

    @property
    def is_configured(self) -> bool:
        return self._openai is not None

    async def transcribe(
        self,
        audio_base64: str,
        audio_format: str = "mp3",
    ) -> Dict[str, Any]:
        """Transcribe audio via Whisper and return word-level timestamps."""
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

    async def analyze(
        self,
        original_sentence: str,
        transcribed_text: str,
        word_timestamps: List[Dict[str, Any]],
        duration_seconds: float,
        grade: str,
    ) -> Dict[str, Any]:
        """Use GPT-4o to analyse speech quality and return structured scores."""
        if not self._openai:
            return {
                "success": False,
                "error": "OpenAI API key not configured",
                "analysis": None,
            }

        prompt = self._build_prompt(
            original_sentence,
            transcribed_text,
            word_timestamps,
            duration_seconds,
            grade,
        )

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
                max_tokens=2000,
            )

            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```"):
                result_text = re.sub(r"^```json?\s*", "", result_text)
                result_text = re.sub(r"\s*```$", "", result_text)

            analysis = json.loads(result_text)
            return {"success": True, "analysis": analysis}

        except json.JSONDecodeError as exc:
            logger.warning("GPT-4o JSON parse error: %s", exc)
            return {
                "success": False,
                "error": f"Failed to parse AI response: {exc}",
                "analysis": None,
            }
        except Exception as exc:
            logger.warning("GPT-4o analysis error: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "analysis": None,
            }

    @staticmethod
    def _build_prompt(
        original_sentence: str,
        transcribed_text: str,
        word_timestamps: List[Dict[str, Any]],
        duration_seconds: float,
        grade: str,
    ) -> str:
        return f"""You are an expert speech therapist and language teacher for children. Analyze the following speech sample from a {grade} grade student.

ORIGINAL SENTENCE (what they should say):
"{original_sentence}"

WHAT THE CHILD ACTUALLY SAID (transcribed):
"{transcribed_text}"

WORD TIMING DATA:
{json.dumps(word_timestamps, indent=2) if word_timestamps else "No detailed timing available"}

TOTAL DURATION: {duration_seconds} seconds
EXPECTED WORD COUNT: {len(original_sentence.split())}
ACTUAL WORD COUNT: {len(transcribed_text.split())}

Please analyze and provide scores (0-100) and feedback for:

1. PRONUNCIATION ACCURACY: How accurately did the child pronounce each word?
2. SPEAKING RATE/PACE: Is their speaking speed appropriate? (normal for children: 100-150 WPM)
3. FLUENCY & GAPS: How smoothly did they speak? (pauses > 1 second are concerning)
4. GRAMMAR & WORD ORDER: Did they maintain correct grammar?

Respond in this exact JSON format:
{{
    "pronunciation": {{
        "score": <0-100>,
        "correct_words": <number>,
        "total_words": <number>,
        "mispronounced_words": [
            {{"expected": "word", "heard": "what_child_said", "feedback": "specific tip"}}
        ],
        "feedback": "child-friendly feedback"
    }},
    "speaking_rate": {{
        "score": <0-100>,
        "wpm": <calculated words per minute>,
        "status": "Too Slow/Slightly Slow/Perfect/Slightly Fast/Too Fast",
        "feedback": "child-friendly feedback"
    }},
    "fluency": {{
        "score": <0-100>,
        "long_pauses_count": <number>,
        "feedback": "child-friendly feedback"
    }},
    "grammar": {{
        "score": <0-100>,
        "issues": [
            {{"type": "missing_word/extra_word/wrong_order", "detail": "description"}}
        ],
        "feedback": "child-friendly feedback"
    }},
    "overall": {{
        "score": <weighted average>,
        "status": "Above/At/Below",
        "level": "Excellent Speaker/Good Speaker/Developing Speaker",
        "strengths": ["list of strengths"],
        "areas_to_improve": ["list of areas"],
        "recommendation": "personalized recommendation for the child",
        "parent_tip": "tip for parents to help"
    }}
}}"""


_speech: Optional[SpeechProvider] = None


def get_speech_provider() -> SpeechProvider:
    global _speech
    if _speech is None:
        _speech = SpeechProvider()
    return _speech


def reset_speech() -> None:
    global _speech
    _speech = None
