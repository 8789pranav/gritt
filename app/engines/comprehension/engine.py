"""Reading comprehension (Story Explorer) assessment engine."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from app.domain.enums import Grade, TestType
from app.domain.models import (
    ComprehensionQuestion,
    ComprehensionResponse,
    ComprehensionStory,
    TagOutput,
    TestScore,
)
from app.engines.base import AssessmentEngine
from app.engines.comprehension.loader import ComprehensionStoryLoader
from app.engines.comprehension.scorer import LEVEL_BANDS, ComprehensionScorer
from app.engines.comprehension.signals import ComprehensionSignalDeriver

#: Guidance shown to parents, keyed by the lowest percentage that earns it.
#: S6: advice describes what the child DID, not what the child IS. No
#: labels, no grade levels, no scores.
_RECOMMENDATIONS: Sequence[Tuple[float, str]] = (
    (
        90.0,
        "Your child understood the stories well, including the parts that "
        "ask them to read between the lines. Try introducing slightly harder "
        "books with richer vocabulary to keep them growing.",
    ),
    (
        75.0,
        "Your child understood most of what they read. Keep offering a mix "
        "of story types and talking about what happened in each one.",
    ),
    (
        50.0,
        "Your child is building their understanding of stories. Re-reading "
        "a story together and talking about what happened will help them "
        "grow.",
    ),
    (
        0.0,
        "Your child is starting to engage with stories. Focus on listening "
        "to short stories together and talking about who, what and where "
        "before moving on to harder questions.",
    ),
)

_NEXT_STEPS: Sequence[Tuple[float, str]] = (
    (90.0, "Consider more advanced reading materials"),
    (75.0, "Continue with current grade level materials"),
    (0.0, "Practise with guided reading and comprehension activities"),
)


class ComprehensionEngine(
    AssessmentEngine[ComprehensionStory, ComprehensionResponse]
):
    """Assembles the comprehension loader, scorer and signal deriver."""

    level_bands = LEVEL_BANDS

    def __init__(self) -> None:
        super().__init__(
            loader=ComprehensionStoryLoader(),
            scorer=ComprehensionScorer(),
            deriver=ComprehensionSignalDeriver(),
        )

    @property
    def test_type(self) -> TestType:
        return TestType.COMPREHENSION

    def item_key(self, item: ComprehensionStory) -> str:
        return item.story_id

    # -- item access -------------------------------------------------------
    def answer_key(self, grade: Grade) -> Dict[str, ComprehensionQuestion]:
        return self.loader.answer_key(grade)

    def total_questions(self, grade: Grade) -> int:
        return self.loader.total_questions(grade)

    def public_stories(self, grade: Grade) -> List[Dict[str, object]]:
        """Stories shaped for the client, with correct answers withheld."""
        payload: List[Dict[str, object]] = []

        for story in self.get_items(grade):
            payload.append(
                {
                    "story_id": story.story_id,
                    "title": story.title,
                    "story_text": story.story_text,
                    "duration_estimate": story.duration_estimate,
                    "total_questions": story.total_questions,
                    "questions": [
                        {
                            "id": question.question_id,
                            "question": question.question,
                            "options": question.options,
                        }
                        for question in story.questions
                    ],
                }
            )

        return payload

    # -- reporting ---------------------------------------------------------
    def recommend(self, score: TestScore, tags: Sequence[TagOutput]) -> str:
        for minimum, text in _RECOMMENDATIONS:
            if score.percentage >= minimum:
                return text
        return _RECOMMENDATIONS[-1][1]

    def next_step(self, score: TestScore) -> str:
        for minimum, text in _NEXT_STEPS:
            if score.percentage >= minimum:
                return text
        return _NEXT_STEPS[-1][1]

    def status(self, score: TestScore) -> str:
        return self.scorer.status_for(score.percentage)

    def story_breakdown(self, score: TestScore) -> List[Dict[str, object]]:
        return self.scorer.story_breakdown(score)

    def narration_targets(self, grade: Grade) -> List[Tuple[str, str]]:
        """One narration clip per story."""
        return [
            (story.story_id, story.story_text)
            for story in self.loader.audio_targets(grade)
        ]
