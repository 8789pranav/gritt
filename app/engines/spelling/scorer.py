"""
Scoring rules for the spelling assessment.

Two scoring modes, matching the legacy behaviour:

* **Regular words** are scored feature by feature - one point per phonics
  pattern the child reproduced correctly. An exact spelling short-circuits to
  full marks.
* **Sight and nonsense words** are all-or-nothing, worth a single point.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from app.domain.enums import Grade, ResponseStatus, TestType, WordType
from app.domain.models import ScoredItem, SpellingResponse, SpellingWord, TestScore
from app.engines.base import Scorer
from app.engines.spelling.phonics import (
    FeatureExpectation,
    PhonicsFeature,
    empty_error_counts,
    is_homophone,
    is_unrelated_attempt,
    parse_expectations,
    sounds_like,
)

#: Response times above this (seconds) are capped — the child likely left.
MAX_RESPONSE_SECONDS = 120.0

#: Percentage bands, highest first.
LEVEL_BANDS: Sequence[tuple[float, str]] = (
    (90.0, "Above Grade Level"),
    (70.0, "At Grade Level"),
    (0.0, "Below Grade Level"),
)

#: Status labels used by the legacy parent summary.
STATUS_BANDS: Sequence[tuple[float, str]] = (
    (90.0, "Above"),
    (70.0, "At"),
    (0.0, "Below"),
)


def _is_dropped_silent_e_vowel_change(
    target: str, attempt: str, long_vowel_pattern: str = ""
) -> bool:
    """Detect a dropped silent 'e' that changes the vowel sound.

    Returns True when the target has a VCe (vowel-consonant-e) long vowel
    pattern and the attempt drops the trailing 'e', shortening the vowel.
    This is a phonics error, not a spelling convention error.

    Uses the word's actual ``long_vowel`` feature pattern from the
    curriculum data when available (e.g. ``"i-e"``, ``"a-e"``, ``"o-e"``).
    Falls back to a heuristic when the pattern is unknown.

    Examples:
        home → hom      (o-e pattern, long o → short o)   True
        turnstile → turnstil (i-e pattern, long i → short i)  True
        amputate → amputat  (a-e pattern, long a → short a)   True
        smile → smil      (i-e pattern, long i → short i)     True

    But NOT:
        standstill → standstil (no VCe pattern, unstressed)  False
        candle → candel (not a dropped e, it's a swap)        False
        puzzle → puzle (the 'e' is part of '-le', not VCe)   False
    """
    target = target.strip().lower()
    attempt = attempt.strip().lower()
    if not target.endswith("e") or attempt.endswith("e"):
        return False
    if target == attempt:
        return False

    # If we have the long_vowel pattern from the word's features, use it.
    # A VCe pattern looks like "a-e", "i-e", "o-e", "u-e".
    if long_vowel_pattern:
        pattern = long_vowel_pattern.strip().lower()
        # Check for VCe split pattern: vowel + "-" + consonant(s) + "e"
        if "-" in pattern:
            vowel_part, _, ending = pattern.partition("-")
            vowel_part = vowel_part.strip()
            ending = ending.strip()
            # The ending must end with 'e' (the silent e)
            if ending.endswith("e"):
                # The attempt must drop the trailing 'e' (or the VCe ending)
                without_e = target[:-1]
                if attempt == without_e:
                    return True
                # Also handle cases where the attempt drops 'e' and changes
                # other letters but the vowel clearly changes.
                from difflib import SequenceMatcher
                ratio = SequenceMatcher(None, without_e, attempt).ratio()
                if ratio >= 0.8:
                    return True
        return False

    # Fallback heuristic (when no long_vowel pattern is available):
    # Check for a VCe pattern without the '-le' syllabic L exception.
    if len(target) < 3:
        return False
    stem = target[:-1]  # without the trailing 'e'
    if len(stem) < 2:
        return False
    # The character before the trailing 'e' must be a consonant.
    if stem[-1] not in "bcdfghjklmnpqrstvwxyz":
        return False
    # There must be a vowel in the stem.
    if not any(c in "aeiou" for c in stem):
        return False
    # Exception: '-le' words (candle, puzzle) where 'e' is not a silent-e
    # making the vowel long. In these words, the 'l' is syllabic.
    # But VCe words like "smile", "file", "while" also end in 'l' + 'e'.
    # Distinguish: in '-le' words, the vowel before the consonant cluster is
    # short (candle has short 'a'). In VCe words, the vowel is long (smile
    # has long 'i'). Without the feature data, we can't tell, so we only
    # block when the pattern is clearly NOT '-le' (i.e., the consonant
    # before 'e' is not 'l').
    if stem.endswith("l"):
        return False  # Could be '-le' syllabic L; let the AI/rules decide

    # The attempt must be close to the target without the trailing 'e'.
    without_e = target[:-1]
    if attempt == without_e:
        return True
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, without_e, attempt).ratio()
    return ratio >= 0.8


class SpellingScorer(Scorer[SpellingWord, SpellingResponse]):
    """Scores a spelling submission word by word."""

    def score(
        self,
        items: Sequence[SpellingWord],
        responses: Sequence[SpellingResponse],
        grade: Grade,
    ) -> TestScore:
        # Match on the word itself: the client submits words, not item ids.
        responses_by_word: Dict[str, SpellingResponse] = {
            response.word.strip().lower(): response for response in responses
        }

        # AI pre-pass: batch-classify wrong attempts as spelling convention
        # errors or phonics errors. This catches sound-equivalent swaps
        # (k/c, ow/ou, ur/er) that the rule-based sounds_like() misses.
        # Falls back to rules when OpenAI is not configured.
        ai_convention_words: set[str] = self._ai_classify_conventions(
            items, responses_by_word
        )

        scored: List[ScoredItem] = []
        total_points = 0.0
        total_max = 0.0
        fully_correct = 0
        answered = 0

        for item in items:
            response = responses_by_word.get(item.word.strip().lower())

            if response is None:
                scored.append(
                    ScoredItem(
                        item_id=item.item_id,
                        label=item.word,
                        is_correct=False,
                        points=0.0,
                        max_points=float(item.max_points),
                        status=ResponseStatus.NOT_ATTEMPTED,
                        detail={"type": item.word_type.value, "user_input": ""},
                    )
                )
                total_max += item.max_points
                continue

            answered += 1
            outcome = self.score_word(
                item, response.user_input, ai_convention_words
            )

            total_points += outcome.points
            total_max += outcome.max_points
            if outcome.is_correct:
                fully_correct += 1

            outcome.detail.update(
                {
                    "time": min(response.response_time_seconds, MAX_RESPONSE_SECONDS),
                    "hints_used": response.hints_used,
                }
            )
            scored.append(outcome)

        percentage = round(total_points / total_max * 100, 1) if total_max else 0.0

        return TestScore(
            test_type=TestType.SPELLING,
            grade=grade,
            total_items=len(items),
            answered_items=answered,
            correct_answers=fully_correct,
            points=round(total_points, 2),
            max_points=round(total_max, 2),
            percentage=percentage,
            level=Scorer.level_for(percentage, LEVEL_BANDS),
            scored_items=scored,
        )

    # -- AI convention pre-pass --------------------------------------------
    @staticmethod
    def _ai_classify_conventions(
        items: Sequence[SpellingWord],
        responses_by_word: Dict[str, SpellingResponse],
    ) -> set[str]:
        """Batch-classify wrong attempts as spelling convention errors.

        Collects all (target, attempt) pairs where the attempt is wrong
        but not unrelated, sends them to the AI classifier in one API call,
        and returns the set of target words that are convention errors.

        Falls back to an empty set (rule-based sounds_like handles it)
        when OpenAI is not configured or the call fails.
        """
        # Build a map of target → long_vowel pattern for the guardrail.
        long_vowel_patterns: Dict[str, str] = {}
        for item in items:
            target = item.word.strip().lower()
            for key, val in item.features.items():
                if key in ("long_vowel", "long_vowel_pattern", "long_vowel_patterns"):
                    long_vowel_patterns[target] = str(val).strip().lower()
                    break

        pairs: List[Dict[str, str]] = []
        for item in items:
            target = item.word.strip().lower()
            response = responses_by_word.get(target)
            if response is None:
                continue
            attempt = (response.user_input or "").strip().lower()
            if not attempt or attempt == target:
                continue
            if is_unrelated_attempt(target, attempt):
                continue
            if is_homophone(target, attempt):
                continue  # homophones are handled separately
            pairs.append({"target": target, "attempt": attempt})

        if not pairs:
            return set()

        try:
            from app.services.ai_provider import get_spelling_convention_classifier

            classifier = get_spelling_convention_classifier()
            if not classifier.is_configured:
                return set()

            convention_indices = classifier.classify_batch(pairs)
            result: set[str] = set()
            for idx in convention_indices:
                if 0 <= idx < len(pairs):
                    target = pairs[idx]["target"]
                    attempt = pairs[idx]["attempt"]
                    # Deterministic guardrail: a dropped silent 'e' that
                    # changes the vowel from long to short is ALWAYS a
                    # phonics error, never a convention error. The AI
                    # classifier is inconsistent on this distinction
                    # (it classifies turnstil as convention in some batches
                    # but not others), so we override it here.
                    if _is_dropped_silent_e_vowel_change(
                        target, attempt, long_vowel_patterns.get(target, "")
                    ):
                        continue
                    result.add(target)
            return result
        except Exception:
            return set()

    # -- single word --------------------------------------------------------
    def score_word(
        self,
        item: SpellingWord,
        user_input: str,
        ai_convention_words: set[str] | None = None,
    ) -> ScoredItem:
        """Score one spelling attempt.

        Parameters
        ----------
        item
            The word being tested.
        user_input
            What the child typed.
        ai_convention_words
            Set of target words that the AI classifier identified as
            spelling convention errors (phonetically correct, wrong
            spelling convention). When the target is in this set, the
            attempt is classified as a convention error regardless of
            the rule-based ``sounds_like()`` check.
        """
        attempt = (user_input or "").strip().lower()
        target = item.word.strip().lower()

        if item.word_type is not WordType.REGULAR:
            return self._score_whole_word(item, attempt, target, ai_convention_words)

        return self._score_features(item, attempt, target, ai_convention_words)

    def _score_whole_word(
        self,
        item: SpellingWord,
        attempt: str,
        target: str,
        ai_convention_words: set[str] | None = None,
    ) -> ScoredItem:
        """Sight and nonsense words are worth one point, all or nothing."""
        is_correct = attempt == target
        if is_correct:
            mistakes: Dict[str, str] = {}
        elif is_homophone(target, attempt):
            mistakes = {"homophone_error": f"Expected {item.word!r}, got {attempt!r} — a homophone"}
        elif (ai_convention_words and target in ai_convention_words) or sounds_like(target, attempt):
            mistakes = {"spelling_convention": f"Sounds correct, spelling convention error: {target!r} vs {attempt!r}"}
        else:
            mistakes = {"spelling": f"Expected {item.word!r}, got {attempt or '(blank)'!r}"}

        return ScoredItem(
            item_id=item.item_id,
            label=item.word,
            is_correct=is_correct,
            points=1.0 if is_correct else 0.0,
            max_points=1.0,
            status=ResponseStatus.ANSWERED,
            detail={
                "type": item.word_type.value,
                "user_input": attempt,
                "mistakes": mistakes,
            },
        )

    def _score_features(
        self,
        item: SpellingWord,
        attempt: str,
        target: str,
        ai_convention_words: set[str] | None = None,
    ) -> ScoredItem:
        """Regular words earn one point per correctly reproduced feature."""
        expectations: List[FeatureExpectation] = parse_expectations(item.features)
        max_points = float(len(expectations)) if expectations else 1.0

        # Exact spelling always earns full marks.
        if attempt == target:
            return ScoredItem(
                item_id=item.item_id,
                label=item.word,
                is_correct=True,
                points=max_points,
                max_points=max_points,
                status=ResponseStatus.ANSWERED,
                detail={
                    "type": item.word_type.value,
                    "user_input": attempt,
                    "mistakes": {},
                    "matched_features": [e.feature.value for e in expectations],
                },
            )

        if not expectations:
            return ScoredItem(
                item_id=item.item_id,
                label=item.word,
                is_correct=False,
                points=0.0,
                max_points=1.0,
                status=ResponseStatus.ANSWERED,
                detail={
                    "type": item.word_type.value,
                    "user_input": attempt,
                    "mistakes": {
                        "spelling": f"Expected {item.word!r}, got {attempt or '(blank)'!r}"
                    },
                },
            )

        # Completely unrelated words (e.g. "cup" -> "red") should not
        # generate phantom feature errors. They are one mistake: unrelated.
        if is_unrelated_attempt(target, attempt):
            return ScoredItem(
                item_id=item.item_id,
                label=item.word,
                is_correct=False,
                points=0.0,
                max_points=max_points,
                status=ResponseStatus.ANSWERED,
                detail={
                    "type": item.word_type.value,
                    "user_input": attempt,
                    "mistakes": {"unrelated_attempt": attempt},
                    "matched_features": [],
                },
            )

        # Homophone check (sun/son, there/their) — the child used a real
        # word that sounds identical but is spelled differently.  This is a
        # word-choice error, not a phonics error, so do not generate phantom
        # feature mistakes.
        if is_homophone(target, attempt):
            return ScoredItem(
                item_id=item.item_id,
                label=item.word,
                is_correct=False,
                points=max_points,
                max_points=max_points,
                status=ResponseStatus.ANSWERED,
                detail={
                    "type": item.word_type.value,
                    "user_input": attempt,
                    "mistakes": {"homophone_error": f"Expected {item.word!r}, got {attempt!r} — a homophone"},
                    "matched_features": [e.feature.value for e in expectations],
                },
            )

        # Phonetically-equivalent check (friend/frend, phone/fone).
        # The child knows all the sounds — only the spelling convention is wrong.
        # Give credit for every phonics feature; record one spelling-convention error.
        # Use AI classification when available (catches k/c, ow/ou, ur/er swaps
        # that the rule-based sounds_like() misses), falling back to rules.
        is_convention = (
            (ai_convention_words and target in ai_convention_words)
            or sounds_like(target, attempt)
        )
        if is_convention:
            return ScoredItem(
                item_id=item.item_id,
                label=item.word,
                is_correct=False,
                points=max_points,
                max_points=max_points,
                status=ResponseStatus.ANSWERED,
                detail={
                    "type": item.word_type.value,
                    "user_input": attempt,
                    "mistakes": {"spelling_convention": f"Sounds correct, spelling convention error: {target!r} vs {attempt!r}"},
                    "matched_features": [e.feature.value for e in expectations],
                },
            )

        points = 0.0
        mistakes: Dict[str, str] = {}
        matched: List[str] = []

        for expectation in expectations:
            if expectation.matches(attempt):
                points += 1
                matched.append(expectation.feature.value)
            else:
                mistakes[expectation.feature.value] = expectation.raw_value

        # Bug 4: is_correct must be exact-match, not points == max_points.
        # This ensures scorer and per_item_tags agree on correctness.
        is_correct = attempt == target

        return ScoredItem(
            item_id=item.item_id,
            label=item.word,
            is_correct=is_correct,
            points=points,
            max_points=max_points,
            status=ResponseStatus.ANSWERED,
            detail={
                "type": item.word_type.value,
                "user_input": attempt,
                "mistakes": mistakes,
                "matched_features": matched,
            },
        )

    # -- reporting helpers --------------------------------------------------
    @staticmethod
    def error_breakdown(score: TestScore) -> Dict[str, int]:
        """Tally feature errors across every regular word.

        #79: also counts homophone and spelling convention errors so they
        appear in key_error_patterns alongside phonics feature errors.
        """
        counts = empty_error_counts()
        # #79: non-phonics error categories that parents need to see.
        counts["Homophone error"] = 0
        counts["Spelling convention error"] = 0

        for item in score.scored_items:
            mistakes = item.detail.get("mistakes", {})
            # #79: count homophone and convention errors for ALL word types
            # (sight words can have homophones too).
            if "homophone_error" in mistakes:
                counts["Homophone error"] += 1
            if "spelling_convention" in mistakes:
                counts["Spelling convention error"] += 1

            if item.detail.get("type") != WordType.REGULAR.value:
                continue
            for feature_name in mistakes:
                try:
                    feature = PhonicsFeature(feature_name)
                except ValueError:
                    continue
                counts[feature.error_label] += 1

        return counts

    @staticmethod
    def status_for(percentage: float) -> str:
        return Scorer.level_for(percentage, STATUS_BANDS)
