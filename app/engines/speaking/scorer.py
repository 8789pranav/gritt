"""
Scoring rules for the speaking assessment.

Unlike the other tests, speaking scores are produced by an external analyzer
rather than computed from a correct answer. The scorer's job is therefore to
aggregate the per-sentence analyses that were attached to each response, and
to record unattempted sentences as zero rather than omitting them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.domain.enums import Grade, ResponseStatus, TestType
from app.domain.models import ScoredItem, SpeakingResponse, SpeakingSentence, TestScore
from app.engines.base import Scorer
from app.engines.speaking.analyzer import SpeechAnalysis

#: Percentage bands, highest first.
LEVEL_BANDS: Sequence[tuple[float, str]] = (
    (90.0, "Excellent Speaker"),
    (75.0, "Good Speaker"),
    (50.0, "Developing Speaker"),
    (0.0, "Needs Improvement"),
)

#: Maximum points available for one sentence.
MAX_SENTENCE_SCORE = 100.0


class SpeakingScorer(Scorer[SpeakingSentence, SpeakingResponse]):
    """Aggregates per-sentence speech analyses into a test score."""

    def __init__(self) -> None:
        # Populated by the engine before scoring; keyed by sentence id.
        self.analyses: Dict[str, SpeechAnalysis] = {}

    def with_analyses(
        self,
        analyses: Dict[str, SpeechAnalysis],
    ) -> "SpeakingScorer":
        """Attach the analyses to use for the next :meth:`score` call."""
        self.analyses = dict(analyses)
        return self

    def score(
        self,
        items: Sequence[SpeakingSentence],
        responses: Sequence[SpeakingResponse],
        grade: Grade,
    ) -> TestScore:
        responses_by_id: Dict[str, SpeakingResponse] = {
            response.sentence_id: response for response in responses
        }

        scored: List[ScoredItem] = []
        total_points = 0.0
        answered = 0
        strong = 0

        for sentence in items:
            response = responses_by_id.get(sentence.sentence_id)
            analysis = self.analyses.get(sentence.sentence_id)

            if response is None or analysis is None:
                scored.append(
                    ScoredItem(
                        item_id=sentence.sentence_id,
                        label=sentence.sentence,
                        is_correct=False,
                        points=0.0,
                        max_points=MAX_SENTENCE_SCORE,
                        status=ResponseStatus.NOT_ATTEMPTED,
                        detail={
                            "original_sentence": sentence.sentence,
                            "difficulty": sentence.difficulty.value,
                            "transcribed_text": "",
                            "recommendation": "Not attempted.",
                        },
                    )
                )
                continue

            answered += 1
            points = max(0.0, min(analysis.overall_score, MAX_SENTENCE_SCORE))
            total_points += points

            # "Correct" for a spoken response means a solid overall delivery.
            is_strong = points >= 75.0
            if is_strong:
                strong += 1

            scored.append(
                ScoredItem(
                    item_id=sentence.sentence_id,
                    label=sentence.sentence,
                    is_correct=is_strong,
                    points=points,
                    max_points=MAX_SENTENCE_SCORE,
                    status=ResponseStatus.ANSWERED,
                    detail={
                        "original_sentence": sentence.sentence,
                        "difficulty": sentence.difficulty.value,
                        "transcribed_text": getattr(response, "transcribed_text", ""),
                        "recommendation": analysis.recommendation,
                        "analysis": analysis.to_dict(),
                    },
                )
            )

        total = len(items)
        max_points = total * MAX_SENTENCE_SCORE
        percentage = round(total_points / max_points * 100, 1) if max_points else 0.0

        return TestScore(
            test_type=TestType.SPEAKING,
            grade=grade,
            total_items=total,
            answered_items=answered,
            correct_answers=strong,
            points=round(total_points, 1),
            max_points=max_points,
            percentage=percentage,
            level=Scorer.level_for(percentage, LEVEL_BANDS),
            scored_items=scored,
        )

    @staticmethod
    def average_score(score: TestScore) -> float:
        """Mean points per sentence across the whole test."""
        if not score.total_items:
            return 0.0
        return round(score.points / score.total_items, 1)
