import requests

API_BASE = "http://localhost:8000"

# Fill these with valid values for your test
id_token = "YOUR_ID_TOKEN"
child_id = "YOUR_CHILD_ID"
grade = "Kindergarten"  # or "First", "Second", "Third"

payload = {
    "idToken": id_token,
    "child_id": child_id,
    "grade": grade
}

resp = requests.post(f"{API_BASE}/speaking/complete_result/", json=payload)

print(f"Status: {resp.status_code}")
try:
    print(resp.json())
except Exception:
    print(resp.text)
