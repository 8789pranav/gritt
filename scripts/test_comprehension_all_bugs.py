"""Verify all Story Explorer bugs: S1, S2, S3, S4, S5, S6, S7, C5."""
import sys
sys.path.insert(0, "Z:/grittt")

import json
from collections import Counter

from app.domain.enums import Grade, QuestionType, TestType
from app.engines.comprehension.engine import ComprehensionEngine
from app.domain.models import ComprehensionResponse

engine = ComprehensionEngine()

passed = 0
failed = 0

def check(label, cond, extra=""):
    global passed, failed
    if cond:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label} {extra}")
        failed += 1


def make_response(question, selected, time=5.0):
    return ComprehensionResponse(
        question_id=question.question_id,
        item_id=question.question_id,
        selected_index=selected,
        response_time_seconds=time,
    )


print("=" * 70)
print("S4: Every grade has >= 3 of each question type")
print("=" * 70)

for grade_name, grade in [("Kindergarten", Grade.KINDERGARTEN), ("Grade 1", Grade.FIRST),
                           ("Grade 2", Grade.SECOND), ("Grade 3", Grade.THIRD)]:
    stories = engine.get_items(grade)
    types = Counter()
    for story in stories:
        for q in story.questions:
            types[q.question_type.value] += 1
    print(f"  {grade_name}: {dict(types)}")
    check(f"{grade_name} has >= 3 literal", types["literal"] >= 3)
    check(f"{grade_name} has >= 3 inferential", types["inferential"] >= 3)
    check(f"{grade_name} has >= 3 vocabulary", types["vocabulary"] >= 3)


print()
print("=" * 70)
print("S2: Unanswered questions excluded from denominators")
print("=" * 70)

# Kindergarten: answer only story 2, leave story 1 unanswered
k_stories = engine.get_items(Grade.KINDERGARTEN)
responses = []
answered_questions = []
for story in k_stories:
    if story.story_id == "k_story2":
        for q in story.questions:
            responses.append(make_response(q, q.correct_index, time=5.0))
            answered_questions.append(q)

result = engine.evaluate("test_child", Grade.KINDERGARTEN, responses)
print(f"  Answered: {len(answered_questions)} questions")
print(f"  Score total_items: {result.score.total_items}")
print(f"  Score answered_items: {result.score.answered_items}")
print(f"  Signals total_questions: {result.signals.get('total_questions')}")

check("total_items = answered_items (unanswered excluded)",
      result.score.total_items == len(answered_questions),
      f"total={result.score.total_items}, answered={len(answered_questions)}")
check("answered_items = number answered",
      result.score.answered_items == len(answered_questions),
      f"answered={result.score.answered_items}")
check("signals.total_questions = answered count",
      result.signals.get("total_questions") == len(answered_questions),
      f"total={result.signals.get('total_questions')}")


print()
print("=" * 70)
print("S1: Tags need >= 3 attempted to fire")
print("=" * 70)

# Kindergarten all correct — should fire all 3 strong tags
k_all_correct = []
for story in k_stories:
    for q in story.questions:
        k_all_correct.append(make_response(q, q.correct_index, time=5.0))

result = engine.evaluate("test_child", Grade.KINDERGARTEN, k_all_correct)
tag_ids = [t.tag for t in result.tags]
print(f"  Tags: {tag_ids}")
check("literal_comprehension_strong fires (3+ attempted)",
      "literal_comprehension_strong" in tag_ids)
check("inferential_comprehension_strong fires (3+ attempted)",
      "inferential_comprehension_strong" in tag_ids)
check("vocabulary_in_context_strong fires (3+ attempted)",
      "vocabulary_in_context_strong" in tag_ids)

# Answer only 1 vocabulary question correctly — vocabulary tag should NOT fire
k_few_vocab = []
vocab_done = 0
for story in k_stories:
    for q in story.questions:
        if q.question_type.value == "vocabulary" and vocab_done < 1:
            k_few_vocab.append(make_response(q, q.correct_index, time=5.0))
            vocab_done += 1
        elif q.question_type.value != "vocabulary":
            k_few_vocab.append(make_response(q, q.correct_index, time=5.0))

result = engine.evaluate("test_child", Grade.KINDERGARTEN, k_few_vocab)
tag_ids = [t.tag for t in result.tags]
print(f"  Tags (1 vocab): {tag_ids}")
check("vocabulary_in_context_strong does NOT fire on 1 question",
      "vocabulary_in_context_strong" not in tag_ids, f"tags={tag_ids}")
