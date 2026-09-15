"""Fix D1, D3, D7, D9: Replace bad questions, fix story, add inference questions, re-shuffle."""
import json
import random

random.seed(99)

# ============================================================
# D7: Fix Grade 2 story - "blue ribbon" → "red ribbon" (second place = red in US)
# ============================================================
g2 = json.loads(open("data/questions/comprehension/grade_2.json", encoding="utf-8").read())
g2["stories"][1]["story_text"] = g2["stories"][1]["story_text"].replace(
    "received a blue ribbon", "received a red ribbon"
)

# ============================================================
# D1: Replace Grade 2 fake vocabulary question with a real one
# ============================================================
g2["stories"][1]["questions"] = [
    q for q in g2["stories"][1]["questions"]
    if q["question_id"] != "s2_q4"
]
g2["stories"][1]["questions"].append({
    "question_id": "s2_q4",
    "question": "In the story, what does 'magma' mean when Marcus learned about magma deep inside the Earth?",
    "options": [
        "Hot liquid rock inside a volcano",
        "Cold water under the ground",
        "A type of rock found on the surface",
        "A tool used to build volcanoes"
    ],
    "correct_index": 0,
    "question_type": "vocabulary"
})

# ============================================================
# D9: Add 2 more inference questions to Grade 2
# ============================================================
g2["stories"][0]["questions"].append({
    "question_id": "s1_q5",
    "question": "Why do you think Sophie's grandmother created the treasure map years ago?",
    "options": [
        "To hide her valuables from thieves",
        "To share her childhood memories with Sophie someday",
        "Because she forgot where she put her things",
        "To test Sophie's math skills"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
g2["stories"][1]["questions"].append({
    "question_id": "s2_q5",
    "question": "What does Marcus's science fair project tell us about him?",
    "options": [
        "He likes to copy other people's work",
        "He is curious and works hard to learn new things",
        "He only cares about winning prizes",
        "He doesn't like science very much"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
g2["total_questions"] = sum(len(s["questions"]) for s in g2["stories"])

# ============================================================
# D3: Replace Kindergarten bad inference question with a real one
# D9: Add 2 more inference questions to Kindergarten
# ============================================================
k = json.loads(open("data/questions/comprehension/kindergarten.json", encoding="utf-8").read())

# D3: Replace "What color was NOT mentioned?" with a real inference question
for i, q in enumerate(k["stories"][1]["questions"]):
    if q["question_id"] == "k2_q4":
        k["stories"][1]["questions"][i] = {
            "question_id": "k2_q4",
            "question": "How did Lily feel when she saw the first green leaf pop up from the ground?",
            "options": [
                "Bored and tired",
                "Scared and worried",
                "Excited and happy",
                "Angry and frustrated"
            ],
            "correct_index": 2,
            "question_type": "inferential"
        }

# D9: Add another inference question to K story 1
k["stories"][0]["questions"].append({
    "question_id": "k1_q6",
    "question": "How do you think Max felt when he met Fluffy the cat?",
    "options": [
        "Sad and lonely",
        "Angry and growly",
        "Happy and excited",
        "Scared and hiding"
    ],
    "correct_index": 2,
    "question_type": "inferential"
})

# D9: Add another inference question to K story 2
k["stories"][1]["questions"].append({
    "question_id": "k2_q5",
    "question": "Why do you think the butterfly landed on the biggest flower?",
    "options": [
        "Because it was the most colourful and attractive",
        "Because it was the only flower",
        "Because the butterfly was tired",
        "Because Lily told it to"
    ],
    "correct_index": 0,
    "question_type": "inferential"
})
k["total_questions"] = sum(len(s["questions"]) for s in k["stories"])

# ============================================================
# D9: Add 2 more inference questions to Grade 1
# ============================================================
g1 = json.loads(open("data/questions/comprehension/grade_1.json", encoding="utf-8").read())

g1["stories"][0]["questions"].append({
    "question_id": "f1_q6",
    "question": "Why did Emma's parents smile at each other after nobody claimed the kitten?",
    "options": [
        "They were happy nobody found the owner",
        "They had already decided to let Emma keep the kitten",
        "They were laughing at the kitten",
        "They were thinking about getting a dog"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
g1["stories"][1]["questions"].append({
    "question_id": "f2_q5",
    "question": "Why did Jake try not to look sad when he didn't see a bicycle?",
    "options": [
        "Because he didn't want a bicycle anymore",
        "Because he didn't want to seem ungrateful for his party",
        "Because he was actually happy",
        "Because his parents told him to stop"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
g1["total_questions"] = sum(len(s["questions"]) for s in g1["stories"])

# ============================================================
# Re-shuffle all answer positions across all four grades
# ============================================================
GRADE_FILES = {
    "kindergarten": ("data/questions/comprehension/kindergarten.json", k),
    "grade_1": ("data/questions/comprehension/grade_1.json", g1),
    "grade_2": ("data/questions/comprehension/grade_2.json", g2),
    "grade_3": ("data/questions/comprehension/grade_3.json", None),  # read from disk
}

for grade_key, (file_path, data) in GRADE_FILES.items():
    if data is None:
        data = json.loads(open(file_path, encoding="utf-8").read())

    all_questions = []
    for story in data["stories"]:
        all_questions.extend(story["questions"])

    n = len(all_questions)
    n_options = 4

    target_per_position = n // n_options
    remainder = n % n_options
    target_counts = [target_per_position + (1 if i < remainder else 0) for i in range(n_options)]

    position_pool = []
    for pos, count in enumerate(target_counts):
        position_pool.extend([pos] * count)
    random.shuffle(position_pool)

    for i, q in enumerate(all_questions):
        new_correct = position_pool[i]
        old_correct = q["correct_index"]
        if new_correct != old_correct:
            options = q["options"]
            options[old_correct], options[new_correct] = options[new_correct], options[old_correct]
            q["correct_index"] = new_correct

    data["total_questions"] = n

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    positions = [q["correct_index"] for q in all_questions]
    types = {}
    for q in all_questions:
        types[q["question_type"]] = types.get(q["question_type"], 0) + 1
    print(f"{grade_key}: {n} questions, positions={positions}, types={types}")
