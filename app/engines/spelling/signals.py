"""
Signal derivation for the spelling assessment.

Produces the accuracy ratios and error counts that the rules in
``data/tags/spelling_tags.json`` are evaluated against.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.domain.enums import TestType, WordType
from app.domain.models import PerItemTags, SpellingResponse, SpellingWord, TestScore
from app.engines.base import SignalDeriver
from app.engines.spelling.phonics import (
    VOWEL_FEATURES,
    PhonicsFeature,
    is_homophone,
    is_unrelated_attempt,
    parse_expectations,
    sounds_like,
)

#: A word answered faster than this (seconds) is treated as rushed when the
#: child's median response time is unavailable.
FAST_RESPONSE_SECONDS = 3.0

#: Mistake keys that classify *why* an attempt is wrong. When one of these
#: fires, the attempt is explained - it is not a rushed slip (#61).
CLASSIFICATION_MISTAKES = frozenset(
    {"unrelated_attempt", "spelling_convention", "homophone_error"}
)

#: Item-level tags that classify an attempt, suppressing rushed_attempt (#61).
CLASSIFICATION_TAGS = frozenset(
    {
        "unrelated_attempt",
        "unrelated_attempt_sightword",
        "homophone_error",
        "spelling_convention_error",
    }
)


def rushed_threshold(responses) -> float:
    """Half the child's median response time (#61).

    A fixed 3-second cut-off mislabels a naturally fast child and misses a
    slow one. Falls back to :data:`FAST_RESPONSE_SECONDS` when there are too
    few timed responses to take a median.
    """
    from statistics import median

    times = [
        r.response_time_seconds
        for r in responses
        if r.response_time_seconds and r.response_time_seconds > 0
    ]
    if not times:
        return 0.0
    return median(times) / 2.0


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
        convention_errors = 0
        improved_with_audio = False
        fast_cutoff = rushed_threshold(responses)

        for scored in score.scored_items:
            item = items_by_id.get(scored.item_id)
            if item is None:
                continue

            response = responses_by_word.get(item.word.strip().lower())
            attempted = response is not None
            mistakes = scored.detail.get("mistakes", {})

            # Per-word-type accuracy. The denominator is every word SHOWN,
            # so a sound-alike or a blank stays in the pool and counts as
            # not-yet-correct (Q3). parent_summary mirrors this exactly.
            if item.word_type is WordType.REGULAR:
                regular_attempted += 1
                if scored.is_correct:
                    regular_correct += 1
            elif item.word_type is WordType.SIGHT:
                sight_attempted += 1
                if scored.is_correct:
                    sight_correct += 1

            # Feature-level accuracy, regular words only.
            # Skip unrelated attempts so they don't create phantom feature errors.
            if (
                item.word_type is WordType.REGULAR
                and attempted
                and "unrelated_attempt" not in mistakes
            ):
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

            # #75: convention errors are the signal that a child hears the
            # sounds but does not know the spelling rule.
            if "spelling_convention" in mistakes:
                convention_errors += 1

            # Rushed slips: wrong and answered in under half the median time.
            # #61: never on an item a classification tag already explains.
            if attempted and not scored.is_correct:
                if (
                    0 < response.response_time_seconds < fast_cutoff
                    and not (CLASSIFICATION_MISTAKES & set(mistakes))
                ):
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
            "digraph_error_count": digraph.errors,
            "blend_error_count": blend.errors,
            "digraph_words_count": digraph.attempted,
            "blend_words_count": blend.attempted,
            "vowel_words_count": vowel_attempted,
            "sight_words_count": sight_attempted,
            "convention_error_count": convention_errors,
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
        # #78: per-feature attempted count, so strengths() can require
        # a minimum number of words before calling a feature "mastered".
        signals.update(
            {
                f"{feature.value}_attempted": tally.attempted
                for feature, tally in tallies.items()
            }
        )

        return signals

    def per_item_tags(
        self,
        items: Sequence[SpellingWord],
        responses: Sequence[SpellingResponse],
        score: Optional[TestScore] = None,
    ) -> List[PerItemTags]:
        """Attribute per-feature tags (both correct and error) for each word.

        Uses the scorer's :class:`ScoredItem` results as the single source of
        truth for correctness and mistakes, ensuring consistency between
        ``teacher_admin_detail`` and ``per_word_tags`` (bug 4).
        """
        responses_by_word = {r.word.strip().lower(): r for r in responses}
        scored_by_id = {s.item_id: s for s in (score.scored_items if score else [])}
        fast_cutoff = rushed_threshold(responses)
        results: List[PerItemTags] = []

        for item in items:
            response = responses_by_word.get(item.word.strip().lower())
            # A word the child never saw, and a word submitted blank, are both
            # unanswered: answered=False and no tags at all.
            if response is None or not (response.user_input or "").strip():
                results.append(
                    PerItemTags(item_id=item.item_id, answered=False, is_correct=None)
                )
                continue

            attempt = (response.user_input or "").strip().lower()
            target = item.word.strip().lower()
            scored = scored_by_id.get(item.item_id)
            tags: List[str] = []

            # Use scorer's result as the single source of truth (bug 4).
            if scored is not None:
                is_correct = scored.is_correct
                mistakes = scored.detail.get("mistakes", {})
                matched = scored.detail.get("matched_features", [])
            else:
                is_correct = attempt == target
                mistakes = {}
                matched = []

            if is_correct:
                if item.word_type is WordType.REGULAR:
                    for expectation in parse_expectations(item.features):
                        if expectation.matches(attempt):
                            tags.append(f"{expectation.feature.value}_correct")
                        else:
                            tags.append(f"{expectation.feature.value}_error")
                else:
                    tags.append(f"{item.word_type.value}_word_correct")
            elif "unrelated_attempt" in mistakes:
                if item.word_type is WordType.REGULAR:
                    tags.append("unrelated_attempt")
                else:
                    tags.append("unrelated_attempt_sightword")
            elif "spelling_convention" in mistakes:
                # Phonetically correct — child knows the sounds, just not the spelling rule.
                for expectation in parse_expectations(item.features):
                    tags.append(f"{expectation.feature.value}_correct")
                tags.append("spelling_convention_error")
            elif "homophone_error" in mistakes:
                tags.append("homophone_error")
            elif item.word_type is WordType.REGULAR:
                for expectation in parse_expectations(item.features):
                    if expectation.matches(attempt):
                        tags.append(f"{expectation.feature.value}_correct")
                    else:
                        tags.append(f"{expectation.feature.value}_error")
                # Bug 5: every wrong word needs at least 1 error tag.
                if not any(t.endswith("_error") for t in tags):
                    tags.append("spelling_error")
            else:
                tags.append(f"{item.word_type.value}_word_error")

            # #61: rushed only when nothing better explains the attempt, and
            # only against half the child's own median time.
            if not is_correct and 0 < response.response_time_seconds < fast_cutoff:
                if not CLASSIFICATION_TAGS.intersection(tags):
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

