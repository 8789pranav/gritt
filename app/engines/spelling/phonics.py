"""
Canonical phonics features for the spelling assessment.

The legacy word lists spell the same feature differently per grade -
``short_vowels`` in Kindergarten but ``short_vowel`` in Second, ``beginning``
in First but ``beginning_consonant`` in Third, and so on. Rather than pushing
those aliases into the scorer, every raw feature name is normalised here once
into a :class:`PhonicsFeature`.

Each feature also declares *how* it is matched against a child's spelling
attempt, which keeps the matching rules beside the definitions instead of
scattered through conditionals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class MatchStrategy(str, Enum):
    """How a feature's expected value is compared to the child's attempt."""

    #: The attempt must start with the expected letters.
    PREFIX = "prefix"
    #: The attempt must end with the expected letters.
    SUFFIX = "suffix"
    #: A vowel-consonant-e style split, e.g. ``"a-e"``: both parts must appear.
    SPLIT_PATTERN = "split_pattern"
    #: Any one of the comma-separated alternatives must appear anywhere.
    CONTAINS_ANY = "contains_any"


class PhonicsFeature(str, Enum):
    """The eight phonics features scored across all grades."""

    BEGINNING_CONSONANT = "beginning_consonant"
    ENDING_CONSONANT = "ending_consonant"
    SHORT_VOWEL = "short_vowel"
    CONSONANT_DIGRAPH = "consonant_digraph"
    CONSONANT_BLEND = "consonant_blend"
    LONG_VOWEL = "long_vowel"
    OTHER_VOWEL_PATTERN = "other_vowel_pattern"
    INFLECTED_ENDING = "inflected_ending"

    @property
    def display_name(self) -> str:
        return _DISPLAY_NAMES[self]

    @property
    def error_label(self) -> str:
        """Label used in the parent-facing error breakdown."""
        return f"{_DISPLAY_NAMES[self]} error"

    @property
    def strategy(self) -> MatchStrategy:
        return _STRATEGIES[self]


_DISPLAY_NAMES: Dict[PhonicsFeature, str] = {
    PhonicsFeature.BEGINNING_CONSONANT: "Beginning consonant",
    PhonicsFeature.ENDING_CONSONANT: "Ending consonant",
    PhonicsFeature.SHORT_VOWEL: "Short vowel",
    PhonicsFeature.CONSONANT_DIGRAPH: "Consonant digraph",
    PhonicsFeature.CONSONANT_BLEND: "Consonant blend",
    PhonicsFeature.LONG_VOWEL: "Long vowel",
    PhonicsFeature.OTHER_VOWEL_PATTERN: "Other vowel pattern",
    PhonicsFeature.INFLECTED_ENDING: "Inflected ending",
}

_STRATEGIES: Dict[PhonicsFeature, MatchStrategy] = {
    PhonicsFeature.BEGINNING_CONSONANT: MatchStrategy.PREFIX,
    PhonicsFeature.ENDING_CONSONANT: MatchStrategy.SUFFIX,
    PhonicsFeature.SHORT_VOWEL: MatchStrategy.CONTAINS_ANY,
    PhonicsFeature.CONSONANT_DIGRAPH: MatchStrategy.CONTAINS_ANY,
    PhonicsFeature.CONSONANT_BLEND: MatchStrategy.CONTAINS_ANY,
    PhonicsFeature.LONG_VOWEL: MatchStrategy.SPLIT_PATTERN,
    PhonicsFeature.OTHER_VOWEL_PATTERN: MatchStrategy.CONTAINS_ANY,
    PhonicsFeature.INFLECTED_ENDING: MatchStrategy.CONTAINS_ANY,
}

#: Every raw key seen in the legacy word lists, mapped to its canonical feature.
_ALIASES: Dict[str, PhonicsFeature] = {
    "beginning": PhonicsFeature.BEGINNING_CONSONANT,
    "beginning_consonant": PhonicsFeature.BEGINNING_CONSONANT,
    "final": PhonicsFeature.ENDING_CONSONANT,
    "final_consonant": PhonicsFeature.ENDING_CONSONANT,
    "ending_consonant": PhonicsFeature.ENDING_CONSONANT,
    "short_vowel": PhonicsFeature.SHORT_VOWEL,
    "short_vowels": PhonicsFeature.SHORT_VOWEL,
    "digraph": PhonicsFeature.CONSONANT_DIGRAPH,
    "consonant_digraph": PhonicsFeature.CONSONANT_DIGRAPH,
    "consonant_digraphs": PhonicsFeature.CONSONANT_DIGRAPH,
    "blend": PhonicsFeature.CONSONANT_BLEND,
    "consonant_blend": PhonicsFeature.CONSONANT_BLEND,
    "consonant_blends": PhonicsFeature.CONSONANT_BLEND,
    "long_vowel": PhonicsFeature.LONG_VOWEL,
    "long_vowel_pattern": PhonicsFeature.LONG_VOWEL,
    "long_vowel_patterns": PhonicsFeature.LONG_VOWEL,
    "other_vowel": PhonicsFeature.OTHER_VOWEL_PATTERN,
    "other_vowel_pattern": PhonicsFeature.OTHER_VOWEL_PATTERN,
    "other_vowel_patterns": PhonicsFeature.OTHER_VOWEL_PATTERN,
    "inflected": PhonicsFeature.INFLECTED_ENDING,
    "inflected_ending": PhonicsFeature.INFLECTED_ENDING,
    "inflected_endings": PhonicsFeature.INFLECTED_ENDING,
}

#: Values that mean "this feature does not apply to this word".
_EMPTY_VALUES = {"", "-", " ", "none", "n/a"}

#: Features that count towards the vowel accuracy signal.
VOWEL_FEATURES = frozenset(
    {
        PhonicsFeature.SHORT_VOWEL,
        PhonicsFeature.LONG_VOWEL,
        PhonicsFeature.OTHER_VOWEL_PATTERN,
    }
)


def normalise(raw_name: str) -> Optional[PhonicsFeature]:
    """Resolve a raw word-list key to a canonical feature, if it is one."""
    return _ALIASES.get(raw_name.strip().lower())


def is_scoreable(value: object) -> bool:
    """True when a feature value represents a real, scoreable pattern."""
    return str(value).strip().lower() not in _EMPTY_VALUES


@dataclass(frozen=True)
class FeatureExpectation:
    """One scoreable phonics feature attached to a specific word."""

    feature: PhonicsFeature
    raw_value: str

    @property
    def alternatives(self) -> List[str]:
        """The acceptable spellings, split on commas and lower-cased."""
        return [
            part.strip().lower()
            for part in self.raw_value.split(",")
            if part.strip()
        ]

    @property
    def letters(self) -> str:
        """The expected value reduced to letters only."""
        return "".join(char for char in self.raw_value.lower() if char.isalpha())

    def matches(self, attempt: str) -> bool:
        """Check a child's spelling attempt against this expectation."""
        attempt = attempt.strip().lower()
        if not attempt:
            return False

        strategy = self.feature.strategy

        if strategy is MatchStrategy.PREFIX:
            return bool(self.letters) and attempt.startswith(self.letters)

        if strategy is MatchStrategy.SUFFIX:
            letters = self.letters
            if not letters:
                return False
            if attempt.endswith(letters):
                return True
            # Silent-e: the ending consonant sits before a trailing 'e'
            # (e.g. "outline" — 'n' is before silent 'e').
            if attempt.endswith("e") and attempt[:-1].endswith(letters):
                return True
            return False

        if strategy is MatchStrategy.SPLIT_PATTERN and "-" in self.raw_value:
            vowel, _, ending = self.raw_value.partition("-")
            return vowel.strip().lower() in attempt and ending.strip().lower() in attempt

        return any(alt in attempt for alt in self.alternatives)


