"""Verify all 4 test types' complete_result responses with edge cases."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.enums import Grade, WordType
from app.domain.models import (
    LogicResponse,
    SpellingResponse,
    SpeakingResponse,
    ComprehensionResponse,
)
from app.engines.registry import (
    logic_engine,
    spelling_engine,
    speaking_engine,
    comprehension_engine,
)


def sep(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def check_overlap(test_name, strengths, focus_areas):
    s = set(strengths)
    f = set(focus_areas)
    overlap = s & f
    if overlap:
        print(f"  FAIL [{test_name}]: strengths & focus_areas overlap: {overlap}")
        return False
    print(f"  OK   [{test_name}]: no overlap between strengths and focus_areas")
    return True


def check_teacher_detail(test_name, table_data, per_item_tags, tag_key="item_id"):
    tag_map = {p.get(tag_key, ""): p.get("tags", []) for p in per_item_tags}
    ok = True
    for row in table_data:
        if not row.get("correct", True) and row.get("error_type"):
            tags = tag_map.get(row.get("word", row.get("question", row.get("sentence_id", ""))), [])
            if "unrelated_attempt" in tags and row["error_type"] not in ("Unrelated attempt", "Rushed attempt", "Sight word (unrelated)"):
                print(f"  FAIL [{test_name}]: {row.get('word', row.get('question', row.get('sentence_id', '')))} error_type={row['error_type']!r} but tags={tags}")
                ok = False
    if ok:
        print(f"  OK   [{test_name}]: teacher_admin_detail error_type respects per_item_tags")
    return ok


# ── 1. LOGIC ────────────────────────────────────────────────────────────────
def test_logic():
    all_ok = True
    engine = logic_engine()
    grade = Grade.FIRST
    items = engine.get_items(grade)

    # Scenario A: All correct
    sep("LOGIC — Scenario A: All correct")
    responses = [
        LogicResponse(item_id=q.item_id, selected_answer_index=q.correct_answer_index, response_time_seconds=5.0)
        for q in items
    ]
    result = engine.evaluate("child-1", grade, responses)
    dear_parent = [{"tag": t.tag, "polarity": t.polarity.value, "confidence": t.confidence.value, "description": t.description} for t in result.tags]
    per_item = [{"item_id": p.item_id, "answered": p.answered, "is_correct": p.is_correct, "tags": p.tags} for p in result.per_item_tags]
    strengths = [t["tag"] for t in dear_parent if t["polarity"] == "strength"]
    focus = [t["tag"] for t in dear_parent if t["polarity"] == "growth_edge"]
    print(f"Score: {result.score.percentage}% ({result.score.correct_answers}/{result.score.total_items})")
    print(f"Tags: {[t['tag'] for t in dear_parent]}")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    all_ok &= check_overlap("Logic-A", strengths, focus)

    # Scenario B: Half wrong, some impulsive (fast wrong)
    sep("LOGIC — Scenario B: Half wrong + impulsive")
    responses = []
    for i, q in enumerate(items):
        if i < len(items) // 2:
            responses.append(LogicResponse(item_id=q.item_id, selected_answer_index=q.correct_answer_index, response_time_seconds=10.0))
        else:
            wrong = (q.correct_answer_index + 1) % len(q.options)
            responses.append(LogicResponse(item_id=q.item_id, selected_answer_index=wrong, response_time_seconds=2.0))
    result = engine.evaluate("child-2", grade, responses)
    dear_parent = [{"tag": t.tag, "polarity": t.polarity.value, "confidence": t.confidence.value, "description": t.description} for t in result.tags]
    per_item = [{"item_id": p.item_id, "answered": p.answered, "is_correct": p.is_correct, "tags": p.tags} for p in result.per_item_tags]
    strengths = [t["tag"] for t in dear_parent if t["polarity"] == "strength"]
    focus = [t["tag"] for t in dear_parent if t["polarity"] == "growth_edge"]
    print(f"Score: {result.score.percentage}% ({result.score.correct_answers}/{result.score.total_items})")
    print(f"Per-item tags sample: {per_item[:3]}")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    all_ok &= check_overlap("Logic-B", strengths, focus)

    # Build teacher_admin_detail table_data from scored_items
    scored_items = [s.model_dump() for s in result.score.scored_items]
    per_item_map = {p["item_id"]: p["tags"] for p in per_item}
    def _error_type(item):
        if item.get("is_correct"):
            return None
        tags = per_item_map.get(item.get("item_id", ""), [])
        if "impulsive_response" in tags:
            return "Impulsive response"
        if "trial_and_error_strategy" in tags:
            return "Trial and error"
        for tag in tags:
            if tag.endswith("_missed"):
                return tag.replace("_missed", "").replace("_", " ")
        return "Incorrect"
    table_data = [
        {
            "question": s.get("label", ""),
            "selected_index": s.get("detail", {}).get("selected_index"),
            "correct_index": s.get("detail", {}).get("correct_index"),
            "correct": s.get("is_correct", False),
            "error_type": _error_type(s),
            "icon": "Correct" if s.get("is_correct") else "Incorrect",
        }
        for s in scored_items
    ]
    print(f"\nteacher_admin_detail table_data (first 4):")
    print(json.dumps(table_data[:4], indent=2))
    all_ok &= check_teacher_detail("Logic-B", table_data, per_item)

    # Scenario C: All not attempted
    sep("LOGIC — Scenario C: All not attempted")
    responses = []
    result = engine.evaluate("child-3", grade, responses)
    dear_parent = [{"tag": t.tag, "polarity": t.polarity.value} for t in result.tags]
    per_item = [{"item_id": p.item_id, "answered": p.answered, "tags": p.tags} for p in result.per_item_tags]
    print(f"Score: {result.score.percentage}%")
    print(f"Per-item tags (first 2): {per_item[:2]}")
    print(f"Tags: {dear_parent}")
    strengths = [t["tag"] for t in dear_parent if t["polarity"] == "strength"]
    focus = [t["tag"] for t in dear_parent if t["polarity"] == "growth_edge"]
    all_ok &= check_overlap("Logic-C", strengths, focus)

    return all_ok


# ── 2. SPELLING ─────────────────────────────────────────────────────────────
def test_spelling():
    all_ok = True
    engine = spelling_engine()
    grade = Grade.FIRST
    test_words = engine.build_test(grade)

    # Scenario A: All correct
    sep("SPELLING — Scenario A: All correct")
    responses = [
        SpellingResponse(item_id=w.word, word=w.word, user_input=w.word, word_type=w.word_type, response_time_seconds=5.0)
        for w in test_words
    ]
    result = engine.evaluate("child-1", grade, responses)
    strengths = engine.strengths(result.signals)
    focus = engine.focus_areas(result.score)
    error_analysis = engine.scorer.error_breakdown(result.score)
    print(f"Score: {result.score.percentage}%")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    print(f"Error analysis: {json.dumps(error_analysis)}")
    all_ok &= check_overlap("Spelling-A", strengths, focus)

    # Scenario B: Mixed — correct, misspelled, unrelated, not attempted
    sep("SPELLING — Scenario B: Mixed (correct + misspelled + unrelated + not attempted)")
    responses = []
    for i, w in enumerate(test_words):
        if i == 2:
            inp = "xyz"
        elif i == 5:
            inp = w.word[:-1] if len(w.word) > 1 else "x"
        elif i == 7:
            continue  # not attempted
        else:
            inp = w.word
        responses.append(SpellingResponse(item_id=w.word, word=w.word, user_input=inp, word_type=w.word_type, response_time_seconds=4.0))
    result = engine.evaluate("child-2", grade, responses)
    strengths = engine.strengths(result.signals)
    focus = engine.focus_areas(result.score)
    error_analysis = engine.scorer.error_breakdown(result.score)
    per_word = [{"item_id": p.item_id, "tags": p.tags} for p in result.per_item_tags]
    print(f"Score: {result.score.percentage}%")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    print(f"Error analysis: {json.dumps(error_analysis)}")
    print(f"Per-word tags (first 5): {per_word[:5]}")
    all_ok &= check_overlap("Spelling-B", strengths, focus)

    # Check no phantom errors for unrelated
    for p in per_word:
        if "unrelated_attempt" in p["tags"]:
            item = next((s for s in result.score.scored_items if s.item_id == p["item_id"]), None)
            if item:
                mistakes = item.detail.get("mistakes", {})
                phantom = {"beginning_consonant", "ending_consonant", "short_vowel"} & set(mistakes.keys())
                if phantom:
                    print(f"  FAIL [Spelling-B]: {p['item_id']} has phantom errors: {phantom}")
                    all_ok = False
                else:
                    print(f"  OK   [Spelling-B]: {p['item_id']} unrelated_attempt, no phantom errors")

    # Scenario C: All unrelated — use inputs that share NO letters with target
    sep("SPELLING — Scenario C: All unrelated attempts")
    unrelated_inputs = ["xyz", "foo", "qqq", "zzz", "ppp", "lll", "nnn", "vvv", "kkk", "jjj", "mmm", "ccc", "bbb", "ttt", "www"]
    responses = [
        SpellingResponse(item_id=w.word, word=w.word, user_input=unrelated_inputs[i % len(unrelated_inputs)], word_type=w.word_type, response_time_seconds=5.0)
        for i, w in enumerate(test_words)
    ]
    result = engine.evaluate("child-3", grade, responses)
    strengths = engine.strengths(result.signals)
    focus = engine.focus_areas(result.score)
    error_analysis = engine.scorer.error_breakdown(result.score)
    print(f"Score: {result.score.percentage}%")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    print(f"Error analysis: {json.dumps(error_analysis)}")
    all_ok &= check_overlap("Spelling-C", strengths, focus)
    for k, v in error_analysis.items():
        if v > 0:
            print(f"  FAIL [Spelling-C]: {k}={v} should be 0 for all unrelated")
            all_ok = False
    if all(error_analysis[k] == 0 for k in error_analysis):
        print(f"  OK   [Spelling-C]: all error_analysis counts are 0")

    return all_ok


# ── 3. SPEAKING ─────────────────────────────────────────────────────────────
def test_speaking():
    all_ok = True
    engine = speaking_engine()
    grade = Grade.FIRST
    items = engine.get_items(grade)

    # Scenario A: No audio (all not attempted)
    sep("SPEAKING — Scenario A: All not attempted")
    responses = [
        SpeakingResponse(item_id=s.sentence_id, sentence_id=s.sentence_id, original_sentence=s.sentence, response_time_seconds=8.0)
        for s in items[:4]
    ]
    result = engine.evaluate("child-1", grade, responses)
    dear_parent = [{"tag": t.tag, "polarity": t.polarity.value} for t in result.tags]
    per_item = [{"item_id": p.item_id, "answered": p.answered, "tags": p.tags} for p in result.per_item_tags]
    strengths = [t["tag"] for t in dear_parent if t["polarity"] == "strength"]
    focus = [t["tag"] for t in dear_parent if t["polarity"] == "growth_edge"]
    print(f"Score: {result.score.percentage}%")
    print(f"Per-item tags (first 3): {per_item[:3]}")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    all_ok &= check_overlap("Speaking-A", strengths, focus)

    # Scenario B: Empty responses (nothing submitted)
    sep("SPEAKING — Scenario B: No responses at all")
    result = engine.evaluate("child-2", grade, [])
    dear_parent = [{"tag": t.tag, "polarity": t.polarity.value} for t in result.tags]
    strengths = [t["tag"] for t in dear_parent if t["polarity"] == "strength"]
    focus = [t["tag"] for t in dear_parent if t["polarity"] == "growth_edge"]
    print(f"Score: {result.score.percentage}%")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    all_ok &= check_overlap("Speaking-B", strengths, focus)

    return all_ok


# ── 4. COMPREHENSION ────────────────────────────────────────────────────────
def test_comprehension():
    all_ok = True
    engine = comprehension_engine()
    grade = Grade.FIRST
    items = engine.get_items(grade)

    all_questions = []
    for story in items:
        for q in story.questions:
            all_questions.append((story, q))

    # Scenario A: All correct
    sep("COMPREHENSION — Scenario A: All correct")
    responses = [
        ComprehensionResponse(item_id=story.story_id, question_id=q.question_id, selected_index=q.correct_index, response_time_seconds=10.0)
        for story, q in all_questions
    ]
    result = engine.evaluate("child-1", grade, responses)
    dear_parent = [{"tag": t.tag, "polarity": t.polarity.value} for t in result.tags]
    per_item = [{"item_id": p.item_id, "answered": p.answered, "is_correct": p.is_correct, "tags": p.tags} for p in result.per_item_tags]
    strengths = [t["tag"] for t in dear_parent if t["polarity"] == "strength"]
    focus = [t["tag"] for t in dear_parent if t["polarity"] == "growth_edge"]
    print(f"Score: {result.score.percentage}% ({result.score.correct_answers}/{result.score.total_items})")
    print(f"Tags: {[t['tag'] for t in dear_parent]}")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    all_ok &= check_overlap("Comp-A", strengths, focus)

    # Scenario B: Half wrong
    sep("COMPREHENSION — Scenario B: Half wrong")
    responses = []
    for i, (story, q) in enumerate(all_questions):
        if i < len(all_questions) // 2:
            responses.append(ComprehensionResponse(item_id=story.story_id, question_id=q.question_id, selected_index=q.correct_index, response_time_seconds=10.0))
        else:
            wrong = (q.correct_index + 1) % len(q.options)
            responses.append(ComprehensionResponse(item_id=story.story_id, question_id=q.question_id, selected_index=wrong, response_time_seconds=10.0))
    result = engine.evaluate("child-2", grade, responses)
    dear_parent = [{"tag": t.tag, "polarity": t.polarity.value} for t in result.tags]
    per_item = [{"item_id": p.item_id, "answered": p.answered, "is_correct": p.is_correct, "tags": p.tags} for p in result.per_item_tags]
    strengths = [t["tag"] for t in dear_parent if t["polarity"] == "strength"]
    focus = [t["tag"] for t in dear_parent if t["polarity"] == "growth_edge"]
    print(f"Score: {result.score.percentage}% ({result.score.correct_answers}/{result.score.total_items})")
    print(f"Per-item tags (first 4): {per_item[:4]}")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    all_ok &= check_overlap("Comp-B", strengths, focus)

    # Build teacher_admin_detail table_data
    scored_items = [s.model_dump() for s in result.score.scored_items]
    per_item_map = {p["item_id"]: p["tags"] for p in per_item}
    def _error_type(item):
        if item.get("is_correct"):
            return None
        tags = per_item_map.get(item.get("item_id", ""), [])
        for tag in tags:
            if tag.endswith("_error"):
                return tag.replace("_error", " error")
        return "Incorrect"
    table_data = [
        {
            "question": s.get("label", ""),
            "story_id": s.get("detail", {}).get("story_id", ""),
            "correct": s.get("is_correct", False),
            "error_type": _error_type(s),
            "icon": "Correct" if s.get("is_correct") else "Incorrect",
        }
        for s in scored_items
    ]
    print(f"\nteacher_admin_detail table_data (first 4):")
    print(json.dumps(table_data[:4], indent=2))

    # Scenario C: All not attempted
    sep("COMPREHENSION — Scenario C: All not attempted")
    result = engine.evaluate("child-3", grade, [])
    dear_parent = [{"tag": t.tag, "polarity": t.polarity.value} for t in result.tags]
    per_item = [{"item_id": p.item_id, "answered": p.answered, "tags": p.tags} for p in result.per_item_tags]
    strengths = [t["tag"] for t in dear_parent if t["polarity"] == "strength"]
    focus = [t["tag"] for t in dear_parent if t["polarity"] == "growth_edge"]
    print(f"Score: {result.score.percentage}%")
    print(f"Per-item tags (first 2): {per_item[:2]}")
    print(f"Strengths: {strengths}")
    print(f"Focus areas: {focus}")
    all_ok &= check_overlap("Comp-C", strengths, focus)

    return all_ok


if __name__ == "__main__":
    print("=" * 80)
    print("  COMPLETE RESULT VERIFICATION — ALL 4 TEST TYPES")
    print("=" * 80)

    all_ok = True
    all_ok &= test_logic()
    all_ok &= test_spelling()
    all_ok &= test_speaking()
    all_ok &= test_comprehension()

    print("\n" + "=" * 80)
    if all_ok:
        print("  ALL CHECKS PASSED — ALL 4 TEST TYPES")
    else:
        print("  SOME CHECKS FAILED — SEE ABOVE")
    print("=" * 80)
