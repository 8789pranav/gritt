"""Infrastructure layer: external service clients and data access."""

from app.infrastructure.firebase import FirebaseClient, get_firebase_client
from app.infrastructure.repositories import UserRepository, ChildRepository, ScoreRepository, AudioCacheRepository, FeedbackRepository
from app.infrastructure.tts import TTSProvider, get_tts_provider
from app.infrastructure.speech import SpeechProvider, get_speech_provider

__all__ = [
    "FirebaseClient",
    "get_firebase_client",
    "UserRepository",
    "ChildRepository",
    "ScoreRepository",
    "AudioCacheRepository",
    "FeedbackRepository",
    "TTSProvider",
    "get_tts_provider",
    "SpeechProvider",
    "get_speech_provider",
]
