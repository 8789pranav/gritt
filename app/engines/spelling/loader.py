"""Question-bank loader for the spelling assessment."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Mapping, Optional

from app.core.exceptions import DataFileError
from app.domain.enums import Grade, TestType, WordType
from app.domain.models import SpellingWord
from app.engines.base import QuestionLoader

#: Number of words sampled per Kindergarten sitting.
KINDERGARTEN_TOTAL_SAMPLE = 15


class SpellingWordLoader(QuestionLoader[SpellingWord]):
    """Reads ``data/questions/spelling/<grade>.json`` into :class:`SpellingWord`."""

    items_key = "words"

    def __init__(self) -> None:
        super().__init__(TestType.SPELLING)

    def parse_item(self, raw: Mapping[str, Any], grade: Grade) -> SpellingWord:
        word = raw.get("word")
        if not word:
            raise DataFileError(
                f"spelling/{grade.file_stem}.json: entry missing 'word'"
            )

        try:
            word_type = WordType(raw.get("type", "regular"))
        except ValueError as exc:
            raise DataFileError(
                f"{word}: unknown word type {raw.get('type')!r}"
            ) from exc

        return SpellingWord(
            item_id=f"{grade.file_stem}:{word}",
            grade=grade,
            word=word,
            word_type=word_type,
            sentence=raw.get("sentence", ""),
            features={
                name: str(value)
                for name, value in (raw.get("features") or {}).items()
            },
        )

    # -- test assembly ------------------------------------------------------
    def build_test(
        self,
        grade: Grade,
        *,
        seed: Optional[int] = None,
    ) -> List[SpellingWord]:
        """Return the word set for one sitting.

        Kindergarten draws a random sample of 15 words from the Kindergarten
        bank only. Every other grade uses its full list.
        """
        words = self.load(grade)

        if grade is not Grade.KINDERGARTEN:
            return words

        rng = random.Random(seed)
        sample = list(words)
        rng.shuffle(sample)
        return sample[:KINDERGARTEN_TOTAL_SAMPLE]


    def audio_targets(self, grade: Grade) -> List[SpellingWord]:
        """Words that need narration - every word that has a sentence."""
        return [w for w in self.load(grade) if w.sentence]
