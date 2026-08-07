"""Verify every Logic Quest question matches the spec exactly."""
from logic_assessment import ALL_LOGIC_ITEMS, get_items_by_grade, GradeLevel

SPEC = {
    "Kindergarten": [
        ("K-1", "Which one does NOT belong? Dog, Cat, Fish, Chair", ["Dog", "Cat", "Fish", "Chair"], 3, "pattern_detection_strong", "easy"),
        ("K-2", "What comes next? Circle, Square, Circle, Square, Circle, ___", ["Triangle", "Square", "Circle", "Star"], 1, "pattern_detection_strong", "easy"),
        ("K-3", "A hat goes on your head. A shoe goes on your foot. Where does a glove go?", ["Your ear", "Your hand", "Your knee", "Your elbow"], 1, "relational_reasoning_present", "easy"),
        ("K-4", "Ravi has 3 red blocks and 2 blue blocks. How many blocks does Ravi have in total?", ["3", "4", "5", "6"], 2, "systematic_problem_solving", "easy"),
        ("K-5", "What is the odd one out? Apple, Banana, Carrot, Grapes?", ["Apple", "Banana", "Carrot", "Grapes"], 2, "pattern_detection_strong", "easy"),
        ("K-6", "A bird can fly. A fish can swim. What can a frog do?", ["Fly", "Read", "Jump", "Drive"], 2, "relational_reasoning_present", "easy"),
        ("K-7", "Which one is the biggest? Ant, dog, horse, cat?", ["An ant", "A dog", "A horse", "A cat"], 2, "reasoning_under_load_emerging", "medium"),
        ("K-8", "If today is sunny, you wear sunglasses. If today is rainy, you wear a raincoat. Today is rainy. What do you wear?", ["Sunglasses", "A raincoat", "A swimsuit", "A scarf"], 1, "systematic_problem_solving", "medium"),
    ],
    "1st Grade": [
        ("1-1", "What comes next? 2, 4, 6, 8, ___", ["9", "10", "11", "12"], 1, "pattern_detection_strong", "easy"),
        ("1-2", "Hot is to cold as big is to ___", ["Tall", "Small", "Fast", "Heavy"], 1, "relational_reasoning_present", "easy"),
        ("1-3", "Mia sorted her toys into two groups. Group 1: ball, marble, orange. Group 2: book, box, block. What rule did Mia use?", ["Color", "Size", "Shape (round vs not round)", "Weight"], 2, "systematic_problem_solving", "medium"),
        ("1-4", "What comes next? Triangle, Triangle, Circle, Triangle, Triangle, Circle, ___", ["Circle", "Square", "Triangle", "Star"], 2, "pattern_detection_strong", "medium"),
        ("1-5", "A puppy grows into a dog. A kitten grows into a cat. A calf grows into a ___", ["Horse", "Cow", "Sheep", "Pig"], 1, "relational_reasoning_present", "medium"),
        ("1-6", "Leo tried to build a tower with round balls. It kept falling. What should he try instead?", ["Use more balls", "Use flat blocks", "Stack them faster", "Use smaller balls"], 1, "flexible_strategy_use", "medium"),
        ("1-7", "There are 3 birds on a fence. 2 more birds land. Then 1 flies away. How many birds are on the fence?", ["3", "4", "5", "6"], 1, "reasoning_under_load_emerging", "medium"),
        ("1-8", "Every animal with wings in this game can fly. A penguin has wings. Can the penguin fly in this game?", ["Yes, because it has wings", "No, because penguins can't really fly", "Only if it wants to", "No, because it's too heavy"], 0, "systematic_problem_solving", "medium"),
    ],
    "2nd Grade": [
        ("2-1", "What number comes next? 3, 6, 9, 12, ___", ["13", "14", "15", "16"], 2, "pattern_detection_strong", "medium"),
        ("2-2", "Shoe is to foot as glove is to ___. Now: hat is to head as belt is to ___", ["Hand, Waist", "Finger, Neck", "Arm, Leg", "Hand, Leg"], 0, "relational_reasoning_present", "medium"),
        ("2-3", "Priya is taller than Sam. Sam is taller than Leo. Who is the shortest?", ["Priya", "Sam", "Leo", "They're all the same height"], 2, "reasoning_under_load_emerging", "hard"),
        ("2-4", "A farmer puts animals in pens using this rule: animals with 4 legs go in the red pen, animals with 2 legs go in the blue pen. The spider has 8 legs. What happens?", ["It goes in the red pen", "It goes in the blue pen", "It goes in both pens", "It doesn't fit either pen"], 3, "systematic_problem_solving", "hard"),
        ("2-5", "Look at this pattern: AB, CD, EF, GH, ___", ["HI", "IJ", "GH", "JK"], 1, "pattern_detection_strong", "medium"),
        ("2-6", "Zara tried to cross a stream by jumping. She couldn't reach. What should she try next?", ["Jump harder", "Look for stepping stones or a log", "Close her eyes and try again", "Jump backwards"], 1, "flexible_strategy_use", "medium"),
        ("2-7", "In a game, red shapes are worth 2 points and blue shapes are worth 3 points. You pick 2 red shapes and 1 blue shape. How many points do you have?", ["5", "6", "7", "8"], 2, "reasoning_under_load_emerging", "hard"),
        ("2-8", "Tom's rule: 'If it has wheels, it goes in the garage. If it has wings, it goes in the hangar.' A toy plane has both wheels and wings. Where does it go?", ["The garage", "The hangar", "Both places", "Neither place"], 2, "flexible_strategy_use", "hard"),
    ],
    "3rd Grade": [
        ("3-1", "Look at this pattern: 2, 6, 18, 54, ___", ["72", "108", "162", "60"], 2, "pattern_detection_strong", "hard"),
        ("3-2", "Maya is older than Kai. Kai is older than Priya. Priya is older than Jude. Who is the second youngest?", ["Maya", "Kai", "Priya", "Jude"], 2, "reasoning_under_load_emerging", "hard"),
        ("3-3", "Every blooper is a floop. Every floop is a zang. Is every blooper a zang?", ["Yes, definitely", "No, never", "Only some bloopers", "Not enough information"], 0, "relational_reasoning_present", "hard"),
        ("3-4", "In a game, you earn a star for every 3 correct answers. You lose a star for every 2 wrong answers. You got 9 right and 4 wrong. How many stars do you have?", ["1", "2", "3", "5"], 0, "systematic_problem_solving", "hard"),
        ("3-5", "Each group follows a rule. Which group breaks its own rule?", ["Cat, Dog, Hamster (pets)", "Rose, Daisy, Sunflower (flowers)", "Red, Blue, Banana (colours)", "Guitar, Drums, Piano (instruments)"], 2, "pattern_detection_strong", "hard"),
        ("3-6", "You're trying to find a word in a dictionary. You open to page 200 and see 'monkey.' Your word is 'planet.' What should you do?", ["Go forward a lot of pages", "Go back a few pages", "Start from the beginning", "Close the dictionary"], 0, "systematic_problem_solving", "hard"),
        ("3-7", "A rule says: 'If it rains, bring an umbrella. If it's cold, wear a jacket.' Today it's raining and cold. What do you do?", ["Bring an umbrella only", "Wear a jacket only", "Bring an umbrella and wear a jacket", "Stay home"], 2, "flexible_strategy_use", "hard"),
        ("3-8", "Aisha tried to solve a puzzle one way and got stuck. She tried a second way and also got stuck. Her friend says 'try combining both ways.' What should Aisha do?", ["Give up", "Try her first way again more carefully", "Use parts of both approaches together", "Ask someone else to do it"], 2, "flexible_strategy_use", "hard"),
    ],
}

