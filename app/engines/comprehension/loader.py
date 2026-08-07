"""Question-bank loader for the reading comprehension assessment."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from app.core.exceptions import DataFileError
from app.domain.enums import Grade, QuestionType, TestType
from app.domain.models import ComprehensionQuestion, ComprehensionStory
from app.engines.base import QuestionLoader


class ComprehensionStoryLoader(QuestionLoader[ComprehensionStory]):
    """Reads ``data/questions/comprehension/<grade>.json`` into stories."""

    items_key = "stories"

    def __init__(self) -> None:
        super().__init__(TestType.COMPREHENSION)

    def parse_item(self, raw: Mapping[str, Any], grade: Grade) -> ComprehensionStory:
        story_id = raw.get("story_id")
        if not story_id:
            raise DataFileError(
                f"comprehension/{grade.file_stem}.json: story missing 'story_id'"
            )

        questions = [
            self._parse_question(question, story_id)
            for question in raw.get("questions", [])
        ]
        if not questions:
            raise DataFileError(f"{story_id}: story has no questions")

        return ComprehensionStory(
            item_id=story_id,
            grade=grade,
            story_id=story_id,
            title=raw.get("title", ""),
            story_text=raw.get("story_text", ""),
            duration_estimate=raw.get("duration_estimate", "60 seconds"),
            questions=questions,
        )

    @staticmethod
    def _parse_question(
        raw: Mapping[str, Any],
        story_id: str,
    ) -> ComprehensionQuestion:
        question_id = raw.get("question_id")
        if not question_id:
            raise DataFileError(f"{story_id}: question missing 'question_id'")

        options = list(raw.get("options", []))
        if len(options) < 2:
            raise DataFileError(f"{question_id}: needs at least two options")

        correct_index = raw.get("correct_index")
        if not isinstance(correct_index, int) or not 0 <= correct_index < len(options):
            raise DataFileError(
                f"{question_id}: correct_index {correct_index!r} is out of range"
            )

        try:
            question_type = QuestionType(raw.get("question_type", "literal"))
        except ValueError:
            # An unrecognised type should not break the whole bank; default to
            # literal and let the data verifier surface it.
            question_type = QuestionType.LITERAL

        return ComprehensionQuestion(
            question_id=question_id,
            question=raw.get("question", ""),
            options=options,
            correct_index=correct_index,
            question_type=question_type,
        )

    # -- convenience --------------------------------------------------------
    def answer_key(self, grade: Grade) -> Dict[str, ComprehensionQuestion]:
        """Map every question id in a grade to its question."""
        key: Dict[str, ComprehensionQuestion] = {}
        for story in self.load(grade):
            for question in story.questions:
                key[question.question_id] = question
        return key

    def story_for_question(self, grade: Grade) -> Dict[str, ComprehensionStory]:
        """Map every question id to the story it belongs to."""
        mapping: Dict[str, ComprehensionStory] = {}
        for story in self.load(grade):
            for question in story.questions:
                mapping[question.question_id] = story
        return mapping

    def total_questions(self, grade: Grade) -> int:
        return sum(story.total_questions for story in self.load(grade))

    def audio_targets(self, grade: Grade) -> List[ComprehensionStory]:
        return [story for story in self.load(grade) if story.story_text]
