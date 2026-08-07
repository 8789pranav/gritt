"""Text-to-speech provider abstraction.

Tries OpenAI TTS first (high-quality ``nova`` voice) and falls back to
AWS Polly (``Joanna`` neural) when OpenAI is unavailable or errors.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

import boto3
import openai

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class TTSProvider:
    """Unified TTS facade over OpenAI and AWS Polly."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._openai: Optional[openai.OpenAI] = None
        self._polly = None
        self._init_openai()
        self._init_polly()

    def _init_openai(self) -> None:
        if self._settings.openai.is_configured:
            self._openai = openai.OpenAI(api_key=self._settings.openai.api_key)

    def _init_polly(self) -> None:
        aws = self._settings.aws
        if aws.is_configured:
            self._polly = boto3.client(
                "polly",
                aws_access_key_id=aws.access_key_id,
                aws_secret_access_key=aws.secret_access_key,
                region_name=aws.region,
            )

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> Optional[str]:
        """Return base64-encoded MP3 for *text*, or ``None`` on failure."""
        if not text or not text.strip():
            return None

        voice = voice or self._settings.openai.tts_voice
        speed = speed if speed is not None else self._settings.audio.default_speed

        if self._openai:
            try:
                response = self._openai.audio.speech.create(
                    model=self._settings.openai.tts_model,
                    voice=voice,
                    input=text.strip(),
                    speed=speed,
                )
                return base64.b64encode(response.content).decode("utf-8")
            except Exception as exc:
                logger.warning("OpenAI TTS error: %s", exc)

        if self._polly:
            try:
                aws = self._settings.aws
                ssml = (
                    f'<speak><prosody rate="{int(speed * 100)}%">'
                    f"{text.strip()[: self._settings.audio.max_polly_characters]}"
                    f"</prosody></speak>"
                )
                audio_response = self._polly.synthesize_speech(
                    Text=ssml,
                    TextType="ssml",
                    OutputFormat="mp3",
                    VoiceId=aws.polly_voice,
                    Engine=aws.polly_engine,
                    LanguageCode=aws.polly_language_code,
                )
                return base64.b64encode(
                    audio_response["AudioStream"].read()
                ).decode("utf-8")
            except Exception as exc:
                logger.warning("Polly TTS error: %s", exc)

        return None


_tts: Optional[TTSProvider] = None


def get_tts_provider() -> TTSProvider:
    global _tts
    if _tts is None:
        _tts = TTSProvider()
    return _tts


def reset_tts() -> None:
    global _tts
    _tts = None
