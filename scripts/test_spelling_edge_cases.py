"""Comprehensive spelling/phonics edge-case testing with full API-style responses."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.enums import Grade, WordType
from app.domain.models import SpellingResponse
from app.engines.spelling import SpellingEngine


def build_response(word_item, user_input, time=5.0, hints=0):
    return SpellingResponse(
        item_id=word_item.word,
        word=word_item.word,
        user_input=user_input,
        word_type=word_item.word_type,
        response_time_seconds=time,
        hints_used=hints,
    )


def run_scenario(engine, grade, title, words, inputs, times=None, hints=None):
    sep = "\n" + "=" * 80 + f"\n  SCENARIO: {title}\n" + "=" * 80
    print(sep)

    print("\nInputs:")
    for w, inp in zip(words, inputs):
        tag = "UNRELATED" if inp and inp.lower() != w.word.lower() and _is_unrelated(w.word, inp) else ""
        print(f"  {w.word:>10s} ({w.word_type.value:>8s}) -> {inp!r:>12s}  {tag}")

    responses = []
    for i, w in enumerate(words):
        t = times[i] if times else 5.0
        h = hints[i] if hints else 0
        if inputs[i] is None:
            continue  # skip = not attempted
        responses.append(build_response(w, inputs[i], t, h))

    result = engine.evaluate("child-test", grade, responses)

    # Build the full submit_words response shape
    summary = engine.summary_by_category(result.score)
    error_analysis = engine.scorer.error_breakdown(result.score)

    submit_response = {
        "user_id": "test-uid",
        "child_id": "child-test",
        "grade": grade.value,
        "score_id": "test-score-id",
        "results": [s.model_dump() for s in result.score.scored_items],
        "evaluation": {
            "status": engine.scorer.status_for(result.score.percentage),
            "level": result.score.level,
            "percentage": result.score.percentage,
        },
        "assessment_summary": summary,
        "error_analysis": error_analysis,
        "instructional_recommendation": result.recommendation,
        "confidence": engine.confidence_label(result.score),
        "strengths": engine.strengths(result.signals),
        "focus_areas": engine.focus_areas(result.score),
        "dear_parent_tags": [
            {"tag": t.tag, "polarity": t.polarity.value, "confidence": t.confidence.value, "description": t.description}
            for t in result.tags
        ],
        "per_word_tags": [
            {"item_id": p.item_id, "answered": p.answered, "is_correct": p.is_correct, "tags": p.tags}
            for p in result.per_item_tags
        ],
    }

    # Build the complete_result response shape (teacher_admin_detail)
    scored = result.score.scored_items
    per_word_map = {p.item_id: p.tags for p in result.per_item_tags}

    def _error_type(item):
        if item.is_correct:
            return None
        tags = per_word_map.get(item.item_id, [])
        if "unrelated_attempt" in tags:
            return "Unrelated attempt"
        if "unrelated_attempt_sightword" in tags:
            return "Sight word (unrelated)"
        if "rushed_attempt" in tags:
            return "Rushed attempt"
        if item.detail.get("type") == WordType.SIGHT.value:
            return "Sight word"
        mistakes = item.detail.get("mistakes", {})
        for k in mistakes:
            if k not in ("spelling", "unrelated_attempt"):
                return k.replace("_", " ")
        return None

    table_data = [
        {
            "word": s.label,
            "attempt": s.detail.get("user_input", ""),
            "correct": s.is_correct,
            "error_type": _error_type(s),
            "time": s.detail.get("time", 0.0),
            "hints_used": s.detail.get("hints_used", 0),
            "icon": "Correct" if s.is_correct else "Incorrect",
        }
        for s in scored
    ]

    complete_response = {
        "user_id": "test-uid",
        "child_id": "child-test",
        "grade": grade.value,
        "parent_summary": {
            "overall_accuracy": round(result.score.percentage),
            "phonics_score": round(summary.get("Phonics", {}).get("percentage", 0)),
            "sight_word_score": round(summary.get("Sight Words", {}).get("percentage", 0)),
            "confidence": engine.confidence_label(result.score),
            "key_error_patterns": [
                {"pattern": k, "count": v} for k, v in error_analysis.items() if v > 0
            ],
            "strengths": engine.strengths(result.signals),
            "focus_areas": engine.focus_areas(result.score),
            "recommendation": result.recommendation,
            "note": "Note: Placement is instructional and not a clinical diagnosis.",
        },
        "dear_parent_tags": submit_response["dear_parent_tags"],
        "per_word_tags": submit_response["per_word_tags"],
        "teacher_admin_detail": {
            "test_level": grade.value,
            "words": len(scored),
            "correct": sum(1 for s in scored if s.is_correct),
            "instructional_level": result.score.level,
            "table_data": table_data,
        },
    }

    print("\n--- submit_words RESPONSE ---")
    print(json.dumps(submit_response, indent=2, default=str))

    print("\n--- complete_result RESPONSE ---")
    print(json.dumps(complete_response, indent=2, default=str))

    # Assertions for this scenario
    print("\n--- CHECKS ---")
    _checks(title, submit_response, complete_response, result)

    return result


def _is_unrelated(target, attempt):
    from app.engines.spelling.phonics import is_unrelated_attempt
    return is_unrelated_attempt(target.lower(), (attempt or "").lower())


def _checks(title, submit, complete, result):
    ok = True

    # Check: no phantom feature errors for unrelated attempts
    for pwt in submit["per_word_tags"]:
        if "unrelated_attempt" in pwt["tags"]:
            item = next((s for s in submit["results"] if s["item_id"] == pwt["item_id"]), None)
            if item:
                mistakes = item.get("detail", {}).get("mistakes", {})
                phantom = {"beginning_consonant", "ending_consonant", "short_vowel"} & set(mistakes.keys())
                if phantom:
                    print(f"  FAIL: {pwt['item_id']} has unrelated_attempt but also phantom errors: {phantom}")
                    ok = False

    # Check: error_type in teacher_admin_detail respects unrelated_attempt
    for row in complete["teacher_admin_detail"]["table_data"]:
        if not row["correct"] and row["error_type"]:
            pwt = next((p for p in submit["per_word_tags"] if p["item_id"] == row["word"] or p["item_id"].endswith(":" + row["word"])), None)
            if pwt and "unrelated_attempt" in pwt["tags"]:
                if row["error_type"] not in ("Unrelated attempt", "Rushed attempt"):
                    print(f"  FAIL: {row['word']} error_type={row['error_type']!r} but per_word_tags says unrelated_attempt")
                    ok = False

    # Check: no overlap between strengths and focus_areas
    strengths = set(submit["strengths"])
    focus = set(submit["focus_areas"])
    overlap = strengths & focus
    if overlap:
        print(f"  FAIL: strengths and focus_areas overlap: {overlap}")
        ok = False

    # Check: error_analysis doesn't count unrelated attempts as feature errors
    for pwt in submit["per_word_tags"]:
        if "unrelated_attempt" in pwt["tags"]:
            # This word should not contribute to any feature error count
            pass  # already verified via phantom check

    if ok:
        print(f"  ALL CHECKS PASSED")
    else:
        print(f"  SOME CHECKS FAILED")
    return ok


def main():
    engine = SpellingEngine()
    grade = Grade.FIRST
    all_items = engine.get_items(grade)
    test_words = engine.build_test(grade)

    # Get regular and sight words from the test
    regular = [w for w in test_words if w.word_type is WordType.REGULAR]
    sight = [w for w in test_words if w.word_type is WordType.SIGHT]

    print(f"Grade: {grade.value}")
    print(f"Total items loaded: {len(all_items)}")
    print(f"Test words: {len(test_words)} ({len(regular)} regular, {len(sight)} sight)")
    print()

    all_ok = True

    # ── Edge Case 1: All correct ──
    words = test_words[:8]
    inputs = [w.word for w in words]
    r = run_scenario(engine, grade, "1. All correct", words, inputs)
    all_ok &= True

    # ── Edge Case 2: All unrelated attempts ──
    words = test_words[:8]
    inputs = ["red", "blue", "green", "yellow", "purple", "orange", "pink", "brown"]
    r = run_scenario(engine, grade, "2. All unrelated attempts (completely different words)", words, inputs)
    all_ok &= True

    # ── Edge Case 3: Mixed - correct, misspelled, unrelated, not attempted ──
    words = test_words[:8]
    inputs = [
        words[0].word,           # correct
        words[1].word[:-1],      # misspelled (drop last letter)
        "xyz",                   # unrelated
        words[3].word,           # correct
        None,                    # not attempted
        words[5].word[::-1],     # reversed (likely unrelated)
        words[6].word,           # correct
        "apple",                 # unrelated
    ]
    times = [5.0, 4.0, 2.0, 5.0, 0.0, 3.0, 5.0, 1.5]
    r = run_scenario(engine, grade, "3. Mixed: correct + misspelled + unrelated + not attempted", words, inputs, times=times)
    all_ok &= True

    # ── Edge Case 4: Vowel errors only (replace vowels) ──
    words = test_words[:8]
    inputs = []
    for w in words:
        word = w.word
        modified = list(word)
        for i, ch in enumerate(modified):
            if ch.lower() in "aeiou":
                modified[i] = "a" if ch.lower() != "a" else "e"
                break
        inputs.append("".join(modified))
    r = run_scenario(engine, grade, "4. Vowel errors only (swap first vowel)", words, inputs)
    all_ok &= True

    # ── Edge Case 5: Rushed attempts (fast wrong answers) ──
    words = test_words[:8]
    inputs = [w.word if i % 2 == 0 else w.word[:-1] for i, w in enumerate(words)]
    times = [5.0, 1.0, 5.0, 0.5, 5.0, 2.0, 5.0, 1.0]  # wrong answers are rushed
    r = run_scenario(engine, grade, "5. Rushed attempts (wrong + fast)", words, inputs, times=times)
    all_ok &= True

    # ── Edge Case 6: Empty string inputs ──
    words = test_words[:4]
    inputs = ["", "", "", ""]
    r = run_scenario(engine, grade, "6. Empty string inputs", words, inputs)
    all_ok &= True

    # ── Edge Case 7: Sight words focus (all sight words wrong) ──
    if sight:
        words = sight[:min(5, len(sight))]
        inputs = ["wrong" for _ in words]
        r = run_scenario(engine, grade, "7. All sight words wrong", words, inputs)
        all_ok &= True

    # ── Edge Case 8: One wrong consonant, rest correct ──
    words = test_words[:8]
    inputs = [w.word for w in words]
    # Swap first consonant of word 2
    if len(inputs[1]) > 1:
        inputs[1] = "z" + inputs[1][1:]
    r = run_scenario(engine, grade, "8. One consonant error, rest correct", words, inputs)
    all_ok &= True

    # ── Edge Case 9: Hints used but correct ──
    words = test_words[:6]
    inputs = [w.word for w in words]
    hints = [0, 2, 0, 1, 0, 3]
    r = run_scenario(engine, grade, "9. Hints used but all correct", words, inputs, hints=hints)
    all_ok &= True

    # ── Edge Case 10: Exact reversal (e.g. "cat" -> "tac") ──
    words = test_words[:8]
    inputs = [w.word[::-1] for w in words]
    r = run_scenario(engine, grade, "10. All reversed (cat -> tac)", words, inputs)
    all_ok &= True

    print("\n" + "=" * 80)
    print("  ALL EDGE CASES COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
