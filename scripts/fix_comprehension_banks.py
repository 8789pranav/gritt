"""Fix comprehension question banks: S3 (retag), S4 (add vocab), S5 (context)."""
import json
import sys

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

# === Kindergarten ===
k = load("Z:/grittt/data/questions/comprehension/kindergarten.json")
# k1_q6 already retagged, k2_q4 already retagged
# Add 2 vocabulary questions
k["stories"][0]["questions"].append({
    "question_id": "k1_q7",
    "question": "In the story, what does 'zooming' mean when Max goes 'Zoom, zoom, zoom!' around the yard?",
    "options": ["Moving very slowly", "Moving very fast", "Sleeping quietly", "Eating food"],
    "correct_index": 1,
    "question_type": "vocabulary"
})
k["stories"][1]["questions"].append({
    "question_id": "k2_q6",
    "question": "In the story, what does 'flutter' mean when the butterfly goes 'Flutter, flutter!'?",
    "options": ["Sitting still on a leaf", "Flying with quick, light wing movements", "Crawling on the ground", "Sleeping in a flower"],
    "correct_index": 1,
    "question_type": "vocabulary"
})
k["total_questions"] = sum(len(s["questions"]) for s in k["stories"])
save("Z:/grittt/data/questions/comprehension/kindergarten.json", k)
print(f"Kindergarten: {k['total_questions']} questions")

# === Grade 1 ===
g1 = load("Z:/grittt/data/questions/comprehension/grade_1.json")
# f1_q4 is borderline — retag as literal (the connection is stated)
for q in g1["stories"][0]["questions"]:
    if q["question_id"] == "f1_q4":
        q["question_type"] = "literal"
# Add 2 vocabulary questions
g1["stories"][0]["questions"].append({
    "question_id": "f1_q7",
    "question": "In the story, what does 'purr' mean when the kitten started to purr?",
    "options": ["A soft happy sound a cat makes", "A loud bark", "A type of food", "A kind of toy"],
    "correct_index": 0,
    "question_type": "vocabulary"
})
g1["stories"][1]["questions"].append({
    "question_id": "f2_q6",
    "question": "In the story, what does 'wobble' mean when Jake went 'Wobble, wobble' on his bike?",
    "options": ["Riding perfectly straight", "Shaking unsteadily from side to side", "Going very fast", "Stopping suddenly"],
    "correct_index": 1,
    "question_type": "vocabulary"
})
g1["total_questions"] = sum(len(s["questions"]) for s in g1["stories"])
save("Z:/grittt/data/questions/comprehension/grade_1.json", g1)
print(f"Grade 1: {g1['total_questions']} questions")

# === Grade 2 ===
g2 = load("Z:/grittt/data/questions/comprehension/grade_2.json")
# s1_q4: "According to the story, what was the real treasure?" — retag as literal
for q in g2["stories"][0]["questions"]:
    if q["question_id"] == "s1_q4":
        q["question_type"] = "literal"
# Add 2 vocabulary questions
g2["stories"][0]["questions"].append({
    "question_id": "s1_q6",
    "question": "In the story, what does 'rust' mean when Sophie found a metal box covered in rust?",
    "options": ["A type of treasure inside the box", "A reddish-brown coating that forms on old metal", "A kind of lock on the box", "A label on the box"],
    "correct_index": 1,
    "question_type": "vocabulary"
})
g2["stories"][1]["questions"].append({
    "question_id": "s2_q6",
    "question": "In the story, what does 'erupt' mean when Marcus made a volcano that would actually erupt?",
    "options": ["To stay quiet and still", "To burst out or explode", "To slowly disappear", "To change color"],
    "correct_index": 1,
    "question_type": "vocabulary"
})
g2["total_questions"] = sum(len(s["questions"]) for s in g2["stories"])
save("Z:/grittt/data/questions/comprehension/grade_2.json", g2)
print(f"Grade 2: {g2['total_questions']} questions")

# === Grade 3 ===
g3 = load("Z:/grittt/data/questions/comprehension/grade_3.json")
# Retag: t1_q4 (who created treasure hunt), t2_q1 (why afraid of water), t2_q4 (what lesson) — all literal
for q in g3["stories"][0]["questions"]:
    if q["question_id"] == "t1_q4":
        q["question_type"] = "literal"
for q in g3["stories"][1]["questions"]:
    if q["question_id"] in ("t2_q1", "t2_q4"):
        q["question_type"] = "literal"
# Rewrite the "elegant" vocabulary question with better context clues
# (the story already says "her name written in elegant cursive" — add context)
# Update the story text to give a clue
g3["stories"][0]["story_text"] = g3["stories"][0]["story_text"].replace(
    "It had no return address, just her name written in elegant cursive.",
    "It had no return address, just her name written in elegant cursive, with every letter flowing gracefully and beautifully."
)
# Add real inference questions to replace the retagged ones
g3["stories"][0]["questions"].append({
    "question_id": "t1_q6",
    "question": "Why do you think Aria's grandmother made a treasure hunt instead of simply giving her the journal?",
    "options": [
        "Because she wanted Aria to earn it",
        "Because she wanted Aria to feel the same excitement and adventure she felt at that school",
        "Because she forgot where the journal was",
        "Because she didn't want Aria to have it"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
g3["stories"][1]["questions"].append({
    "question_id": "t2_q5",
    "question": "Why do you think Maya started Daniel at the shallow end instead of the deep end?",
    "options": [
        "Because the shallow end was closer",
        "Because she knew deep water would scare him, and starting small would help him feel safe first",
        "Because the deep end was closed",
        "Because she couldn't swim in the deep end"
    ],
    "correct_index": 1,
    "question_type": "inferential"
})
# Add 1 more vocabulary question to reach 3
g3["stories"][1]["questions"].append({
    "question_id": "t2_q6",
    "question": "In the story, what does 'terrified' mean when it says Daniel had always been terrified of water?",
    "options": [
        "A little bit nervous",
        "Very afraid or frightened",
        "Excited and happy",
        "Bored and uninterested"
    ],
    "correct_index": 1,
    "question_type": "vocabulary"
})
g3["total_questions"] = sum(len(s["questions"]) for s in g3["stories"])
save("Z:/grittt/data/questions/comprehension/grade_3.json", g3)
print(f"Grade 3: {g3['total_questions']} questions")

print("All comprehension banks updated.")
