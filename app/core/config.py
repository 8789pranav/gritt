"""
Centralised application configuration.

All environment-dependent values are resolved here exactly once and exposed
through a cached :func:`get_settings` accessor. No other module should read
``os.environ`` directly - that keeps configuration a single, testable seam
(dependency inversion) and makes it trivial to override values in tests.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Repository root: app/core/config.py -> app/core -> app -> <root>
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(dotenv_path=BASE_DIR / ".env")


class ConfigurationError(RuntimeError):
    """Raised when a required configuration value is missing or malformed."""


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class FirebaseSettings:
    """Credentials and connection details for Firebase."""

    api_key: Optional[str]
    database_url: Optional[str]
    credentials_base64: Optional[str]

    @property
    def is_configured(self) -> bool:
        return bool(self.credentials_base64 and self.database_url)

    def decode_credentials(self) -> Dict[str, Any]:
        """Decode the base64 service-account blob into a credentials dict."""
        if not self.credentials_base64:
            raise ConfigurationError(
                "FIREBASE_CRED_BASE64 is not set; cannot initialise Firebase Admin SDK"
            )
        try:
            decoded = base64.b64decode(self.credentials_base64).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ConfigurationError(
                "FIREBASE_CRED_BASE64 is not valid base64-encoded UTF-8"
            ) from exc

        try:
            return json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                "FIREBASE_CRED_BASE64 does not decode to valid JSON"
            ) from exc


@dataclass(frozen=True)
class OpenAISettings:
    """OpenAI client configuration for TTS, transcription and analysis."""

    api_key: Optional[str]
    tts_model: str = "tts-1-hd"
    tts_voice: str = "nova"
    transcription_model: str = "whisper-1"
    analysis_model: str = "gpt-4o"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class AWSSettings:
    """AWS credentials used for the Polly text-to-speech fallback."""

    access_key_id: Optional[str]
    secret_access_key: Optional[str]
    region: str = "us-east-1"
    polly_voice: str = "Joanna"
    polly_engine: str = "neural"
    polly_language_code: str = "en-US"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)


@dataclass(frozen=True)
class AudioSettings:
    """Shared narration settings applied across every assessment."""

    default_speed: float = 0.85
    word_speed: float = 0.95
    sentence_speed: float = 1.0
    speaking_speed: float = 0.9
    max_polly_characters: int = 2900


@dataclass(frozen=True)
class PathSettings:
    """Filesystem locations for data files and static assets."""

    base_dir: Path
    data_dir: Path
    questions_dir: Path
    tags_dir: Path
    static_dir: Path

    @classmethod
    def build(cls, base_dir: Path) -> "PathSettings":
        data_dir = base_dir / "data"
        return cls(
            base_dir=base_dir,
            data_dir=data_dir,
            questions_dir=data_dir / "questions",
            tags_dir=data_dir / "tags",
            static_dir=base_dir / "static",
        )


@dataclass(frozen=True)
class Settings:
    """Top-level application settings."""

    app_name: str = "Dear Parent Assessment API"
    app_version: str = "2.0.0"
    debug: bool = False

    cors_origins: List[str] = field(default_factory=lambda: ["*"])

    firebase: FirebaseSettings = field(
        default_factory=lambda: FirebaseSettings(None, None, None)
    )
    openai: OpenAISettings = field(default_factory=lambda: OpenAISettings(None))
    aws: AWSSettings = field(default_factory=lambda: AWSSettings(None, None))
    audio: AudioSettings = field(default_factory=AudioSettings)
    paths: PathSettings = field(default_factory=lambda: PathSettings.build(BASE_DIR))

    # Grades accepted by the public API, in display order.
    supported_grades: List[str] = field(
        default_factory=lambda: ["Kindergarten", "First", "Second", "Third"]
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that environment parsing happens once. Tests can call
    ``get_settings.cache_clear()`` to force a reload after patching env vars.
    """
    return Settings(
        app_name=os.getenv("APP_NAME", "Dear Parent Assessment API"),
        app_version=os.getenv("APP_VERSION", "2.0.0"),
        debug=_get_bool("DEBUG", False),
        cors_origins=[
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "*").split(",")
            if origin.strip()
        ],
        firebase=FirebaseSettings(
            api_key=os.getenv("FIREBASE_API_KEY"),
            database_url=os.getenv("FIREBASE_DB_URL"),
            credentials_base64=os.getenv("FIREBASE_CRED_BASE64"),
        ),
        openai=OpenAISettings(
            api_key=os.getenv("OPENAI_API_KEY"),
            tts_model=os.getenv("OPENAI_TTS_MODEL", "tts-1-hd"),
            tts_voice=os.getenv("OPENAI_TTS_VOICE", "nova"),
            transcription_model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1"),
            analysis_model=os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-4o"),
        ),
        aws=AWSSettings(
            access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            polly_voice=os.getenv("AWS_POLLY_VOICE", "Joanna"),
            polly_engine=os.getenv("AWS_POLLY_ENGINE", "neural"),
        ),
        audio=AudioSettings(
            default_speed=_get_float("AUDIO_DEFAULT_SPEED", 0.85),
            word_speed=_get_float("AUDIO_WORD_SPEED", 0.95),
            sentence_speed=_get_float("AUDIO_SENTENCE_SPEED", 1.0),
            speaking_speed=_get_float("AUDIO_SPEAKING_SPEED", 0.9),
            max_polly_characters=_get_int("AUDIO_MAX_POLLY_CHARS", 2900),
        ),
        paths=PathSettings.build(BASE_DIR),
    )
