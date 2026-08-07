"""Dedicated test script for the Cognitive Logic Assessment APIs."""
import requests

BASE_URL = "http://localhost:8000"
EMAIL = "rajdandeepak@gmail.com"
PASSWORD = "Test@123"
CHILD_ID = "f9fee450-a1ae-4d56-b0a7-e6edb6536074"


def get_child_id(token: str) -> str:
    """Return the known test child ID, or fall back to the first available child."""
    response = requests.post(f"{BASE_URL}/get_children/", json={"idToken": token}, timeout=20)
    if response.status_code != 200:
        raise RuntimeError(f"get_children failed: {response.status_code} {response.text}")

    data = response.json()
    if isinstance(data, dict) and isinstance(data.get("children"), list) and data["children"]:
        first_child = data["children"][0]
        if isinstance(first_child, dict) and first_child.get("child_id"):
            return first_child["child_id"]

    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and first.get("child_id"):
            return first["child_id"]

    # Fallback: use the known test child from the current suite if available.
    if CHILD_ID:
        return CHILD_ID

    # Fallback: create a child for the test user.
    create_resp = requests.post(
        f"{BASE_URL}/add_child/",
        json={"idToken": token, "name": "Logic Test Child", "age": 6, "grade": "Kindergarten"},
        timeout=30,
    )
    if create_resp.status_code != 200:
        raise RuntimeError(f"add_child failed: {create_resp.status_code} {create_resp.text}")

    child_id = create_resp.json().get("child_id")
    if not child_id:
        raise RuntimeError("add_child returned no child_id")
    return child_id


def main() -> None:
    print("=" * 70)
    print("🧠 LOGIC API TEST SUITE")
    print("=" * 70)

    try:
        health = requests.get(f"{BASE_URL}/docs", timeout=10)
        print(f"Server health: {health.status_code}")
        if health.status_code != 200:
            raise RuntimeError("Server is not responding on /docs")
    except Exception as exc:
        print(f"ERROR: Server not running: {exc}")
        return

    login = requests.post(f"{BASE_URL}/login/", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    print(f"Login status: {login.status_code}")
    if login.status_code != 200:
        print(login.text)
        return

    token = login.json().get("id_token")
    if not token:
        print("Login response did not contain id_token")
        return

    child_id = get_child_id(token)
    print(f"Using child_id: {child_id}")

    grade = "Kindergarten"

    print("\n1) /logic/get_test/")
    get_test = requests.post(
        f"{BASE_URL}/logic/get_test/",
        json={"idToken": token, "child_id": child_id, "grade": grade},
        timeout=30,
    )
    print(f"Status: {get_test.status_code}")
    print(get_test.text[:500])
    if get_test.status_code != 200:
        return

    test_payload = get_test.json()
    items = test_payload.get("items", [])
    if not items:
        print("No logic items returned from /logic/get_test/")
        return

    first_item = items[0]
    item_id = first_item.get("item_id")
    print(f"First item id: {item_id}")

    print("\n2) /logic/submit_response/")
    submit_response = requests.post(
        f"{BASE_URL}/logic/submit_response/",
        json={
            "idToken": token,
            "child_id": child_id,
            "item_id": item_id,
            "selected_answer_index": 0,
            "response_time_seconds": 4,
            "attempts": 1,
            "self_corrected": False,
            "explanation_provided": "Test response",
        },
        timeout=30,
    )
    print(f"Status: {submit_response.status_code}")
    print(submit_response.text[:500])
    if submit_response.status_code != 200:
        return

    print("\n3) /logic/submit_test/")
    submit_test = requests.post(
        f"{BASE_URL}/logic/submit_test/",
        json={
            "idToken": token,
            "child_id": child_id,
            "grade": grade,
            "responses": [
                {
                    "item_id": item_id,
                    "selected_answer_index": 0,
                    "response_time_seconds": 4,
                }
            ],
        },
        timeout=30,
    )
    print(f"Status: {submit_test.status_code}")
    print(submit_test.text[:500])
    if submit_test.status_code != 200:
        return

    print("\n4) /logic/complete_result/")
    complete_result = requests.post(
        f"{BASE_URL}/logic/complete_result/",
        json={"idToken": token, "child_id": child_id, "grade": grade},
        timeout=30,
    )
    print(f"Status: {complete_result.status_code}")
    print(complete_result.text[:500])


if __name__ == "__main__":
    main()
