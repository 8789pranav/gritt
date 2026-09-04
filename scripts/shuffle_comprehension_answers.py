"""Shuffle correct answer positions in comprehension question banks and add vocabulary questions."""
import json
import random

random.seed(42)

# Vocabulary questions to add (one per grade that lacks them)
VOCAB_QUESTIONS = {
    "kindergarten": {
        "story_index": 0,  # Add to first story (The Friendly Dog)
        "question": {
            "question_id": "k1_q5",
            "question": "In the story, what does 'cozy' mean when it says Max lived in a cozy red house?",
            "options": [
                "Cold and uncomfortable",
                "Warm and comfortable",
                "Big and empty",
                "Dark and scary"
            ],
            "correct_index": 1,
            "question_type": "vocabulary"
        }
    },
    "grade_1": {
        "story_index": 0,  # Add to first story (The Lost Kitten)
        "question": {
            "question_id": "f1_q5",
            "question": "In the story, what does 'shivering' mean when the kitten was wet and shivering?",
            "options": [
                "Sleeping peacefully",
                "Shaking from cold",
                "Playing happily",
                "Eating quickly"
            ],
            "correct_index": 1,
            "question_type": "vocabulary"
        }
    },
    "grade_3": {
        "story_index": 0,  # Add to first story (The Mysterious Letter)
        "question": {
            "question_id": "t1_q5",
            "question": "In the story, what does 'elegant' mean when it says her name was written in elegant cursive?",
            "options": [
                "Messy and hard to read",
                "Graceful and beautiful",
                "Large and bold",
                "Quick and sloppy"
            ],
            "correct_index": 1,
            "question_type": "vocabulary"
        }
    }
}

GRADE_FILES = {
    "kindergarten": "data/questions/comprehension/kindergarten.json",
    "grade_1": "data/questions/comprehension/grade_1.json",
    "grade_2": "data/questions/comprehension/grade_2.json",
    "grade_3": "data/questions/comprehension/grade_3.json",
}

for grade_key, file_path in GRADE_FILES.items():
    data = json.loads(open(file_path, encoding="utf-8").read())

    # Add vocabulary question if needed
    if grade_key in VOCAB_QUESTIONS:
        vocab = VOCAB_QUESTIONS[grade_key]
        story = data["stories"][vocab["story_index"]]
        story["questions"].append(vocab["question"])

    # Collect all questions across stories
    all_questions = []
    for story in data["stories"]:
        all_questions.extend(story["questions"])

    # Generate a balanced distribution of correct positions
    n = len(all_questions)
    n_options = 4  # all questions have 4 options

    # Target: roughly equal distribution
    target_per_position = n // n_options
    remainder = n % n_options
    target_counts = [target_per_position + (1 if i < remainder else 0) for i in range(n_options)]

    # Shuffle the target positions
    position_pool = []
    for pos, count in enumerate(target_counts):
        position_pool.extend([pos] * count)
    random.shuffle(position_pool)

    # Assign positions
    for i, q in enumerate(all_questions):
        new_correct = position_pool[i]
        old_correct = q["correct_index"]
        if new_correct != old_correct:
            # Swap the correct answer with whatever is at new_correct
            options = q["options"]
            options[old_correct], options[new_correct] = options[new_correct], options[old_correct]
            q["correct_index"] = new_correct

    # Update total_questions
    data["total_questions"] = n

    # Write back
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Report
    positions = [q["correct_index"] for q in all_questions]
    types = {}
    for q in all_questions:
        types[q["question_type"]] = types.get(q["question_type"], 0) + 1
    print(f"{grade_key}: {n} questions, positions={positions}, types={types}")