GRADE_MAP = {
    "Kindergarten": GradeLevel.KINDERGARTEN_1,
    "1st Grade": GradeLevel.GRADE_1_2,
    "2nd Grade": GradeLevel.GRADE_2_3,
    "3rd Grade": GradeLevel.GRADE_3_4,
}

total_checks = 0
total_pass = 0
total_fail = 0

print("=" * 80)
print("LOGIC QUEST — FULL SPEC VERIFICATION")
print("=" * 80)

for grade_name, grade_level in GRADE_MAP.items():
    print(f"\n{'='*80}")
    print(f"  {grade_name}")
    print(f"{'='*80}")

    items = get_items_by_grade(grade_level)
    spec_items = SPEC[grade_name]

    if len(items) != len(spec_items):
        print(f"  FAIL: {len(items)} items in code vs {len(spec_items)} in spec")

    for i, (spec_item, code_item) in enumerate(zip(spec_items, items)):
        spec_num, spec_q, spec_opts, spec_correct, spec_tag, spec_diff = spec_item
        checks = []

        # Check item_number
        match_num = code_item.item_number == spec_num
        checks.append(("item_number", match_num, f"code='{code_item.item_number}' vs spec='{spec_num}'"))

        # Check question_text
        match_q = code_item.question_text == spec_q
        checks.append(("question_text", match_q, f"code='{code_item.question_text[:60]}...' vs spec='{spec_q[:60]}...'"))

        # Check options
        code_opts = [opt.text for opt in code_item.options]
        match_opts = code_opts == spec_opts
        checks.append(("options", match_opts, f"code={code_opts} vs spec={spec_opts}"))

        # Check correct_answer_index
        match_correct = code_item.correct_answer_index == spec_correct
        checks.append(("correct_answer", match_correct, f"code={code_item.correct_answer_index} vs spec={spec_correct}"))

        # Check primary_tag
        code_tag = code_item.primary_tag.value
        match_tag = code_tag == spec_tag
        checks.append(("cognitive_tag", match_tag, f"code='{code_tag}' vs spec='{spec_tag}'"))

        # Check difficulty
        match_diff = code_item.difficulty == spec_diff
        checks.append(("difficulty", match_diff, f"code='{code_item.difficulty}' vs spec='{spec_diff}'"))

        # Check option count
        match_count = len(code_item.options) == 4
        checks.append(("4_options", match_count, f"code has {len(code_item.options)} options"))

        all_match = all(c[1] for c in checks)
        status = "PASS" if all_match else "FAIL"
        if all_match:
            total_pass += 1
        else:
            total_fail += 1
        total_checks += 1

        print(f"\n  Q{i+1} [{status}] {spec_num}: {spec_q[:60]}...")
        if not all_match:
            for check_name, check_pass, detail in checks:
                if not check_pass:
                    print(f"    MISMATCH [{check_name}]: {detail}")

# Tag coverage summary
print(f"\n\n{'='*80}")
print("TAG COVERAGE SUMMARY")
print(f"{'='*80}")

tag_coverage = {}
for grade_name, grade_level in GRADE_MAP.items():
    items = get_items_by_grade(grade_level)
    tags = [item.primary_tag.value for item in items]
    tag_counts = {}
    for t in tags:
        tag_counts[t] = tag_counts.get(t, 0) + 1
    tag_coverage[grade_name] = tag_counts
    print(f"\n  {grade_name}:")
    for tag, count in sorted(tag_counts.items()):
        print(f"    {tag}: {count}")

# Final result
print(f"\n\n{'='*80}")
print(f"RESULT: {total_pass}/{total_checks} questions fully match spec")
if total_fail == 0:
    print("ALL QUESTIONS MATCH SPEC PERFECTLY")
else:
    print(f"{total_fail} QUESTIONS HAVE MISMATCHES")
print(f"{'='*80}")
