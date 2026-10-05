"""Tests for promo code generation, listing, and redemption."""

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_can_generate_codes(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 3
    assert len(data["codes"]) == 3
    assert len(set(data["codes"])) == 3  # all unique
    for code in data["codes"]:
        assert code.startswith("DPP-")


@pytest.mark.asyncio
async def test_non_admin_cannot_generate(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "test-token", "count": 1,
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_generate_rejects_invalid_count(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 0,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_generate_persists_active_codes(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 2,
    })
    codes = resp.json()["codes"]
    from app.infrastructure.firebase import get_firebase_client
    fb = get_firebase_client()
    for code in codes:
        record = fb.ref(f"promo_codes/{code}").get()
        assert record["status"] == "active"
        assert record["created_by"] == "admin-uid"


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_can_list_codes(client, mock_firebase_auth, seed_user):
    await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 2,
    })
    resp = await client.post("/admin/promo-codes/list/", json={
        "idToken": "admin-token",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["active"] == 2
    assert data["used"] == 0
    assert len(data["codes"]) == 2


@pytest.mark.asyncio
async def test_non_admin_cannot_list(client, mock_firebase_auth, seed_user):
    resp = await client.post("/admin/promo-codes/list/", json={
        "idToken": "test-token",
    })
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Redeem
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_redeem_unlocks_child(client, mock_firebase_auth, seed_user):
    gen = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 1,
    })
    code = gen.json()["codes"][0]

    resp = await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token",
        "code": code,
        "child_id": "child-unpaid",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["child_id"] == "child-unpaid"

    from app.infrastructure.firebase import get_firebase_client
    fb = get_firebase_client()
    child = fb.ref("users/test-uid/children/child-unpaid").get()
    assert child["payment_status"] == "paid"
    assert child["paid_via"] == "promo_code"
    assert child["promo_code"] == code
    # lifetime counter incremented
    user = fb.ref("users/test-uid").get()
    assert user["lifetime_paid_children"] == 2  # child-1 already paid + this


@pytest.mark.asyncio
async def test_redeem_is_case_insensitive(client, mock_firebase_auth, seed_user):
    gen = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 1,
    })
    code = gen.json()["codes"][0]

    resp = await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token",
        "code": code.lower(),
        "child_id": "child-unpaid",
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_code_can_only_be_used_once(client, mock_firebase_auth, seed_user):
    gen = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 1,
    })
    code = gen.json()["codes"][0]

    # First redemption succeeds.
    resp1 = await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token", "code": code, "child_id": "child-unpaid",
    })
    assert resp1.status_code == 200

    # Second redemption on the same code fails.
    from app.infrastructure.firebase import get_firebase_client
    get_firebase_client().ref("users/test-uid/children/child-2").set({
        "name": "Second Kid", "age": 5, "grade": "First", "payment_status": "unpaid",
    })
    resp2 = await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token", "code": code, "child_id": "child-2",
    })
    assert resp2.status_code == 400
    # Second child stays unpaid.
    child2 = get_firebase_client().ref("users/test-uid/children/child-2").get()
    assert child2["payment_status"] == "unpaid"


@pytest.mark.asyncio
async def test_redeem_unknown_code(client, mock_firebase_auth, seed_user):
    resp = await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token", "code": "DPP-NOPE-NOPE", "child_id": "child-unpaid",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_redeem_already_paid_child(client, mock_firebase_auth, seed_user):
    gen = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 1,
    })
    code = gen.json()["codes"][0]
    resp = await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token", "code": code, "child_id": "child-1",
    })
    assert resp.status_code == 400  # child-1 is already paid


@pytest.mark.asyncio
async def test_redeem_other_parents_child(client, mock_firebase_auth, seed_user):
    from app.infrastructure.firebase import get_firebase_client
    get_firebase_client().ref("users/other-uid/children/other-child").set({
        "name": "Other", "age": 6, "grade": "First", "payment_status": "unpaid",
    })
    gen = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 1,
    })
    code = gen.json()["codes"][0]
    resp = await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token", "code": code, "child_id": "other-child",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_redeem_marks_code_used_with_record(client, mock_firebase_auth, seed_user):
    gen = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 1,
    })
    code = gen.json()["codes"][0]

    await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token", "code": code, "child_id": "child-unpaid",
    })

    from app.infrastructure.firebase import get_firebase_client
    record = get_firebase_client().ref(f"promo_codes/{code}").get()
    assert record["status"] == "used"
    assert record["used_by"] == "test-uid"
    assert record["used_for_child"] == "child-unpaid"
    assert record["used_at"]


@pytest.mark.asyncio
async def test_list_shows_used_status_after_redemption(client, mock_firebase_auth, seed_user):
    gen = await client.post("/admin/promo-codes/generate/", json={
        "idToken": "admin-token", "count": 2,
    })
    codes = gen.json()["codes"]

    await client.post("/promo-codes/redeem/", json={
        "idToken": "test-token", "code": codes[0], "child_id": "child-unpaid",
    })

    resp = await client.post("/admin/promo-codes/list/", json={
        "idToken": "admin-token",
    })
    data = resp.json()
    assert data["active"] == 1
    assert data["used"] == 1
    used_codes = {c["code"] for c in data["codes"] if c["status"] == "used"}
    assert codes[0] in used_codes
    # The used code carries the redemption record.
    used_entry = next(c for c in data["codes"] if c["status"] == "used")
    assert used_entry["used_by"] == "test-uid"
    assert used_entry["used_for_child"] == "child-unpaid"
