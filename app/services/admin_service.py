"""Admin service: stats, feedback, audio pre-generation, user management."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.security import verify_admin, verify_token
from app.domain.enums import Grade
from app.engines.registry import (
    comprehension_engine,
    logic_engine,
    speaking_engine,
    spelling_engine,
)
from app.infrastructure.repositories import (
    AudioCacheRepository,
    FeedbackRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)

VALID_GRADES = ["Kindergarten", "First", "Second", "Third"]


class AdminService:
    """Admin-only operations: stats, feedback, audio pre-generation."""

    def __init__(self) -> None:
        from app.infrastructure.firebase import get_firebase_client

        self._client = get_firebase_client()
        self._users = UserRepository(self._client)
        self._feedback = FeedbackRepository(self._client)
        self._cache = AudioCacheRepository(self._client)

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- make admin --------------------------------------------------------
    def make_admin(self, id_token: str, target_email: str) -> Dict[str, Any]:
        verify_admin(id_token)
        target_email = target_email.strip().lower()
        all_users = self._users.get_all()

        target_uid = None
        for uid, data in all_users.items():
            if data.get("email", "").strip().lower() == target_email:
                target_uid = uid
                break

        if not target_uid:
            from app.core.exceptions import NotFoundError

            raise NotFoundError(f"User with email '{target_email}' not found")

        self._users.update(target_uid, {"isAdmin": True})
        return {
            "message": f"User {target_email} is now an admin",
            "updated": True,
            "targetUid": target_uid,
        }

    # -- stats -------------------------------------------------------------
    def get_stats(self, id_token: str) -> Dict[str, Any]:
        try:
            verify_admin(id_token)
        except Exception:
            return {"isAdmin": False, "totalUsers": 0, "users": []}

        all_users_raw = self._users.get_all()
        auth_users_map: Dict[str, Any] = {}

        try:
            from firebase_admin import auth as firebase_auth

            page = firebase_auth.list_users()
            while page is not None:
                for user in page.users:
                    auth_users_map[user.uid] = user
                page = page.get_next_page() if page.has_next_page else None
        except Exception as exc:
            logger.warning("list_users error: %s", exc)

        user_list = []
        for uid, data in all_users_raw.items():
            email = data.get("email", "N/A")
            auth_user = auth_users_map.get(uid)
            if auth_user and auth_user.user_metadata.creation_timestamp:
                created_at = int(auth_user.user_metadata.creation_timestamp / 1000)
            else:
                created_at = data.get("createdAt")
                if not created_at or not isinstance(created_at, (int, float)):
                    created_at = int(time.time()) - (30 * 24 * 3600)

            joined_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(created_at))
            user_list.append({
                "email": email,
                "joinedDate": joined_date,
                "timestamp": created_at,
            })

        user_list.sort(key=lambda x: x["timestamp"], reverse=True)
        final_users = [
            {"email": u["email"], "joinedDate": u["joinedDate"]}
            for u in user_list
        ]
        return {
            "isAdmin": True,
            "totalUsers": len(final_users),
            "users": final_users,
        }

    # -- feedback ----------------------------------------------------------
    def get_all_feedback(self, id_token: str) -> Dict[str, Any]:
        verify_admin(id_token)
        feedbacks = self._feedback.get_all()
        feedback_list = list(feedbacks.values())
        return {"count": len(feedback_list), "feedbacks": feedback_list}

    def submit_feedback(self, id_token: str, child_id: str, answers: Dict[str, str]) -> Dict[str, Any]:
        decoded = verify_token(id_token)
        uid = decoded["uid"]
        user_email = decoded.get("email", "unknown@example.com")

        from app.infrastructure.repositories import ChildRepository

        child_repo = ChildRepository(self._client)
        if not child_repo.get(uid, child_id):
            from app.core.exceptions import ChildNotFoundError

            raise ChildNotFoundError(child_id)

        feedback_id = str(uuid.uuid4())
        payload = {
            "user_id": uid,
            "email": user_email,
            "child_id": child_id,
            "answers": answers,
            "timestamp": self._utc_now() + "Z",
        }
        self._feedback.save(feedback_id, payload)
        return {
            "message": "Feedback saved successfully",
            "feedback_id": feedback_id,
            "saved_under": "parent_feedback",
            "email": user_email,
            "timestamp": payload["timestamp"],
        }

    # -- audio pre-generation ----------------------------------------------
    async def pregenerate_logic_audio(self, id_token: str) -> Dict[str, Any]:
        verify_admin(id_token)
        from app.services.audio_service import AudioService

        audio_svc = AudioService()
        results = {"generated": [], "failed": [], "skipped": []}

        engine = logic_engine()

        for grade_str in VALID_GRADES:
            grade_enum = Grade.parse(grade_str)
            items = engine.get_items(grade_enum)
            for item in items:
                cached = self._cache.get_node(f"logic_audio/{grade_str}/{item.item_id}")
                if cached and cached.get("question_audio"):
                    results["skipped"].append(f"{grade_str}/{item.item_id}")
                    continue

                q_audio = await audio_svc._tts.synthesize(item.question_text)
                if not q_audio:
                    results["failed"].append(f"{grade_str}/{item.item_id}")
                    continue

                opt_audios = []
                for opt in item.options:
                    opt_audios.append(await audio_svc._tts.synthesize(opt.text))

                self._cache.set_node(
                    f"logic_audio/{grade_str}/{item.item_id}",
                    {
                        "question_audio": q_audio,
                        "option_audios": opt_audios,
                        "voice": "nova",
                        "generated_at": self._utc_now(),
                    },
                )
                results["generated"].append(f"{grade_str}/{item.item_id}")

        return {
            "success": True,
            "message": "Logic audio pre-generation complete",
            "results": results,
        }

    async def pregenerate_speaking_audio(self, id_token: str) -> Dict[str, Any]:
        verify_admin(id_token)
        from app.services.audio_service import AudioService

        audio_svc = AudioService()
        results = {"generated": [], "failed": [], "skipped": []}

        engine = speaking_engine()
        for grade_str in VALID_GRADES:
            grade_enum = Grade.parse(grade_str)
            sentences = engine.loader.load(grade_enum)
            existing = self._cache.get_all_in(f"speaking_audio/{grade_str}")

            for s in sentences:
                if s.sentence_id in existing and existing[s.sentence_id].get("audio_base64"):
                    results["skipped"].append(f"{grade_str}/{s.sentence_id}")
                else:
                    audio = await audio_svc._tts.synthesize(s.sentence, speed=0.9)
                    if audio:
                        self._cache.set_node(
                            f"speaking_audio/{grade_str}/{s.sentence_id}",
                            {
                                "audio_base64": audio,
                                "voice": "nova",
                                "generated_at": self._utc_now(),
                            },
                        )
                        results["generated"].append(f"{grade_str}/{s.sentence_id}")
                    else:
                        results["failed"].append(f"{grade_str}/{s.sentence_id}")

        return {
            "success": True,
            "message": "Speaking audio pre-generation complete",
            "results": results,
        }

    async def pregenerate_spelling_audio(self, id_token: str) -> Dict[str, Any]:
        verify_admin(id_token)
        from app.services.audio_service import AudioService

        audio_svc = AudioService()
        results = {"generated": [], "failed": [], "skipped": []}

        engine = spelling_engine()
        for grade_str in VALID_GRADES:
            grade_enum = Grade.parse(grade_str)
            words = engine.loader.audio_targets(grade_enum)
            if not words:
                continue

            existing = self._cache.get_all_in(f"spelling_audio/{grade_str}")

            for w in words:
                if w.word in existing and existing[w.word].get("word_audio"):
                    results["skipped"].append(f"{grade_str}/{w.word}")
                else:
                    w_b64 = await audio_svc._tts.synthesize(w.word, speed=0.95)
                    s_b64 = await audio_svc._tts.synthesize(w.sentence, speed=1.0)
                    if w_b64:
                        self._cache.set_node(
                            f"spelling_audio/{grade_str}/{w.word}",
                            {
                                "word_audio": w_b64,
                                "sentence_audio": s_b64,
                                "voice": "nova",
                                "generated_at": self._utc_now(),
                            },
                        )
                        results["generated"].append(f"{grade_str}/{w.word}")
                    else:
                        results["failed"].append(f"{grade_str}/{w.word}")

        return {
            "success": True,
            "message": "Spelling audio pre-generation complete",
            "results": results,
        }

    async def pregenerate_story_audio(self, id_token: str) -> Dict[str, Any]:
        verify_admin(id_token)
        from app.services.audio_service import AudioService

        audio_svc = AudioService()
        results = {"generated": [], "failed": [], "skipped": []}

        engine = comprehension_engine()
        for grade_str in VALID_GRADES:
            grade_enum = Grade.parse(grade_str)
            stories = engine.loader.load(grade_enum)
            for story in stories:
                cached = self._cache.get_node(f"story_audio/{grade_str}/{story.story_id}")
                if cached and cached.get("audio_base64"):
                    results["skipped"].append(f"{grade_str}/{story.story_id}")
                    continue

                audio_b64 = await audio_svc._tts.synthesize(story.story_text, speed=0.85)
                if audio_b64:
                    self._cache.set_node(
                        f"story_audio/{grade_str}/{story.story_id}",
                        {
                            "audio_base64": audio_b64,
                            "title": story.title,
                            "voice": "nova",
                            "generated_at": self._utc_now(),
                        },
                    )
                    results["generated"].append(f"{grade_str}/{story.story_id}")
                else:
                    results["failed"].append(f"{grade_str}/{story.story_id}")

        return {
            "success": True,
            "message": "Audio pre-generation complete",
            "results": results,
        }

    async def regenerate_story_audio(self, id_token: str,
                                     grade: Optional[str] = None,
                                     story_id: Optional[str] = None) -> Dict[str, Any]:
        verify_admin(id_token)
        from app.services.audio_service import AudioService

        audio_svc = AudioService()
        results = {"regenerated": [], "failed": []}

        engine = comprehension_engine()
        if grade and story_id:
            grade_enum = Grade.parse(grade)
            stories_to_process = [(grade, s) for s in engine.loader.load(grade_enum) if s.story_id == story_id]
        elif grade:
            grade_enum = Grade.parse(grade)
            stories_to_process = [(grade, s) for s in engine.loader.load(grade_enum)]
        else:
            stories_to_process = [
                (g, s)
                for g in VALID_GRADES
                for s in engine.loader.load(Grade.parse(g))
            ]

        for g, story in stories_to_process:
            if story is None:
                continue
            audio_b64 = await audio_svc._tts.synthesize(story.story_text, speed=0.85)
            if audio_b64:
                self._cache.set_node(
                    f"story_audio/{g}/{story.story_id}",
                    {
                        "audio_base64": audio_b64,
                        "title": story.title,
                        "voice": "nova",
                        "generated_at": self._utc_now(),
                    },
                )
                results["regenerated"].append(f"{g}/{story.story_id}")
            else:
                results["failed"].append(f"{g}/{story.story_id}")

        return {"success": True, "results": results}