def parse_expectations(features: Dict[str, str]) -> List[FeatureExpectation]:
    """Convert a word's raw feature dict into canonical expectations.

    Unknown keys and placeholder values are dropped. When two aliases map to
    the same canonical feature, the first one wins.
    """
    expectations: List[FeatureExpectation] = []
    seen: set[PhonicsFeature] = set()

    for raw_name, raw_value in features.items():
        feature = normalise(raw_name)
        if feature is None or feature in seen or not is_scoreable(raw_value):
            continue
        # Vowel-start words have no beginning consonant to check.
        if feature is PhonicsFeature.BEGINNING_CONSONANT and "vowel start" in str(raw_value).lower():
            continue
        seen.add(feature)
        expectations.append(
            FeatureExpectation(feature=feature, raw_value=str(raw_value).strip())
        )

    return expectations


def empty_error_counts() -> Dict[str, int]:
    """A zeroed error tally covering every feature, in display order."""
    return {feature.error_label: 0 for feature in PhonicsFeature}


#: Known homophone groups — words that sound identical but are spelled
#: differently and have different meanings.
_HOMOPHONE_GROUPS: List[frozenset] = [
    frozenset({"there", "their", "they're"}),
    frozenset({"which", "witch"}),
    frozenset({"to", "too", "two"}),
    frozenset({"your", "you're"}),
    frozenset({"were", "where"}),
    frozenset({"hear", "here"}),
    frozenset({"write", "right"}),
    frozenset({"no", "know"}),
    frozenset({"by", "buy"}),
    frozenset({"for", "four"}),
    frozenset({"won", "one"}),
    frozenset({"ate", "eight"}),
    frozenset({"see", "sea"}),
    frozenset({"hi", "high"}),
]

