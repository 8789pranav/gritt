import json
from collections import Counter

for g in ["kindergarten", "grade_1", "grade_2", "grade_3"]:
    data = json.load(open(f"Z:/grittt/data/questions/comprehension/{g}.json", encoding="utf-8"))
    types = Counter(q["question_type"] for s in data["stories"] for q in s["questions"])
    print(f"{g}: {dict(types)} (total={sum(types.values())})")
