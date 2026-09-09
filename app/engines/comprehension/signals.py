"""
Signal derivation for the reading comprehension assessment.

Accuracy is broken down by question type (literal, inferential, vocabulary)
because the gap between literal and inferential performance is the key
diagnostic signal for this test.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.domain.enums import QuestionType, TestType
from app.domain.models import (
    ComprehensionResponse,
    ComprehensionStory,
    PerItemTags,
    TestScore,
)
from app.engines.base import SignalDeriver


class ComprehensionSignalDeriver(
    SignalDeriver[ComprehensionStory, ComprehensionResponse]
):
    """Derives comprehension tagging signals."""

    def __init__(self) -> None:
        super().__init__(TestType.COMPREHENSION)

    def derive(
        self,
        items: Sequence[ComprehensionStory],
        responses: Sequence[ComprehensionResponse],
        score: TestScore,
    ) -> Dict[str, Any]:
        attempted: Dict[QuestionType, int] = {qt: 0 for qt in QuestionType}
        correct: Dict[QuestionType, int] = {qt: 0 for qt in QuestionType}

        for item in score.scored_items:
            # S2: skip unanswered questions entirely. They carry no signal.
            if not item.detail.get("answered", True):
                continue
            try:
                question_type = QuestionType(item.detail.get("question_type", "literal"))
            except ValueError:
                question_type = QuestionType.LITERAL

            attempted[question_type] += 1
            if item.is_correct:
                correct[question_type] += 1

        literal_accuracy = self.ratio(
            correct[QuestionType.LITERAL], attempted[QuestionType.LITERAL]
        )
        inferential_accuracy = self.ratio(
            correct[QuestionType.INFERENTIAL], attempted[QuestionType.INFERENTIAL]
        )
        vocabulary_accuracy = self.ratio(
            correct[QuestionType.VOCABULARY], attempted[QuestionType.VOCABULARY]
        )
        # S2: overall_accuracy uses only answered questions.
        overall_accuracy = self.ratio(score.correct_answers, score.answered_items)

        # C11: one story near zero while another scored well, same sitting.
        story_scores = {}
        for item in score.scored_items:
            # S2: skip unanswered questions.
            if not item.detail.get("answered", True):
                continue
            story_id = str(item.detail.get("story_id", ""))
            bucket = story_scores.setdefault(story_id, [0, 0])
            bucket[1] += 1
            if item.is_correct:
                bucket[0] += 1
        per_story = [
            round(right / total, 4) for right, total in story_scores.values() if total
        ]
        story_score_gap = (
            round(max(per_story) - min(per_story), 4) if len(per_story) > 1 else 0.0
        )
        story_low = round(min(per_story), 4) if per_story else 0.0

        # Only meaningful when both question types were actually asked.
        gap = 0.0
        if attempted[QuestionType.LITERAL] and attempted[QuestionType.INFERENTIAL]:
            gap = round(literal_accuracy - inferential_accuracy, 4)

        # D4: Detect repeating answer patterns (data capture for later analysis).
        # A child who always picks the same option position (e.g. alternating
        # B, C, B, C) can score high without comprehension. This signal records
        # the most common selected index and its frequency.
        selected_indices = [
            r.selected_index for r in responses
            if r is not None and r.selected_index is not None
        ]
        repeating_pattern_detected = False
        most_common_index = -1
        most_common_count = 0
        if selected_indices:
            from collections import Counter
            index_counts = Counter(selected_indices)
            most_common_index, most_common_count = index_counts.most_common(1)[0]
            # Flag if any single position is used more than 60% of the time.
            if most_common_count / len(selected_indices) > 0.6:
                repeating_pattern_detected = True

        return {
            "literal_accuracy": literal_accuracy,
            "inferential_accuracy": inferential_accuracy,
            "vocabulary_accuracy": vocabulary_accuracy,
            "overall_accuracy": overall_accuracy,
            "literal_inferential_gap": gap,
            "story_score_gap": story_score_gap,
            "story_low_score": story_low,
            "stories_attempted": len(per_story),
            # Contextual counts, not referenced by any trigger.
            "literal_attempted": attempted[QuestionType.LITERAL],
            "inferential_attempted": attempted[QuestionType.INFERENTIAL],
            "vocabulary_attempted": attempted[QuestionType.VOCABULARY],
            # S2: total_questions counts only answered questions.
            "total_questions": score.answered_items,
            "questions_answered": score.answered_items,
            # D4: Data capture for pattern detection (not used at launch).
            "repeating_pattern_detected": repeating_pattern_detected,
            "most_common_selected_index": most_common_index,
            "most_common_selected_count": most_common_count,
        }

    def per_item_tags(
        self,
        items: Sequence[ComprehensionStory],
        responses: Sequence[ComprehensionResponse],
        score: Optional[TestScore] = None,
    ) -> List[PerItemTags]:
        """Tag each question with its type and outcome."""
        responses_by_question = {r.question_id: r for r in responses}
        results: List[PerItemTags] = []

        for story in items:
            for question in story.questions:
                response = responses_by_question.get(question.question_id)

                if response is None:
                    results.append(
                        PerItemTags(
                            item_id=question.question_id,
                            answered=False,
                            is_correct=None,
                            tags=[question.question_type.value],
                        )
                    )
                    continue

                is_correct = question.is_correct(response.selected_index)
                suffix = "correct" if is_correct else "error"
                results.append(
                    PerItemTags(
                        item_id=question.question_id,
                        answered=True,
                        is_correct=is_correct,
                        tags=[
                            question.question_type.value,
                            f"{question.question_type.value}_{suffix}",
                        ],
                    )
                )

        return results
