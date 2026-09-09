import json

g1 = json.load(open("Z:/grittt/data/questions/comprehension/grade_1.json", encoding="utf-8"))
# Add 1 more inferential to story 2
g1["stories"][1]["questions"].append({
    "question_id": "f2_q7",
    "question": "Why do you think Jake kept getting back up every time he fell off his bike?",
    "options": [
        "Because he didn't want to ride anymore",
        "Because he wanted the bicycle so much that he was determined to learn",
        "Because his dad told him to give up",
        "Because he liked falling"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
g1["total_questions"] = sum(len(s["questions"]) for s in g1["stories"])
with open("Z:/grittt/data/questions/comprehension/grade_1.json", "w", encoding="utf-8") as f:
    json.dump(g1, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(f"Grade 1: {g1['total_questions']} questions")
