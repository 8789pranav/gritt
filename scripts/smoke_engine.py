"""
Developer smoke test for the assessment engines.

Exercises every registered engine end to end against its real question bank -
loading items, scoring a perfect and an empty submission, and emitting tags -
without touching Firebase, OpenAI or the network.

Run from the repository root::

    python scripts/smoke_engine.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.enums import Grade, TestType, WordType  # noqa: E402
from app.domain.models import (  # noqa: E402
    ComprehensionResponse,
    LogicResponse,
    SpeakingResponse,
    SpellingResponse,
)
from app.engines import registry  # noqa: E402
from app.engines.speaking.analyzer import DimensionScore, SpeechAnalysis  # noqa: E402


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    return condition


def smoke_logic() -> List[bool]:
    print("\nLogic Quest engine")
    engine = registry.logic_engine()
    results: List[bool] = []

    for grade in Grade:
        items = engine.get_items(grade)
        results.append(
            check(f"{grade.value}: loaded items", len(items) == 8, f"{len(items)} items")
        )

        # Every item should carry a tag the config knows about.
        known = set(engine.tag_config.tag_ids)
        unknown = [i.item_number for i in items if i.primary_tag.value not in known]
        results.append(
            check(f"{grade.value}: tags resolve", not unknown, ", ".join(unknown))
        )

        # --- all correct -------------------------------------------------
        perfect = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=item.expected_latency_seconds * 0.8,
            )
            for item in items
        ]
        result = engine.evaluate("smoke-child", grade, perfect)
        results.append(
            check(
                f"{grade.value}: perfect score is 100%",
                result.score.percentage == 100.0,
                f"{result.score.percentage}% / {result.score.level}",
            )
        )
        results.append(
            check(
                f"{grade.value}: perfect run emits tags",
                len(result.tags) > 0,
                ", ".join(result.tag_ids) or "none",
            )
        )
        results.append(
            check(
                f"{grade.value}: perfect run has strengths",
                len(result.strengths) > 0,
                f"{len(result.strengths)} strengths",
            )
        )
        results.append(
            check(
                f"{grade.value}: per-item tags cover every item",
                len(result.per_item_tags) == len(items),
                f"{len(result.per_item_tags)}/{len(items)}",
            )
        )

        # --- all wrong ----------------------------------------------------
        wrong = [
            LogicResponse(
                item_id=item.item_id,
                selected_answer_index=(item.correct_answer_index + 1)
                % len(item.options),
                response_time_seconds=item.expected_latency_seconds * 0.8,
            )
            for item in items
        ]
        zero = engine.evaluate("smoke-child", grade, wrong)
        results.append(
            check(
                f"{grade.value}: all-wrong score is 0%",
                zero.score.percentage == 0.0,
                f"{zero.score.percentage}% / {zero.score.level}",
            )
        )

        # --- nothing submitted --------------------------------------------
        empty = engine.evaluate("smoke-child", grade, [])
        results.append(
            check(
                f"{grade.value}: empty submission is safe",
                empty.score.percentage == 0.0
                and empty.score.total_items == len(items)
                and empty.score.answered_items == 0,
                f"answered={empty.score.answered_items}",
            )
        )

    # Signals produced for a perfect Kindergarten run, for eyeballing.
    items = engine.get_items(Grade.KINDERGARTEN)
    perfect = [
        LogicResponse(
            item_id=item.item_id,
            selected_answer_index=item.correct_answer_index,
            response_time_seconds=10,
        )
        for item in items
    ]
    signals = engine.evaluate("smoke-child", Grade.KINDERGARTEN, perfect).signals
    print("\n  Kindergarten signals (all correct):")
    for name in sorted(signals):
        print(f"    {name:<32} {signals[name]}")

    return results


def smoke_spelling() -> List[bool]:
    print("\nSpelling engine")
    engine = registry.spelling_engine()
    results: List[bool] = []

    for grade in Grade:
        items = engine.get_items(grade)
        results.append(
            check(f"{grade.value}: loaded words", len(items) > 0, f"{len(items)} words")
        )

        # A sitting should never be larger than the full bank.
        sitting = engine.build_test(grade)
        results.append(
            check(
                f"{grade.value}: sitting is well formed",
                0 < len(sitting) <= len(items),
                f"{len(sitting)} of {len(items)}",
            )
        )

        # --- everything spelled correctly ---------------------------------
        perfect = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input=item.word,
                word_type=item.word_type,
                response_time_seconds=6.0,
            )
            for item in items
        ]
        result = engine.evaluate("smoke-child", grade, perfect)
        results.append(
            check(
                f"{grade.value}: perfect score is 100%",
                result.score.percentage == 100.0,
                f"{result.score.percentage}% / {result.score.level}",
            )
        )
        results.append(
            check(
                f"{grade.value}: perfect run emits tags",
                len(result.tags) > 0,
                ", ".join(result.tag_ids) or "none",
            )
        )

        # --- everything misspelled ----------------------------------------
        wrong = [
            SpellingResponse(
                item_id=item.item_id,
                word=item.word,
                user_input="zzqq",
                word_type=item.word_type,
                response_time_seconds=6.0,
            )
            for item in items
        ]
        zero = engine.evaluate("smoke-child", grade, wrong)
        results.append(
            check(
                f"{grade.value}: all-wrong scores near zero",
                zero.score.percentage < 20.0,
                f"{zero.score.percentage}%",
            )
        )
        results.append(
            check(
                f"{grade.value}: all-wrong reports focus areas",
                len(engine.focus_areas(zero.score)) > 0,
                ", ".join(engine.focus_areas(zero.score)),
            )
        )

        # --- nothing submitted ---------------------------------------------
        empty = engine.evaluate("smoke-child", grade, [])
        results.append(
            check(
                f"{grade.value}: empty submission is safe",
                empty.score.percentage == 0.0 and empty.score.answered_items == 0,
                f"answered={empty.score.answered_items}",
            )
        )

        summary = engine.summary_by_category(empty.score)
        results.append(
            check(
                f"{grade.value}: category summary present",
                "Phonics" in summary and "Sight Words" in summary,
            )
        )

    return results


def smoke_comprehension() -> List[bool]:
    print("\nComprehension engine")
    engine = registry.comprehension_engine()
    results: List[bool] = []

    for grade in Grade:
        stories = engine.get_items(grade)
        total_questions = engine.total_questions(grade)
        results.append(
            check(
                f"{grade.value}: loaded stories",
                len(stories) > 0 and total_questions > 0,
                f"{len(stories)} stories, {total_questions} questions",
            )
        )

        # Correct answers must never reach the client.
        public = engine.public_stories(grade)
        leaked = [
            q
            for story in public
            for q in story["questions"]  # type: ignore[index]
            if "correct_index" in q
        ]
        results.append(
            check(f"{grade.value}: answers withheld from client", not leaked)
        )

        # --- all correct ----------------------------------------------------
        perfect = [
            ComprehensionResponse(
                item_id=question.question_id,
                question_id=question.question_id,
                selected_index=question.correct_index,
            )
            for story in stories
            for question in story.questions
        ]
        result = engine.evaluate("smoke-child", grade, perfect)
        results.append(
            check(
                f"{grade.value}: perfect score is 100%",
                result.score.percentage == 100.0,
                f"{result.score.percentage}% / {result.score.level}",
            )
        )
        results.append(
            check(
                f"{grade.value}: perfect run emits tags",
                len(result.tags) > 0,
                ", ".join(result.tag_ids) or "none",
            )
        )

        breakdown = engine.story_breakdown(result.score)
        results.append(
            check(
                f"{grade.value}: story breakdown matches story count",
                len(breakdown) == len(stories),
                f"{len(breakdown)}/{len(stories)}",
            )
        )

        # --- all wrong -------------------------------------------------------
        wrong = [
            ComprehensionResponse(
                item_id=question.question_id,
                question_id=question.question_id,
                selected_index=(question.correct_index + 1) % len(question.options),
            )
            for story in stories
            for question in story.questions
        ]
        zero = engine.evaluate("smoke-child", grade, wrong)
        results.append(
            check(
                f"{grade.value}: all-wrong score is 0%",
                zero.score.percentage == 0.0,
                f"{zero.score.percentage}% / {zero.score.level}",
            )
        )

        # --- nothing submitted -------------------------------------------------
        empty = engine.evaluate("smoke-child", grade, [])
        results.append(
            check(
                f"{grade.value}: empty submission is safe",
                empty.score.percentage == 0.0
                and empty.score.total_items == total_questions,
                f"total={empty.score.total_items}",
            )
        )

    return results


def _analysis(score: float) -> SpeechAnalysis:
    """Build a uniform analysis at the given 0-100 score."""
    dimension = DimensionScore(score=score)
    return SpeechAnalysis(
        pronunciation=dimension,
        fluency=dimension,
        prosody=dimension,
        grammar=dimension,
        speaking_rate=dimension,
        overall_score=score,
        level="smoke",
        recommendation="smoke",
    )


def smoke_speaking() -> List[bool]:
    print("\nSpeaking engine")
    engine = registry.speaking_engine()
    results: List[bool] = []

    for grade in Grade:
        sentences = engine.get_items(grade)
        results.append(
            check(
                f"{grade.value}: loaded sentences",
                len(sentences) > 0,
                f"{len(sentences)} sentences",
            )
        )

        responses = [
            SpeakingResponse(
                item_id=sentence.sentence_id,
                sentence_id=sentence.sentence_id,
                original_sentence=sentence.sentence,
                audio_base64="",
            )
            for sentence in sentences
        ]

        # --- strong delivery throughout --------------------------------------
        strong = {s.sentence_id: _analysis(95.0) for s in sentences}
        result = engine.evaluate_with_analyses("smoke-child", grade, responses, strong)
        results.append(
            check(
                f"{grade.value}: strong delivery scores 95%",
                result.score.percentage == 95.0,
                f"{result.score.percentage}% / {result.score.level}",
            )
        )
        results.append(
            check(
                f"{grade.value}: strong delivery emits tags",
                len(result.tags) > 0,
                ", ".join(result.tag_ids) or "none",
            )
        )

        # --- weak delivery should surface a growth edge -----------------------
        weak = {s.sentence_id: _analysis(35.0) for s in sentences}
        low = engine.evaluate_with_analyses("smoke-child", grade, responses, weak)
        results.append(
            check(
                f"{grade.value}: weak delivery flags growth edges",
                len(low.growth_edges) > 0,
                ", ".join(t.tag for t in low.growth_edges) or "none",
            )
        )

        # --- no recordings submitted ------------------------------------------
        empty = engine.evaluate_with_analyses("smoke-child", grade, [], {})
        results.append(
            check(
                f"{grade.value}: empty submission is safe",
                empty.score.percentage == 0.0 and empty.score.answered_items == 0,
                f"answered={empty.score.answered_items}",
            )
        )

    return results


def smoke_registry() -> List[bool]:
    print("\nEngine registry")
    results: List[bool] = []

    tests = registry.registered_tests()
    results.append(
        check("all four tests registered", len(tests) == 4, f"{len(tests)} registered")
    )

    for test in TestType:
        engine = registry.get_engine(test)
        results.append(
            check(f"{test.value}: resolves to matching engine", engine.test_type is test)
        )
        results.append(
            check(
                f"{test.value}: engine is cached",
                registry.get_engine(test) is engine,
            )
        )
        results.append(
            check(
                f"{test.value}: tag config loads",
                len(engine.tag_config.tags) > 0,
                f"{len(engine.tag_config.tags)} tags",
            )
        )

    results.append(
        check(
            "unknown test raises",
            _raises(lambda: registry.resolve("astrology")),
        )
    )

    return results


def _raises(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


def main() -> int:
    print("=" * 62)
    print("ENGINE SMOKE TEST")
    print("=" * 62)

    results: List[bool] = []
    results.extend(smoke_logic())
    results.extend(smoke_spelling())
    results.extend(smoke_comprehension())
    results.extend(smoke_speaking())
    results.extend(smoke_registry())

    passed = sum(1 for r in results if r)
    total = len(results)

    print("\n" + "=" * 62)
    print(f"{passed}/{total} checks passed")
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
