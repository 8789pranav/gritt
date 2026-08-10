"""
Signal derivation for the spelling assessment.

Produces the accuracy ratios and error counts that the rules in
``data/tags/spelling_tags.json`` are evaluated against.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from app.domain.enums import TestType, WordType
from app.domain.models import PerItemTags, SpellingResponse, SpellingWord, TestScore
from app.engines.base import SignalDeriver
from app.engines.spelling.phonics import (
    VOWEL_FEATURES,
    PhonicsFeature,
    parse_expectations,
)

#: A word answered faster than this (seconds) is treated as rushed.
FAST_RESPONSE_SECONDS = 3.0


class _FeatureTally:
    """Running attempted/correct counts for one phonics feature."""

    __slots__ = ("attempted", "correct")

    def __init__(self) -> None:
        self.attempted = 0
        self.correct = 0

    @property
    def errors(self) -> int:
        return self.attempted - self.correct

    def accuracy(self) -> float:
        if not self.attempted:
            return 0.0
        return round(self.correct / self.attempted, 4)


class SpellingSignalDeriver(SignalDeriver[SpellingWord, SpellingResponse]):
    """Derives spelling tagging signals."""

    def __init__(self) -> None:
        super().__init__(TestType.SPELLING)

    def derive(
        self,
        items: Sequence[SpellingWord],
        responses: Sequence[SpellingResponse],
        score: TestScore,
    ) -> Dict[str, Any]:
        tallies: Dict[PhonicsFeature, _FeatureTally] = {
            feature: _FeatureTally() for feature in PhonicsFeature
        }

        items_by_id = {item.item_id: item for item in items}
        responses_by_word = {r.word.strip().lower(): r for r in responses}

        regular_attempted = regular_correct = 0
        sight_attempted = sight_correct = 0
        hard_attempted = hard_total = 0
        fast_slips = 0
        improved_with_audio = False

        for scored in score.scored_items:
            item = items_by_id.get(scored.item_id)
            if item is None:
                continue

            response = responses_by_word.get(item.word.strip().lower())
            attempted = response is not None
            mistakes = scored.detail.get("mistakes", {})

            # Per-word-type accuracy.
            if item.word_type is WordType.REGULAR:
                if attempted:
                    regular_attempted += 1
                    if scored.is_correct:
                        regular_correct += 1
            elif item.word_type is WordType.SIGHT:
                if attempted:
                    sight_attempted += 1
                    if scored.is_correct:
                        sight_correct += 1

            # Feature-level accuracy, regular words only.
            if item.word_type is WordType.REGULAR and attempted:
                for expectation in parse_expectations(item.features):
                    tally = tallies[expectation.feature]
                    tally.attempted += 1
                    if expectation.feature.value not in mistakes:
                        tally.correct += 1

            # Persistence: did the child attempt the harder multi-feature words?
            if item.max_points >= 3:
                hard_total += 1
                if attempted and (response.user_input or "").strip():
                    hard_attempted += 1

            # Rushed slips: fast, wrong, and on a word with few features.
            if attempted and not scored.is_correct:
                if 0 < response.response_time_seconds < FAST_RESPONSE_SECONDS:
                    fast_slips += 1

            if attempted and response.hints_used > 0 and scored.is_correct:
                improved_with_audio = True

        vowel_attempted = sum(tallies[f].attempted for f in VOWEL_FEATURES)
        vowel_correct = sum(tallies[f].correct for f in VOWEL_FEATURES)
        vowel_errors = sum(tallies[f].errors for f in VOWEL_FEATURES)

        digraph = tallies[PhonicsFeature.CONSONANT_DIGRAPH]
        blend = tallies[PhonicsFeature.CONSONANT_BLEND]

        signals: Dict[str, Any] = {
            "beginning_accuracy": tallies[PhonicsFeature.BEGINNING_CONSONANT].accuracy(),
            "final_accuracy": tallies[PhonicsFeature.ENDING_CONSONANT].accuracy(),
            "vowel_accuracy": self.ratio(vowel_correct, vowel_attempted),
            "vowel_error_count": vowel_errors,
            "digraph_accuracy": digraph.accuracy(),
            "blend_accuracy": blend.accuracy(),
            "digraph_error_count": digraph.errors + blend.errors,
            "sight_word_accuracy": self.ratio(sight_correct, sight_attempted),
            "regular_word_accuracy": self.ratio(regular_correct, regular_attempted),
            "improved_with_audio": improved_with_audio,
            "hard_words_attempted_ratio": self.ratio(hard_attempted, hard_total),
            "fast_slips": fast_slips,
        }

        # Contextual values for reporting; no trigger references these.
        signals.update(
            {
                "overall_accuracy": self.ratio(score.points, score.max_points),
                "words_tested": score.total_items,
                "words_answered": score.answered_items,
            }
        )
        signals.update(
            {
                f"{feature.value}_accuracy": tally.accuracy()
                for feature, tally in tallies.items()
            }
        )

        return signals

    def per_item_tags(
        self,
        items: Sequence[SpellingWord],
        responses: Sequence[SpellingResponse],
    ) -> List[PerItemTags]:
        """Attribute per-feature tags (both correct and error) for each word.

        For regular (phonetic) words, every phonics feature is tagged as
        either ``{feature}_correct`` or ``{feature}_error``.

        For sight words, ``sight_word_correct`` or ``sight_word_error``.

        Additionally, ``rushed_attempt`` is added when a wrong answer is
        given in under ``FAST_RESPONSE_SECONDS``.
        """
        responses_by_word = {r.word.strip().lower(): r for r in responses}
        results: List[PerItemTags] = []

        for item in items:
            response = responses_by_word.get(item.word.strip().lower())
            if response is None:
                results.append(
                    PerItemTags(item_id=item.item_id, answered=False, is_correct=None)
                )
                continue

            attempt = (response.user_input or "").strip().lower()
            target = item.word.strip().lower()
            tags: List[str] = []

            if item.word_type is WordType.REGULAR:
                for expectation in parse_expectations(item.features):
                    if expectation.matches(attempt):
                        tags.append(f"{expectation.feature.value}_correct")
                    else:
                        tags.append(f"{expectation.feature.value}_error")
                is_correct = attempt == target
            else:
                is_correct = attempt == target
                if is_correct:
                    tags.append(f"{item.word_type.value}_word_correct")
                else:
                    tags.append(f"{item.word_type.value}_word_error")

            if not is_correct and 0 < response.response_time_seconds < FAST_RESPONSE_SECONDS:
                tags.append("rushed_attempt")

            results.append(
                PerItemTags(
                    item_id=item.item_id,
                    answered=True,
                    is_correct=is_correct,
                    tags=list(dict.fromkeys(tags)),
                )
            )

        return results
