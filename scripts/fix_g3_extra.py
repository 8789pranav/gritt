import json

g3 = json.load(open("Z:/grittt/data/questions/comprehension/grade_3.json", encoding="utf-8"))
# Add 1 more vocabulary to story 1
g3["stories"][0]["questions"].append({
    "question_id": "t1_q7",
    "question": "In the story, what does 'riddle' mean when Aria found a riddle inside the letter?",
    "options": [
        "A type of envelope",
        "A puzzle or question that needs clever thinking to solve",
        "A kind of stamp",
        "A list of rules"
    ],
    "correct_index": 1,
    "question_type": "vocabulary"
})
# Add 1 more inferential to story 1
g3["stories"][0]["questions"].append({
    "question_id": "t1_q8",
    "question": "Why do you think the grandmother hid clues in different places around the school instead of putting them all in one spot?",
    "options": [
        "Because she couldn't carry them all",
        "Because she wanted Aria to explore the school and remember each place",
        "Because she only had one clue",
        "Because the school was too small"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
g3["total_questions"] = sum(len(s["questions"]) for s in g3["stories"])
with open("Z:/grittt/data/questions/comprehension/grade_3.json", "w", encoding="utf-8") as f:
    json.dump(g3, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(f"Grade 3: {g3['total_questions']} questions")
