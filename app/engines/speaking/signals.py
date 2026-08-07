"""
Signal derivation for the speaking assessment.

Averages the per-dimension scores produced by the speech analyzer. Only
answered sentences contribute to the averages, so a partially completed test
is not unfairly penalised - but the shared
``min_sentences_for_speaking_tag`` threshold still guards against drawing
conclusions from one or two clips.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from app.domain.enums import Difficulty, ResponseStatus, TestType
from app.domain.models import PerItemTags, SpeakingResponse, SpeakingSentence, TestScore
from app.engines.base import SignalDeriver
from app.engines.speaking.analyzer import SpeechAnalysis
from app.tagging.config_loader import load_shared_settings

#: Prosody at or below this ratio counts as a flat, monotone delivery.
FLAT_DELIVERY_THRESHOLD = 0.5


class SpeakingSignalDeriver(SignalDeriver[SpeakingSentence, SpeakingResponse]):
    """Derives speaking tagging signals."""

    def __init__(self) -> None:
        super().__init__(TestType.SPEAKING)
        self.analyses: Dict[str, SpeechAnalysis] = {}

    def with_analyses(
        self,
        analyses: Dict[str, SpeechAnalysis],
    ) -> "SpeakingSignalDeriver":
        self.analyses = dict(analyses)
        return self

    def derive(
        self,
        items: Sequence[SpeakingSentence],
        responses: Sequence[SpeakingResponse],
        score: TestScore,
    ) -> Dict[str, Any]:
        sentences_by_id = {sentence.sentence_id: sentence for sentence in items}

        fluency: List[float] = []
        pronunciation: List[float] = []
        prosody: List[float] = []
        grammar: List[float] = []
        hard_band: List[float] = []

        for scored in score.scored_items:
            if scored.status is not ResponseStatus.ANSWERED:
                continue

            analysis = self.analyses.get(scored.item_id)
            if analysis is None:
                continue

            fluency.append(analysis.fluency.normalised)
            pronunciation.append(analysis.pronunciation.normalised)
            prosody.append(analysis.prosody.normalised)
            grammar.append(analysis.grammar.normalised)

            sentence = sentences_by_id.get(scored.item_id)
            if sentence is not None and sentence.difficulty is Difficulty.HARD:
                hard_band.append(round(analysis.overall_score / 100, 4))

        avg_prosody = self._mean(prosody)
        answered = len(fluency)

        # Not enough evidence to characterise delivery from one or two clips.
        minimum = load_shared_settings().threshold("min_sentences_for_speaking_tag", 3)
        has_enough_evidence = answered >= int(minimum)

        return {
            "avg_fluency": self._mean(fluency),
            "avg_pronunciation": self._mean(pronunciation),
            "avg_prosody": avg_prosody,
            "avg_grammar": self._mean(grammar),
            "flat_delivery": bool(
                has_enough_evidence and avg_prosody <= FLAT_DELIVERY_THRESHOLD
            ),
            "hard_band_avg": self._mean(hard_band),
            # Contextual values, not referenced by any trigger.
            "sentences_answered": answered,
            "sentences_total": score.total_items,
            "has_enough_evidence": has_enough_evidence,
            "overall_accuracy": self.ratio(score.points, score.max_points),
        }

    def per_item_tags(
        self,
        items: Sequence[SpeakingSentence],
        responses: Sequence[SpeakingResponse],
    ) -> List[PerItemTags]:
        """Flag the weakest dimension on each attempted sentence."""
        responses_by_id = {r.sentence_id: r for r in responses}
        results: List[PerItemTags] = []

        for sentence in items:
            response = responses_by_id.get(sentence.sentence_id)
            analysis = self.analyses.get(sentence.sentence_id)

            if response is None or analysis is None:
                results.append(
                    PerItemTags(
                        item_id=sentence.sentence_id,
                        answered=False,
                        is_correct=None,
                    )
                )
                continue

            tags: List[str] = []
            dimensions = {
                "pronunciation": analysis.pronunciation.normalised,
                "fluency": analysis.fluency.normalised,
                "prosody": analysis.prosody.normalised,
                "grammar": analysis.grammar.normalised,
            }

            for name, value in dimensions.items():
                if value >= 0.85:
                    tags.append(f"{name}_strong")
                elif value < 0.6:
                    tags.append(f"{name}_needs_work")

            results.append(
                PerItemTags(
                    item_id=sentence.sentence_id,
                    answered=True,
                    is_correct=analysis.overall_score >= 75.0,
                    tags=tags,
                )
            )

        return results

    @staticmethod
    def _mean(values: Sequence[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)
