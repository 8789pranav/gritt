"""Spelling (Word Wizard) assessment engine."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from app.core.config import get_settings
from app.domain.enums import Grade, TestType, WordType
from app.domain.models import (
    SpellingResponse,
    SpellingWord,
    TagOutput,
    TestScore,
)
from app.engines.base import AssessmentEngine
from app.engines.spelling.loader import SpellingWordLoader
from app.engines.spelling.phonics import PhonicsFeature
from app.engines.spelling.scorer import LEVEL_BANDS, SpellingScorer
from app.engines.spelling.signals import SpellingSignalDeriver

#: Accuracy at or above this counts as mastery of a phonics feature.
MASTERY_THRESHOLD = 0.75


class SpellingEngine(AssessmentEngine[SpellingWord, SpellingResponse]):
    """Assembles the spelling loader, scorer and signal deriver."""

    level_bands = LEVEL_BANDS

    def __init__(self) -> None:
        super().__init__(
            loader=SpellingWordLoader(),
            scorer=SpellingScorer(),
            deriver=SpellingSignalDeriver(),
        )

    @property
    def test_type(self) -> TestType:
        return TestType.SPELLING

    def item_key(self, item: SpellingWord) -> str:
        return item.word

    def build_test(self, grade: Grade) -> List[SpellingWord]:
        """Word set for one sitting (Kindergarten draws a balanced sample)."""
        return self.loader.build_test(grade)

    # -- reporting ---------------------------------------------------------
    def recommend(self, score: TestScore, tags: Sequence[TagOutput]) -> str:
        weak = self.focus_areas(score)
        if not weak:
            if score.percentage >= 90:
                return "Advance to the next level. Continue practising all phonics patterns."
            return "Keep practising regularly to consolidate these skills."

        return f"Continue practising: {', '.join(weak)}."

    def focus_areas(self, score: TestScore) -> List[str]:
        """Feature names the child made the most errors on, worst first.

        Only features the child has NOT mastered are listed, so a skill never
        appears in both strengths and focus areas.
        """
        from collections import defaultdict

        errors = self.scorer.error_breakdown(score)
        attempts: Dict[str, int] = defaultdict(int)
        correct: Dict[str, int] = defaultdict(int)

        for item in score.scored_items:
            if item.detail.get("type") != WordType.REGULAR.value:
                continue
            mistakes = item.detail.get("mistakes", {})
            if "unrelated_attempt" in mistakes:
                continue
            matched = set(item.detail.get("matched_features", []))
            for feature_value in matched:
                try:
                    feature = PhonicsFeature(feature_value)
                except ValueError:
                    continue
                attempts[feature.error_label] += 1
                correct[feature.error_label] += 1
            for feature_value in mistakes:
                if feature_value in ("spelling", "unrelated_attempt"):
                    continue
                try:
                    feature = PhonicsFeature(feature_value)
                except ValueError:
                    continue
                attempts[feature.error_label] += 1

        ranked = sorted(
            ((label, count) for label, count in errors.items() if count > 0),
            key=lambda pair: -pair[1],
        )

        focus: List[str] = []
        for label, _ in ranked:
            attempted = attempts.get(label, 0)
            if not attempted:
                continue
            accuracy = correct.get(label, 0) / attempted
            if accuracy < MASTERY_THRESHOLD:
                focus.append(label.replace(" error", ""))
            if len(focus) >= 3:
                break

        return focus

    def strengths(self, signals: Dict[str, float]) -> List[str]:
        """Features the child reached mastery on."""
        mastered: List[str] = []
        for feature in PhonicsFeature:
            accuracy = signals.get(f"{feature.value}_accuracy", 0.0)
            if accuracy >= MASTERY_THRESHOLD:
                mastered.append(feature.display_name)
        return mastered

    def summary_by_category(self, score: TestScore) -> Dict[str, Dict[str, float]]:
        """Split the score into Phonics and Sight Words for the parent view."""
        buckets = {
            "Phonics": {WordType.REGULAR.value},
            "Sight Words": {WordType.SIGHT.value},
        }
        summary: Dict[str, Dict[str, float]] = {}

        for label, types in buckets.items():
            items = [
                item
                for item in score.scored_items
                if item.detail.get("type") in types
            ]
            points = sum(item.points for item in items)
            max_points = sum(item.max_points for item in items)
            summary[label] = {
                "score": round(points, 2),
                "max_score": round(max_points, 2),
                "percentage": round(points / max_points * 100, 1) if max_points else 0.0,
            }

        return summary

    def confidence_label(self, score: TestScore) -> str:
        """How reliable the placement is, based on category agreement."""
        summary = self.summary_by_category(score)
        phonics = summary["Phonics"]["percentage"]
        sight = summary["Sight Words"]["percentage"]

        if summary["Sight Words"]["max_score"] == 0:
            return "Medium"

        variance = abs(phonics - sight)
        average = (phonics + sight) / 2

        if variance < 20 and average > 70:
            return "High"
        if variance < 20 and average > 40:
            return "Medium"
        return "Low"

    def narration_targets(self, grade: Grade) -> List[Tuple[str, str]]:
        """Word and example-sentence clips needed for this grade."""
        targets: List[Tuple[str, str]] = []
        for word in self.loader.audio_targets(grade):
            targets.append((f"{word.word}:word", word.word))
            if word.sentence:
                targets.append((f"{word.word}:sentence", word.sentence))
        return targets

    def narration_speeds(self) -> Dict[str, float]:
        """Playback speed per narration kind."""
        audio = get_settings().audio
        return {"word": audio.word_speed, "sentence": audio.sentence_speed}
