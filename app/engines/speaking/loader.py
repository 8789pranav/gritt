"""Question-bank loader for the speaking assessment."""

from __future__ import annotations

import random
from typing import Any, List, Mapping, Optional

from app.core.exceptions import DataFileError
from app.domain.enums import Difficulty, Grade, TestType
from app.domain.models import SpeakingSentence
from app.engines.base import QuestionLoader


class SpeakingSentenceLoader(QuestionLoader[SpeakingSentence]):
    """Reads ``data/questions/speaking/<grade>.json`` into sentences."""

    items_key = "sentences"

    def __init__(self) -> None:
        super().__init__(TestType.SPEAKING)

    def parse_item(self, raw: Mapping[str, Any], grade: Grade) -> SpeakingSentence:
        sentence_id = raw.get("sentence_id")
        if not sentence_id:
            raise DataFileError(
                f"speaking/{grade.file_stem}.json: entry missing 'sentence_id'"
            )

        sentence = raw.get("sentence", "")
        if not sentence.strip():
            raise DataFileError(f"{sentence_id}: sentence text is empty")

        try:
            difficulty = Difficulty(raw.get("difficulty", "medium"))
        except ValueError as exc:
            raise DataFileError(
                f"{sentence_id}: unknown difficulty {raw.get('difficulty')!r}"
            ) from exc

        return SpeakingSentence(
            item_id=sentence_id,
            grade=grade,
            sentence_id=sentence_id,
            sentence=sentence,
            # Trust the text over a stale declared count.
            word_count=raw.get("word_count") or len(sentence.split()),
            difficulty=difficulty,
        )

    def shuffled(
        self,
        grade: Grade,
        *,
        seed: Optional[int] = None,
    ) -> List[SpeakingSentence]:
        """Sentences in random order, so repeat sittings differ."""
        sentences = self.load(grade)
        random.Random(seed).shuffle(sentences)
        return sentences

    def pick_one(
        self,
        grade: Grade,
        *,
        seed: Optional[int] = None,
    ) -> SpeakingSentence:
        """A single random sentence for the one-at-a-time flow."""
        sentences = self.load(grade)
        if not sentences:
            raise DataFileError(f"No speaking sentences for grade {grade.value}")
        return random.Random(seed).choice(sentences)

    def audio_targets(self, grade: Grade) -> List[SpeakingSentence]:
        return self.load(grade)
