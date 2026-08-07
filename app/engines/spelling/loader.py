"""Question-bank loader for the spelling assessment."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Mapping, Optional

from app.core.exceptions import DataFileError
from app.domain.enums import Grade, TestType, WordType
from app.domain.models import SpellingWord
from app.engines.base import QuestionLoader

#: Kindergarten has a much larger regular-word pool than the other grades, so a
#: balanced subset is sampled per sitting rather than testing every word.
KINDERGARTEN_REGULAR_SAMPLE = 10

#: Short vowels used to balance the Kindergarten sample.
_SHORT_VOWELS = "aeiou"


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

        Kindergarten draws a vowel-balanced sample of regular words; every
        other grade uses its full list. Sight and nonsense words are always
        included in full.
        """
        words = self.load(grade)

        if grade is not Grade.KINDERGARTEN:
            return words

        regular = [w for w in words if w.word_type is WordType.REGULAR]
        others = [w for w in words if w.word_type is not WordType.REGULAR]

        return self._balanced_sample(regular, seed=seed) + others

    def _balanced_sample(
        self,
        regular: List[SpellingWord],
        *,
        seed: Optional[int] = None,
    ) -> List[SpellingWord]:
        """Pick a sample spread across the five short vowels where possible."""
        if len(regular) <= KINDERGARTEN_REGULAR_SAMPLE:
            return list(regular)

        rng = random.Random(seed)

        by_vowel: Dict[str, List[SpellingWord]] = {v: [] for v in _SHORT_VOWELS}
        unbucketed: List[SpellingWord] = []

        for word in regular:
            vowel = self._short_vowel_of(word)
            if vowel in by_vowel:
                by_vowel[vowel].append(word)
            else:
                unbucketed.append(word)

        # Take two per vowel first so every vowel sound is represented.
        selected: List[SpellingWord] = []
        per_vowel = max(1, KINDERGARTEN_REGULAR_SAMPLE // len(_SHORT_VOWELS))
        for vowel in _SHORT_VOWELS:
            bucket = by_vowel[vowel]
            rng.shuffle(bucket)
            selected.extend(bucket[:per_vowel])

        # Top up from whatever is left if the buckets were uneven.
        if len(selected) < KINDERGARTEN_REGULAR_SAMPLE:
            chosen = {w.word for w in selected}
            remainder = [w for w in regular if w.word not in chosen]
            rng.shuffle(remainder)
            selected.extend(remainder[: KINDERGARTEN_REGULAR_SAMPLE - len(selected)])

        return selected[:KINDERGARTEN_REGULAR_SAMPLE]

    @staticmethod
    def _short_vowel_of(word: SpellingWord) -> str:
        """Best-effort short-vowel classification used for sampling."""
        for name, value in word.features.items():
            if "short" in name.lower():
                letters = "".join(c for c in str(value).lower() if c.isalpha())
                if letters:
                    return letters[0]
        for char in word.word.lower():
            if char in _SHORT_VOWELS:
                return char
        return ""

    def audio_targets(self, grade: Grade) -> List[SpellingWord]:
        """Words that need narration - every word that has a sentence."""
        return [w for w in self.load(grade) if w.sentence]
