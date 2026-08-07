"""Speaking (Voice Challenge) assessment engine."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.core.config import get_settings
from app.domain.enums import Grade, TestType
from app.domain.models import (
    AssessmentResult,
    SpeakingResponse,
    SpeakingSentence,
    TagOutput,
    TestScore,
)
from app.engines.base import AssessmentEngine, Scorer
from app.engines.speaking.analyzer import SpeechAnalysis
from app.engines.speaking.loader import SpeakingSentenceLoader
from app.engines.speaking.scorer import LEVEL_BANDS, SpeakingScorer
from app.engines.speaking.signals import SpeakingSignalDeriver

_RECOMMENDATIONS: Sequence[Tuple[float, str]] = (
    (90.0, "Excellent speaking! Encourage reading aloud with expression and pace."),
    (75.0, "Strong delivery. Practise longer sentences to build stamina."),
    (50.0, "Developing well. Read aloud together daily, focusing on clarity."),
    (0.0, "Focus on saying each word slowly and clearly, one sentence at a time."),
)


class SpeakingEngine(AssessmentEngine[SpeakingSentence, SpeakingResponse]):
    """Assembles the speaking loader, scorer and signal deriver.

    Speaking differs from the other engines in that scoring depends on an
    external analysis step. Callers run transcription/analysis first, then
    pass the results to :meth:`evaluate_with_analyses`.
    """

    level_bands = LEVEL_BANDS

    def __init__(self) -> None:
        super().__init__(
            loader=SpeakingSentenceLoader(),
            scorer=SpeakingScorer(),
            deriver=SpeakingSignalDeriver(),
        )

    @property
    def test_type(self) -> TestType:
        return TestType.SPEAKING

    def item_key(self, item: SpeakingSentence) -> str:
        return item.sentence_id

    # -- item access -------------------------------------------------------
    def shuffled_sentences(
        self,
        grade: Grade,
        *,
        seed: Optional[int] = None,
    ) -> List[SpeakingSentence]:
        return self.loader.shuffled(grade, seed=seed)

    def pick_sentence(
        self,
        grade: Grade,
        *,
        seed: Optional[int] = None,
    ) -> SpeakingSentence:
        return self.loader.pick_one(grade, seed=seed)

    # -- evaluation --------------------------------------------------------
    def evaluate_with_analyses(
        self,
        child_id: str,
        grade: Grade,
        responses: Sequence[SpeakingResponse],
        analyses: Dict[str, SpeechAnalysis],
    ) -> AssessmentResult:
        """Score and tag a submission using pre-computed speech analyses.

        ``analyses`` maps sentence id to the analysis for that recording.
        Sentences absent from the mapping are recorded as not attempted.
        """
        self.scorer.with_analyses(analyses)
        self.deriver.with_analyses(analyses)
        return self.evaluate(child_id, grade, responses)

    def evaluate(
        self,
        child_id: str,
        grade: Grade,
        responses: Sequence[SpeakingResponse],
    ) -> AssessmentResult:
        """Run the standard pipeline.

        Prefer :meth:`evaluate_with_analyses`; calling this directly without
        first attaching analyses scores every sentence as not attempted.
        """
        return super().evaluate(child_id, grade, responses)

    # -- reporting ---------------------------------------------------------
    def recommend(self, score: TestScore, tags: Sequence[TagOutput]) -> str:
        for minimum, text in _RECOMMENDATIONS:
            if score.percentage >= minimum:
                return text
        return _RECOMMENDATIONS[-1][1]

    def summary_message(self, score: TestScore) -> str:
        not_attempted = score.total_items - score.answered_items
        return (
            f"Submission completed: {score.answered_items} answered, "
            f"{not_attempted} not attempted."
        )

    def average_score(self, score: TestScore) -> float:
        return self.scorer.average_score(score)

    def narration_targets(self, grade: Grade) -> List[Tuple[str, str]]:
        """One narration clip per sentence."""
        return [
            (sentence.sentence_id, sentence.sentence)
            for sentence in self.loader.audio_targets(grade)
        ]

    def narration_speed(self) -> float:
        return get_settings().audio.speaking_speed
