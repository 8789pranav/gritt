"""Run the spelling engine 5 times with different inputs and print per-word tags."""
from __future__ import annotations

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.enums import Grade
from app.domain.models import SpellingResponse
from app.engines.spelling import SpellingEngine
from app.engines.spelling.loader import SpellingWordLoader
from app.engines.spelling.phonics import PhonicsFeature


def _collect_test_words(grade: Grade) -> list:
    """Return the first 4 words for the grade (regular + sight mix)."""
    loader = SpellingWordLoader()
    all_words = loader.build_test(grade)
    return all_words[:4]


def _make_attempts(words: list, scenario: int) -> list:
    """Build 5 different spelling attempt scenarios for the same words."""
    scenarios = [
        # Scenario 0: all correct
        [w.word for w in words],
        # Scenario 1: reverse first/last letters
        [w.word[::-1] if len(w.word) > 1 else w.word + "x" for w in words],
        # Scenario 2: drop last letter
        [w.word[:-1] for w in words],
        # Scenario 3: unrelated random words
        ["book", "table", "chair", "apple"][: len(words)],
        # Scenario 4: mixed - some correct, some with vowel errors
        [
            w.word if i % 2 == 0 else _vowel_error(w.word)
            for i, w in enumerate(words)
        ],
    ]
    return scenarios[scenario % 5]


def _vowel_error(word: str) -> str:
    """Replace a vowel with another vowel to simulate a vowel error."""
    vowels = "aeiou"
    for i, ch in enumerate(word):
        if ch in vowels:
            new_vowel = random.choice([v for v in vowels if v != ch])
            return word[:i] + new_vowel + word[i + 1 :]
    return word + "e"


def main():
    engine = SpellingEngine()
    grade = Grade.FIRST
    words = _collect_test_words(grade)

    print(f"=== Spelling Engine Test | Grade: {grade.value} | {len(words)} words ===\n")
    for i, w in enumerate(words, 1):
        print(f"Word {i}: '{w.word}' | type: {w.word_type.value} | sentence: {w.sentence}")
    print()

    for scenario in range(5):
        attempts = _make_attempts(words, scenario)
        responses = [
            SpellingResponse(
                item_id=w.word,
                word=w.word,
                user_input=attempts[i],
                word_type=w.word_type,
                response_time_seconds=random.uniform(2.0, 6.0),
            )
            for i, w in enumerate(words)
        ]

        result = engine.evaluate("child", grade, responses)
        per_word_tags = [
            {"item_id": p.item_id, "answered": p.answered, "is_correct": p.is_correct, "tags": p.tags}
            for p in result.per_item_tags
        ]

        print(f"--- Scenario {scenario + 1} ---")
        for w, r, p in zip(words, responses, result.per_item_tags):
            print(f"  {w.word} -> '{r.user_input}' | correct={p.is_correct} | tags={p.tags}")
        print()

    print("=== Sample API-style response for Scenario 3 (unrelated attempts) ===")
    attempts = _make_attempts(words, 3)
    responses = [
        SpellingResponse(
            item_id=w.word,
            word=w.word,
            user_input=attempts[i],
            word_type=w.word_type,
            response_time_seconds=3.0,
        )
        for i, w in enumerate(words)
    ]
    result = engine.evaluate("child", grade, responses)
    api_response = {
        "grade": grade.value,
        "evaluation": {
            "status": engine.scorer.status_for(result.score.percentage),
            "level": result.score.level,
            "percentage": result.score.percentage,
        },
        "assessment_summary": engine.summary_by_category(result.score),
        "error_analysis": engine.scorer.error_breakdown(result.score),
        "confidence": engine.confidence_label(result.score),
        "strengths": engine.strengths(result.signals),
        "focus_areas": engine.focus_areas(result.score),
        "dear_parent_tags": [
            {"tag": t.tag, "polarity": t.polarity.value, "description": t.description}
            for t in result.tags
        ],
        "per_word_tags": [
            {"item_id": p.item_id, "answered": p.answered, "is_correct": p.is_correct, "tags": p.tags}
            for p in result.per_item_tags
        ],
    }
    print(json.dumps(api_response, indent=2))


if __name__ == "__main__":
    main()
