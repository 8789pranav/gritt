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
    is_unrelated_attempt,
    parse_expectations,
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
            outcome = self.score_word(item, response.user_input)

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

    # -- single word --------------------------------------------------------
    def score_word(self, item: SpellingWord, user_input: str) -> ScoredItem:
        """Score one spelling attempt."""
        attempt = (user_input or "").strip().lower()
        target = item.word.strip().lower()

        if item.word_type is not WordType.REGULAR:
            return self._score_whole_word(item, attempt, target)

        return self._score_features(item, attempt, target)

    def _score_whole_word(
        self,
        item: SpellingWord,
        attempt: str,
        target: str,
    ) -> ScoredItem:
        """Sight and nonsense words are worth one point, all or nothing."""
        is_correct = attempt == target
        mistakes: Dict[str, str] = (
            {}
            if is_correct
            else {"spelling": f"Expected {item.word!r}, got {attempt or '(blank)'!r}"}
        )

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

        points = 0.0
        mistakes: Dict[str, str] = {}
        matched: List[str] = []

        for expectation in expectations:
            if expectation.matches(attempt):
                points += 1
                matched.append(expectation.feature.value)
            else:
                mistakes[expectation.feature.value] = expectation.raw_value

        return ScoredItem(
            item_id=item.item_id,
            label=item.word,
            is_correct=points == max_points,
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
        """Tally feature errors across every regular word."""
        counts = empty_error_counts()

        for item in score.scored_items:
            if item.detail.get("type") != WordType.REGULAR.value:
                continue
            for feature_name in item.detail.get("mistakes", {}):
                try:
                    feature = PhonicsFeature(feature_name)
                except ValueError:
                    continue
                counts[feature.error_label] += 1

        return counts

    @staticmethod
    def status_for(percentage: float) -> str:
        return Scorer.level_for(percentage, STATUS_BANDS)
