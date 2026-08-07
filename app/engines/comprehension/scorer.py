"""Scoring rules for the reading comprehension assessment."""

from __future__ import annotations

from typing import Dict, List, Sequence

from app.domain.enums import Grade, ResponseStatus, TestType
from app.domain.models import (
    ComprehensionResponse,
    ComprehensionStory,
    ScoredItem,
    TestScore,
)
from app.engines.base import Scorer

#: Percentage bands, highest first.
LEVEL_BANDS: Sequence[tuple[float, str]] = (
    (90.0, "Excellent Reader"),
    (75.0, "Good Reader"),
    (50.0, "Developing Reader"),
    (0.0, "Needs Practice"),
)

#: Placement status shown alongside the level.
STATUS_BANDS: Sequence[tuple[float, str]] = (
    (90.0, "Above"),
    (75.0, "At"),
    (0.0, "Below"),
)


class ComprehensionScorer(Scorer[ComprehensionStory, ComprehensionResponse]):
    """Awards one point per correctly answered question.

    Scoring is per *question*, not per story, so the denominator is the total
    question count across every story in the grade.
    """

    def score(
        self,
        items: Sequence[ComprehensionStory],
        responses: Sequence[ComprehensionResponse],
        grade: Grade,
    ) -> TestScore:
        responses_by_question: Dict[str, ComprehensionResponse] = {
            response.question_id: response for response in responses
        }

        scored: List[ScoredItem] = []
        correct = 0
        answered = 0
        total = 0

        for story in items:
            for question in story.questions:
                total += 1
                response = responses_by_question.get(question.question_id)

                if response is None:
                    scored.append(
                        ScoredItem(
                            item_id=question.question_id,
                            label=question.question,
                            is_correct=False,
                            points=0.0,
                            max_points=1.0,
                            status=ResponseStatus.NOT_ATTEMPTED,
                            detail={
                                "story_id": story.story_id,
                                "story_title": story.title,
                                "question_type": question.question_type.value,
                                "correct_index": question.correct_index,
                                "correct_answer": question.answer_text(
                                    question.correct_index
                                ),
                                "selected_index": None,
                                "selected_answer": None,
                            },
                        )
                    )
                    continue

                answered += 1
                is_correct = question.is_correct(response.selected_index)
                if is_correct:
                    correct += 1

                scored.append(
                    ScoredItem(
                        item_id=question.question_id,
                        label=question.question,
                        is_correct=is_correct,
                        points=1.0 if is_correct else 0.0,
                        max_points=1.0,
                        status=ResponseStatus.ANSWERED,
                        detail={
                            "story_id": story.story_id,
                            "story_title": story.title,
                            "question_type": question.question_type.value,
                            "selected_index": response.selected_index,
                            "selected_answer": question.answer_text(
                                response.selected_index
                            ),
                            "correct_index": question.correct_index,
                            "correct_answer": question.answer_text(
                                question.correct_index
                            ),
                        },
                    )
                )

        percentage = round(correct / total * 100, 1) if total else 0.0

        return TestScore(
            test_type=TestType.COMPREHENSION,
            grade=grade,
            total_items=total,
            answered_items=answered,
            correct_answers=correct,
            points=float(correct),
            max_points=float(total),
            percentage=percentage,
            level=Scorer.level_for(percentage, LEVEL_BANDS),
            scored_items=scored,
        )

    # -- reporting helpers --------------------------------------------------
    @staticmethod
    def story_breakdown(score: TestScore) -> List[Dict[str, object]]:
        """Per-story correct/total counts, preserving story order."""
        buckets: Dict[str, Dict[str, object]] = {}

        for item in score.scored_items:
            story_id = str(item.detail.get("story_id", ""))
            bucket = buckets.setdefault(
                story_id,
                {
                    "story_id": story_id,
                    "story_title": item.detail.get("story_title", ""),
                    "correct": 0,
                    "total": 0,
                    "questions": [],
                },
            )
            bucket["total"] = int(bucket["total"]) + 1
            if item.is_correct:
                bucket["correct"] = int(bucket["correct"]) + 1

            questions = bucket["questions"]
            assert isinstance(questions, list)
            questions.append(
                {
                    "question_id": item.item_id,
                    "question": item.label,
                    "selected_index": item.detail.get("selected_index"),
                    "selected_answer": item.detail.get("selected_answer"),
                    "correct_index": item.detail.get("correct_index"),
                    "correct_answer": item.detail.get("correct_answer"),
                    "is_correct": item.is_correct,
                }
            )

        for bucket in buckets.values():
            total = int(bucket["total"])
            correct = int(bucket["correct"])
            bucket["percentage"] = round(correct / total * 100, 1) if total else 0.0

        return list(buckets.values())

    @staticmethod
    def status_for(percentage: float) -> str:
        return Scorer.level_for(percentage, STATUS_BANDS)
