"""Executable checks for the Logic Quest Kindergarten-3rd Grade bank."""

from collections import Counter

from logic_assessment import (
    ALL_LOGIC_ITEMS,
    CognitiveTag,
    GradeLevel,
    StudentResponse,
    aggregate_test_results,
    get_items_by_grade,
)


EXPECTED = {
    GradeLevel.KINDERGARTEN_1: (
        [3, 1, 1, 2, 2, 2, 2, 1],
        Counter({
            "pattern_detection_strong": 3,
            "relational_reasoning_present": 2,
            "systematic_problem_solving": 2,
            "reasoning_under_load_emerging": 1,
        }),
    ),
    GradeLevel.GRADE_1_2: (
        [1, 1, 2, 2, 1, 1, 1, 0],
        Counter({
            "pattern_detection_strong": 2,
            "relational_reasoning_present": 2,
            "systematic_problem_solving": 2,
            "flexible_strategy_use": 1,
            "reasoning_under_load_emerging": 1,
        }),
    ),
    GradeLevel.GRADE_2_3: (
        [2, 0, 2, 3, 1, 1, 2, 2],
        Counter({
            "pattern_detection_strong": 2,
            "relational_reasoning_present": 1,
            "systematic_problem_solving": 1,
            "flexible_strategy_use": 2,
            "reasoning_under_load_emerging": 2,
        }),
    ),
    GradeLevel.GRADE_3_4: (
        [2, 2, 0, 0, 2, 0, 2, 2],
        Counter({
            "pattern_detection_strong": 2,
            "relational_reasoning_present": 1,
            "systematic_problem_solving": 2,
            "flexible_strategy_use": 2,
            "reasoning_under_load_emerging": 1,
        }),
    ),
}


def run_checks():
    assert len(ALL_LOGIC_ITEMS) == 32
    assert len({item.item_id for item in ALL_LOGIC_ITEMS}) == 32

    for grade, (answer_keys, expected_tags) in EXPECTED.items():
        items = get_items_by_grade(grade)
        assert len(items) == 8
        assert [item.correct_answer_index for item in items] == answer_keys
        assert Counter(item.primary_tag.value for item in items) == expected_tags
        assert all(len(item.options) == 4 for item in items)
        assert all(item.item_type != "sort_task" for item in items)

        responses = [
            StudentResponse(
                student_id="logic_quest_check",
                item_id=item.item_id,
                selected_answer_index=item.correct_answer_index,
                response_time_seconds=20,
            )
            for item in items
        ]
        result = aggregate_test_results(responses, grade)
        assert result.total_correct == 8
        assert result.total_items == 8
        assert result.score_percentage == 100.0

    assert CognitiveTag.PATTERN_DETECTION_EMERGING not in {
        item.primary_tag for item in ALL_LOGIC_ITEMS
    }
    print("Logic Quest specification checks passed.")


if __name__ == "__main__":
    run_checks()