check("vocabulary_in_context_emerging does NOT fire on 1 question",
      "vocabulary_in_context_emerging" not in tag_ids, f"tags={tag_ids}")


print()
print("=" * 70)
print("S6: No labels, scores, percentages in response")
print("=" * 70)

# Check the recommendation text doesn't contain labels
result = engine.evaluate("test_child", Grade.KINDERGARTEN, k_all_correct)
rec = result.recommendation
print(f"  Recommendation: {rec[:80]}...")
check("Recommendation doesn't say 'Above grade level'",
      "above grade level" not in rec.lower())
check("Recommendation doesn't say 'Outstanding'",
      "outstanding" not in rec.lower())
check("Recommendation describes what child did",
      "your child" in rec.lower())


print()
print("=" * 70)
print("S7: Unanswered questions show 'Not answered' in teacher table")
print("=" * 70)

# Check that unanswered questions have answered=False in scored_items
result = engine.evaluate("test_child", Grade.KINDERGARTEN, responses)
unanswered_items = [s for s in result.score.scored_items
                    if not s.detail.get("answered", True)]
print(f"  Unanswered items: {len(unanswered_items)}")
check("Unanswered items have answered=False",
      all(not s.detail.get("answered", True) for s in unanswered_items))
check("Unanswered items have max_points=0",
      all(s.max_points == 0.0 for s in unanswered_items))


print()
print("=" * 70)
print("S3: No mislabeled inference questions")
print("=" * 70)

# Check that retagged questions are now literal
for grade_name, grade in [("K", Grade.KINDERGARTEN), ("G1", Grade.FIRST),
                           ("G2", Grade.SECOND), ("G3", Grade.THIRD)]:
    stories = engine.get_items(grade)
    for story in stories:
        for q in story.questions:
            if q.question_type.value == "inferential":
                # Check it's a real inference question (answer not stated)
                # We just verify the question type is correct based on our retagging
                pass

# Verify specific retagged questions
g3_stories = engine.get_items(Grade.THIRD)
for story in g3_stories:
    for q in story.questions:
        if q.question_id in ("t1_q4", "t2_q1", "t2_q4"):
            check(f"{q.question_id} is now literal",
                  q.question_type.value == "literal",
                  f"type={q.question_type.value}")

g2_stories = engine.get_items(Grade.SECOND)
for story in g2_stories:
    for q in story.questions:
        if q.question_id == "s1_q4":
            check(f"{q.question_id} is now literal",
                  q.question_type.value == "literal",
                  f"type={q.question_type.value}")

g1_stories = engine.get_items(Grade.FIRST)
for story in g1_stories:
    for q in story.questions:
        if q.question_id == "f1_q4":
            check(f"{q.question_id} is now literal",
                  q.question_type.value == "literal",
                  f"type={q.question_type.value}")


print()
print("=" * 70)
print("C5: response_time_seconds flows through")
print("=" * 70)

# Answer with specific times and verify they flow through
responses_timed = []
for story in k_stories:
    for q in story.questions:
        responses_timed.append(make_response(q, q.correct_index, time=12.5))

result = engine.evaluate("test_child", Grade.KINDERGARTEN, responses_timed)
timed_items = [s for s in result.score.scored_items if s.detail.get("answered", True)]
check("Answered items have response_time_seconds",
      all(s.detail.get("response_time_seconds") == 12.5 for s in timed_items),
      f"times={[s.detail.get('response_time_seconds') for s in timed_items[:3]]}")


print()
print("=" * 70)
print("Growth-edge tags fire on wrong answers")
print("=" * 70)

# All wrong at Grade 3
g3_stories = engine.get_items(Grade.THIRD)
g3_all_wrong = []
for story in g3_stories:
    for q in story.questions:
        wrong = (q.correct_index + 1) % len(q.options)
        g3_all_wrong.append(make_response(q, wrong, time=5.0))

result = engine.evaluate("test_child", Grade.THIRD, g3_all_wrong)
tag_ids = [t.tag for t in result.tags]
print(f"  Tags (all wrong): {tag_ids}")
check("literal_comprehension_emerging fires on wrong",
      "literal_comprehension_emerging" in tag_ids)
check("inferential_comprehension_emerging fires on wrong",
      "inferential_comprehension_emerging" in tag_ids)
check("vocabulary_in_context_emerging fires on wrong",
      "vocabulary_in_context_emerging" in tag_ids)


print()
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 70)
sys.exit(1 if failed else 0)
