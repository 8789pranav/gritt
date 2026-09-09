import json

for test in ["spelling", "speaking", "logic", "comprehension"]:
    data = json.load(open(f"Z:/grittt/data/tags/{test}_tags.json", encoding="utf-8"))
    print(f"\n{test}:")
    for t in data["tags"]:
        print(f"  {t['id']} ({t['polarity']})")
