"""Test if deployed API returns the new Logic Quest questions."""
import requests

BASE_URL = 'https://nvupmmyd66.us-east-1.awsapprunner.com'
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"

print("=" * 60)
print("TESTING DEPLOYED API FOR NEW LOGIC QUEST QUESTIONS")
print("=" * 60)

# Step 1: Login
print("\n1. Login...")
r = requests.post(f"{BASE_URL}/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
if r.status_code != 200:
    print(f"   FAILED: {r.status_code} - {r.text[:200]}")
    exit(1)
token = r.json().get("id_token")
print("   SUCCESS!")

# Step 2: Get children
print("\n2. Get Children...")
r = requests.post(f"{BASE_URL}/get_children/", json={"idToken": token}, timeout=15)
if r.status_code != 200:
    print(f"   FAILED: {r.status_code} - {r.text[:200]}")
    exit(1)
children = r.json().get("children", [])
if not children:
    print("   No children found, creating one...")
    r = requests.post(f"{BASE_URL}/add_child/", json={
        "idToken": token, "name": "TestChild", "age": 6, "grade": "Kindergarten"
    }, timeout=15)
    if r.status_code == 200:
        child_id = r.json().get("child_id")
    else:
        print(f"   FAILED to create child: {r.text[:200]}")
        exit(1)
else:
    child_id = children[0].get("child_id")
print(f"   Using child: {child_id[:20]}...")

# Step 3: Test each grade
NEW_QUESTION_MARKERS = {
    "Kindergarten": ["Which one does NOT belong", "Circle, Square, Circle, Square", "glove go", "red blocks and 2 blue", "odd one out", "frog do", "biggest", "rainy"],
    "First": ["2, 4, 6, 8", "Hot is to cold", "Mia sorted", "Triangle, Triangle, Circle", "puppy grows", "round balls", "birds on a fence", "penguin"],
    "Second": ["3, 6, 9, 12", "Shoe is to foot", "Priya is taller", "spider has 8 legs", "AB, CD, EF", "cross a stream", "red shapes are worth", "toy plane"],
    "Third": ["2, 6, 18, 54", "Maya is older", "blooper is a floop", "star for every 3", "breaks its own rule", "dictionary", "raining and cold", "combining both ways"],
}

GRADE_PARAMS = {
    "Kindergarten": "Kindergarten",
    "First": "First",
    "Second": "Second",
    "Third": "Third",
}

for grade_name, param in GRADE_PARAMS.items():
    print(f"\n3. Testing grade: {grade_name}...")
    r = requests.post(f"{BASE_URL}/logic/get_test/", json={
        "idToken": token,
        "child_id": child_id,
        "grade": param
    }, timeout=30)

    if r.status_code != 200:
        print(f"   FAILED: {r.status_code} - {r.text[:200]}")
        continue

    data = r.json()
    items = data.get("items", [])
    total = data.get("total_items", 0)
    print(f"   Total items: {total}")

    markers = NEW_QUESTION_MARKERS.get(grade_name, [])
    new_count = 0
    for item in items:
        qtext = item.get("question_text", "")
        item_num = item.get("item_number", "")
        is_new = any(marker.lower() in qtext.lower() for marker in markers)
        tag = "NEW" if is_new else "OLD"
        print(f"   [{tag}] {item_num}: {qtext[:60]}...")
        if is_new:
            new_count += 1

    if new_count > 0:
        print(f"   -> {new_count}/{total} questions match NEW Logic Quest bank")
    else:
        print(f"   -> NO new questions found - still serving old bank!")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