_HOMOPHONE_MAP: Dict[str, frozenset] = {}
for _group in _HOMOPHONE_GROUPS:
    for _word in _group:
        _HOMOPHONE_MAP[_word] = _group


def is_homophone(target: str, attempt: str) -> bool:
    """True when *attempt* is a different real English word that sounds like *target*."""
    if not target or not attempt or target == attempt:
        return False
    group = _HOMOPHONE_MAP.get(target.strip().lower())
    if group is None:
        return False
    return attempt.strip().lower() in group


def _phonetic_key(word: str) -> str:
    """Convert a word to a simplified phonetic representation.

    Normalises spelling patterns that produce the same sound so that
    phonetically-equivalent misspellings collapse to the same key.
    """
    w = word.lower().strip()
    # ph -> f  (phone/fone, graph/graff)
    w = w.replace("ph", "f")
    # gh -> f  (laugh/lauf)
    w = w.replace("gh", "f")
    # ie -> e  (friend/frend — the i is silent before e)
    w = w.replace("ie", "e")
    # Reduce doubled consonants to a single letter (still/stil, puzzle/puzle)
    w = re.sub(r"(.)\1+", r"\1", w)
    # Remove silent 'e' at end (phone/fon, home/hom)
    if len(w) > 2 and w.endswith("e") and w[-2] not in "aeiou":
        w = w[:-1]
    # Normalise final 'le' / 'el' to 'l' (candle/candel)
    if w.endswith("el") and len(w) > 3 and w[-3] not in "aeiou":
        w = w[:-2] + "l"
    elif w.endswith("le") and len(w) > 3 and w[-3] not in "aeiou":
        w = w[:-2] + "l"
    return w


def sounds_like(target: str, attempt: str) -> bool:
    """Check if *attempt* sounds the same as *target* but is spelled differently.

    Returns ``True`` for phonetically-equivalent misspellings such as
    phone→fone, graph→graff, standstill→standstil, candle→candel.
    Returns ``False`` for exact matches, unrelated attempts, or genuine
    phonics errors (wrong vowel sound, wrong consonant, etc.).
    """
    if not target or not attempt or target == attempt:
        return False
    return _phonetic_key(target) == _phonetic_key(attempt)


def is_unrelated_attempt(target: str, attempt: str) -> bool:
    """Check if the child typed a completely different word.

    Returns ``True`` when the attempt is unrelated (e.g. "cup" -> "red"),
    and ``False`` when it is a genuine misspelling of the target.
    """
    if not attempt or not target:
        return True

    from difflib import SequenceMatcher

    ratio = SequenceMatcher(None, target, attempt).ratio()

    if ratio >= 0.5:
        return False

    shared = set(target) & set(attempt)
    shared_count = len(shared)

    if shared_count == 0:
        return True

    first_match = target[0] == attempt[0]
    last_match = target[-1] == attempt[-1]
    t_shared = [c for c in target if c in shared]
    a_shared = [c for c in attempt if c in shared]
    order_match = t_shared == a_shared

    lcp = 0
    for i in range(min(len(target), len(attempt))):
        if target[i] == attempt[i]:
            lcp += 1
        else:
            break

    lcs = 0
    for i in range(1, min(len(target), len(attempt)) + 1):
        if target[-i] == attempt[-i]:
            lcs += 1
        else:
            break

    if len(target) == 2:
        return not (shared_count >= 1 and (first_match or last_match) and order_match)

    if len(target) == 3:
        return not (shared_count >= 2 and (first_match or last_match) and order_match)

    if shared_count >= 2 and (first_match or last_match or lcp >= 1 or lcs >= 1):
        return False

    if ratio >= 0.4:
        return False

    return True
