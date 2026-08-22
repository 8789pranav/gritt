"""Audio generation & caching service.

Uses engine ``narration_targets()`` and ``get_items()`` to know what audio
to generate, then caches results in Firebase via ``AudioCacheRepository``.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import InvalidGradeError, NotFoundError
from app.core.security import verify_child, verify_token
from app.domain.enums import Grade
from app.engines.registry import (
    comprehension_engine,
    logic_engine,
    speaking_engine,
    spelling_engine,
)
from app.infrastructure.repositories import AudioCacheRepository
from app.infrastructure.tts import TTSProvider

logger = logging.getLogger(__name__)

VALID_GRADES = ["Kindergarten", "First", "Second", "Third"]


def _parse_grade(grade_str: str) -> Grade:
    try:
        return Grade.parse(grade_str)
    except ValueError:
        raise InvalidGradeError(grade_str, VALID_GRADES)


class AudioService:
    """TTS generation, Firebase audio caching, and pre-generation jobs."""

    def __init__(self, tts: Optional[TTSProvider] = None) -> None:
        from app.infrastructure.firebase import get_firebase_client

        self._client = get_firebase_client()
        self._cache = AudioCacheRepository(self._client)
        self._tts = tts or TTSProvider()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- single word / text audio ------------------------------------------
    async def generate_text_audio(self, id_token: str, text: str) -> Dict[str, Any]:
        verify_token(id_token)
        audio_b64 = await self._tts.synthesize(text, speed=0.9)
        return {"base64_audio": audio_b64}

    # -- spelling: all words for a grade -----------------------------------
    async def generate_all_grade_audio(self, id_token: str, grade: str) -> Dict[str, Any]:
        grade_enum = _parse_grade(grade)
        engine = spelling_engine()
        if grade_enum.name == "KINDERGARTEN":
            words = engine.build_test(grade_enum)
        else:
            words = engine.loader.audio_targets(grade_enum)
        if not words:
            raise NotFoundError("No words with sentences found")

        shuffled = list(words)
        random.shuffle(shuffled)

        all_cached = self._cache.get_all_in(f"spelling_audio/{grade}")

        to_generate = [
            w for w in shuffled
            if w.word not in all_cached
            or not all_cached[w.word].get("word_audio")
        ]

        if to_generate:
            async def gen_word(w):
                w_b64 = await self._tts.synthesize(w.word, speed=0.95)
                s_b64 = await self._tts.synthesize(w.sentence, speed=1.0)
                return w, w_b64, s_b64

            generated = await asyncio.gather(*[gen_word(w) for w in to_generate])
            for word, w_b64, s_b64 in generated:
                if w_b64:
                    self._cache.set_node(
                        f"spelling_audio/{grade}/{word.word}",
                        {
                            "word_audio": w_b64,
                            "sentence_audio": s_b64,
                            "voice": "nova",
                            "generated_at": self._utc_now(),
                        },
                    )
                    all_cached[word.word] = {
                        "word_audio": w_b64,
                        "sentence_audio": s_b64,
                    }

        audio_files = []
        for w in shuffled:
            cached = all_cached.get(w.word, {})
            audio_files.append({
                "word": w.word,
                "word_type": w.word_type.value,
                "word_audio": cached.get("word_audio"),
                "sentence_audio": cached.get("sentence_audio"),
                "word_filename": f"{w.word_type.value}/{w.word}_word.mp3",
                "sentence_filename": f"{w.word_type.value}/{w.word}_sentence.mp3",
            })
        return {"grade": grade, "audio_files": audio_files}

    # -- logic: test with audio --------------------------------------------
    async def logic_test_with_audio(self, id_token: str, child_id: str, grade: str) -> Dict[str, Any]:
        verify_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = logic_engine()
        items = engine.get_items(grade_enum)

        all_cached = self._cache.get_all_in(f"logic_audio/{grade}")

        to_generate = [
            item for item in items
            if item.item_id not in all_cached
            or not all_cached[item.item_id].get("question_audio")
        ]

        if to_generate:
            async def gen_item(item):
                q_audio = await self._tts.synthesize(item.question_text)
                opt_audios = await asyncio.gather(
                    *[self._tts.synthesize(opt.text) for opt in item.options]
                )
                return item.item_id, q_audio, list(opt_audios)

            generated = await asyncio.gather(*[gen_item(i) for i in to_generate])
            for item_id, q_audio, o_audios in generated:
                if q_audio:
                    self._cache.set_node(
                        f"logic_audio/{grade}/{item_id}",
                        {
                            "question_audio": q_audio,
                            "option_audios": o_audios,
                            "voice": "nova",
                            "generated_at": self._utc_now(),
                        },
                    )
                    all_cached[item_id] = {
                        "question_audio": q_audio,
                        "option_audios": o_audios,
                    }

        formatted = []
        for item in items:
            cached = all_cached.get(item.item_id, {})
            q_audio = cached.get("question_audio")
            o_audios = cached.get("option_audios", [])
            fmt: Dict[str, Any] = {
                "item_id": item.item_id,
                "item_number": item.item_number,
                "item_type": item.item_type,
                "question_text": item.question_text,
                "difficulty": item.difficulty.value,
                "question_audio_base64": q_audio,
                "audio_source": "cached" if item.item_id in all_cached else "not_cached",
                "options": [
                    {
                        "index": opt.index,
                        "text": opt.text,
                        "image_url": opt.image_url,
                        "audio_base64": o_audios[i] if i < len(o_audios) else None,
                    }
                    for i, opt in enumerate(item.options)
                ],
            }
            if hasattr(item, "sort_config") and item.sort_config:
                fmt["sort_config"] = {
                    "cards": item.sort_config.cards,
                    "rounds": [
                        {
                            "round_number": r.round_number,
                            "sort_rule": r.sort_rule,
                            "num_bins": r.num_bins,
                            "rule_shown": r.rule_shown,
                        }
                        for r in item.sort_config.rounds
                    ],
                }
            formatted.append(fmt)

        return {
            "success": True,
            "test_id": str(_uuid.uuid4()),
            "grade": grade,
            "total_items": len(items),
            "instructions": (
                "Listen to each question carefully, then choose your answer. "
                "Think about patterns, relationships, and rules. Take your time!"
            ),
            "items": formatted,
        }

    # -- speaking: get sentence with audio ---------------------------------
    async def get_speaking_sentence(self, id_token: str, child_id: str, grade: str) -> Dict[str, Any]:
        verify_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = speaking_engine()
        selected = engine.pick_sentence(grade_enum)

        cached = self._cache.get_node(
            f"speaking_audio/{grade}/{selected.sentence_id}"
        ) or {}
        audio_b64 = cached.get("audio_base64")
        if not audio_b64:
            audio_b64 = await self._tts.synthesize(selected.sentence, speed=0.9)
            if audio_b64:
                self._cache.set_node(
                    f"speaking_audio/{grade}/{selected.sentence_id}",
                    {
                        "audio_base64": audio_b64,
                        "voice": "nova",
                        "generated_at": self._utc_now(),
                    },
                )
        return {
            "grade": grade,
            "sentence_id": selected.sentence_id,
            "sentence": selected.sentence,
            "word_count": selected.word_count,
            "difficulty": selected.difficulty.value,
            "audio_base64": audio_b64,
            "instructions": "Listen to the sentence, then record yourself saying it clearly.",
        }

    # -- speaking: all sentences with audio --------------------------------
    async def get_all_speaking_sentences(self, id_token: str, child_id: str, grade: str) -> Dict[str, Any]:
        verify_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = speaking_engine()
        sentences = engine.shuffled_sentences(grade_enum)

        all_cached = self._cache.get_all_in(f"speaking_audio/{grade}")

        to_gen = [
            s for s in sentences
            if s.sentence_id not in all_cached
            or not all_cached[s.sentence_id].get("audio_base64")
        ]

        if to_gen:
            async def gen(s):
                audio = await self._tts.synthesize(s.sentence, speed=0.9)
                return s.sentence_id, audio

            generated = await asyncio.gather(*[gen(s) for s in to_gen])
            for sid, audio_b64 in generated:
                if audio_b64:
                    self._cache.set_node(
                        f"speaking_audio/{grade}/{sid}",
                        {
                            "audio_base64": audio_b64,
                            "voice": "nova",
                            "generated_at": self._utc_now(),
                        },
                    )
                    all_cached[sid] = {"audio_base64": audio_b64}

        result = []
        for s in sentences:
            cached = all_cached.get(s.sentence_id, {})
            result.append({
                "sentence_id": s.sentence_id,
                "sentence": s.sentence,
                "word_count": s.word_count,
                "difficulty": s.difficulty.value,
                "audio_base64": cached.get("audio_base64"),
            })
        return {
            "grade": grade,
            "total_sentences": len(result),
            "sentences": result,
        }

    # -- comprehension: stories with audio ---------------------------------
    async def get_comprehension_stories(self, id_token: str, child_id: str, grade: str) -> Dict[str, Any]:
        verify_child(id_token, child_id)
        grade_enum = _parse_grade(grade)
        engine = comprehension_engine()
        stories = engine.get_items(grade_enum)

        all_cached = self._cache.get_all_in(f"story_audio/{grade}")

        to_gen = [
            s for s in stories
            if s.story_id not in all_cached
            or not all_cached[s.story_id].get("audio_base64")
        ]

        if to_gen:
            async def gen(s):
                audio = await self._tts.synthesize(s.story_text, speed=0.85)
                return s.story_id, audio

            generated = await asyncio.gather(*[gen(s) for s in to_gen])
            for sid, audio_b64 in generated:
                if audio_b64:
                    story_obj = next(s for s in stories if s.story_id == sid)
                    self._cache.set_node(
                        f"story_audio/{grade}/{sid}",
                        {
                            "audio_base64": audio_b64,
                            "title": story_obj.title,
                            "voice": "nova",
                            "generated_at": self._utc_now(),
                        },
                    )
                    all_cached[sid] = {"audio_base64": audio_b64, "title": story_obj.title}

        result_stories = []
        for story in stories:
            cached = all_cached.get(story.story_id, {})
            audio_b64 = cached.get("audio_base64")
            audio_source = "cached_openai" if audio_b64 else "failed"

            questions_for_client = [
                {
                    "id": q.question_id,
                    "question": q.question,
                    "options": q.options,
                }
                for q in story.questions
            ]

            result_stories.append({
                "story_id": story.story_id,
                "title": story.title,
                "story_text": story.story_text,
                "story_audio_base64": audio_b64,
                "audio_source": audio_source,
                "duration_estimate": story.duration_estimate,
                "questions": questions_for_client,
                "total_questions": len(questions_for_client),
            })

        return {
            "grade": grade,
            "total_stories": len(result_stories),
            "total_questions": sum(s["total_questions"] for s in result_stories),
            "instructions": "Listen to each story carefully, then answer the questions. Each question has 4 options.",
            "stories": result_stories,
        }
