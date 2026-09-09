import json

g2 = json.load(open("Z:/grittt/data/questions/comprehension/grade_2.json", encoding="utf-8"))
# Add 1 more inferential to story 1
g2["stories"][0]["questions"].append({
    "question_id": "s1_q7",
    "question": "Why do you think Sophie's grandmother kept the treasure map instead of throwing it away?",
    "options": [
        "Because she forgot about it",
        "Because it held memories of her childhood and she wanted to share them someday",
        "Because it was worth a lot of money",
        "Because she didn't want anyone else to find it"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
g2["total_questions"] = sum(len(s["questions"]) for s in g2["stories"])
with open("Z:/grittt/data/questions/comprehension/grade_2.json", "w", encoding="utf-8") as f:
    json.dump(g2, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(f"Grade 2: {g2['total_questions']} questions")
