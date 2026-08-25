"""Tests for payment endpoints and the paid-child enforcement gate."""

from unittest.mock import patch, MagicMock

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def stripe_env(monkeypatch):
    """Configure Stripe settings for the test process."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Quote
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quote_first_child_is_9_dollars(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/test-uid").set({"name": "P", "email": "t@t.com"})
    mock_firebase_client.ref("users/test-uid/children/c1").set({
        "name": "Emma", "age": 7, "grade": "Second", "payment_status": "unpaid",
    })
    resp = await client.post("/payment/quote/", json={
        "idToken": "test-token", "child_ids": ["c1"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cents"] == 900
    assert data["items"][0]["amount_cents"] == 900


@pytest.mark.asyncio
async def test_quote_two_children_is_12_dollars(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/test-uid").set({"name": "P", "email": "t@t.com"})
    mock_firebase_client.ref("users/test-uid/children/c1").set({
        "name": "Emma", "age": 7, "grade": "Second", "payment_status": "unpaid",
    })
    mock_firebase_client.ref("users/test-uid/children/c2").set({
        "name": "Sam", "age": 5, "grade": "Kindergarten", "payment_status": "unpaid",
    })
    resp = await client.post("/payment/quote/", json={
        "idToken": "test-token", "child_ids": ["c1", "c2"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cents"] == 1200
    amounts = [i["amount_cents"] for i in data["items"]]
    assert amounts == [900, 300]


@pytest.mark.asyncio
async def test_quote_after_first_payment_is_3_dollars(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/test-uid").set({
        "name": "P", "email": "t@t.com", "lifetime_paid_children": 1,
    })
    mock_firebase_client.ref("users/test-uid/children/c1").set({
        "name": "Paid Kid", "age": 7, "grade": "Second", "payment_status": "paid",
    })
    mock_firebase_client.ref("users/test-uid/children/c2").set({
        "name": "New Kid", "age": 5, "grade": "Kindergarten", "payment_status": "unpaid",
    })
    resp = await client.post("/payment/quote/", json={
        "idToken": "test-token", "child_ids": ["c2"],
    })
    assert resp.status_code == 200
    assert resp.json()["total_cents"] == 300


@pytest.mark.asyncio
async def test_quote_rejects_already_paid_child(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/test-uid").set({"name": "P", "email": "t@t.com"})
    mock_firebase_client.ref("users/test-uid/children/c1").set({
        "name": "Paid Kid", "age": 7, "grade": "Second", "payment_status": "paid",
    })
    resp = await client.post("/payment/quote/", json={
        "idToken": "test-token", "child_ids": ["c1"],
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_quote_rejects_other_parents_child(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/other-uid/children/c9").set({
        "name": "Other Kid", "age": 7, "grade": "Second", "payment_status": "unpaid",
    })
    resp = await client.post("/payment/quote/", json={
        "idToken": "test-token", "child_ids": ["c9"],
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Checkout session
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_checkout_session(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/test-uid").set({"name": "P", "email": "t@t.com"})
    mock_firebase_client.ref("users/test-uid/children/c1").set({
        "name": "Emma", "age": 7, "grade": "Second", "payment_status": "unpaid",
    })
    fake_session = MagicMock(id="cs_test_123", url="https://checkout.stripe.com/pay/cs_test_123")
    with patch("stripe.checkout.Session.create", return_value=fake_session) as mock_create:
        resp = await client.post("/payment/create-checkout-session/", json={
            "idToken": "test-token",
            "child_ids": ["c1"],
            "success_url": "http://localhost:3000/payment/success?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": "http://localhost:3000/payment/cancelled",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_123"
    assert data["payment_id"]
    # server computed the price, not the client
    line_items = mock_create.call_args.kwargs["line_items"]
    assert line_items[0]["price_data"]["unit_amount"] == 900
    # pending payment record persisted
    payment = mock_firebase_client.ref(f"payments/{data['payment_id']}").get()
    assert payment["status"] == "pending"
    assert payment["stripe_session_id"] == "cs_test_123"


@pytest.mark.asyncio
async def test_create_checkout_session_rejects_bad_redirect(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/test-uid/children/c1").set({
        "name": "Emma", "age": 7, "grade": "Second", "payment_status": "unpaid",
    })
    resp = await client.post("/payment/create-checkout-session/", json={
        "idToken": "test-token",
        "child_ids": ["c1"],
        "success_url": "javascript:alert(1)",
        "cancel_url": "http://localhost:3000/payment/cancelled",
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
def _completed_event(session_id: str):
    return {
        "type": "checkout.session.completed",
        "data": {"object": {"id": session_id, "metadata": {}}},
    }


@pytest.mark.asyncio
async def test_webhook_marks_children_paid(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/test-uid").set({"name": "P", "email": "t@t.com"})
    mock_firebase_client.ref("users/test-uid/children/c1").set({
        "name": "Emma", "age": 7, "grade": "Second", "payment_status": "unpaid",
    })
    mock_firebase_client.ref("payments/pay-1").set({
        "parent_uid": "test-uid",
        "child_ids": ["c1"],
        "amount_cents": 900,
        "currency": "usd",
        "stripe_session_id": "cs_1",
        "status": "pending",
    })
    mock_firebase_client.ref("payment_sessions/cs_1").set("pay-1")

    with patch("stripe.Webhook.construct_event", return_value=_completed_event("cs_1")):
        resp = await client.post(
            "/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"}
        )
    assert resp.status_code == 200

    child = mock_firebase_client.ref("users/test-uid/children/c1").get()
    assert child["payment_status"] == "paid"
    payment = mock_firebase_client.ref("payments/pay-1").get()
    assert payment["status"] == "completed"
    user = mock_firebase_client.ref("users/test-uid").get()
    assert user["lifetime_paid_children"] == 1


@pytest.mark.asyncio
async def test_webhook_is_idempotent(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("users/test-uid").set({"name": "P", "email": "t@t.com"})
    mock_firebase_client.ref("users/test-uid/children/c1").set({
        "name": "Emma", "age": 7, "grade": "Second", "payment_status": "unpaid",
    })
    mock_firebase_client.ref("payments/pay-1").set({
        "parent_uid": "test-uid",
        "child_ids": ["c1"],
        "stripe_session_id": "cs_1",
        "status": "pending",
    })
    mock_firebase_client.ref("payment_sessions/cs_1").set("pay-1")

    with patch("stripe.Webhook.construct_event", return_value=_completed_event("cs_1")):
        await client.post("/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})
        await client.post("/stripe/webhook", content=b"{}", headers={"stripe-signature": "sig"})

    user = mock_firebase_client.ref("users/test-uid").get()
    assert user["lifetime_paid_children"] == 1  # not double-counted


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(client, mock_firebase_auth):
    with patch("stripe.Webhook.construct_event", side_effect=Exception("bad sig")):
        resp = await client.post(
            "/stripe/webhook", content=b"{}", headers={"stripe-signature": "bad"}
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payment_status(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("payments/pay-1").set({
        "parent_uid": "test-uid",
        "child_ids": ["c1"],
        "stripe_session_id": "cs_1",
        "status": "completed",
    })
    resp = await client.post("/payment/status/", json={
        "idToken": "test-token", "payment_id": "pay-1",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_payment_status_hidden_from_other_parent(client, mock_firebase_auth, mock_firebase_client):
    mock_firebase_client.ref("payments/pay-1").set({
        "parent_uid": "someone-else",
        "child_ids": ["c1"],
        "stripe_session_id": "cs_1",
        "status": "completed",
    })
    resp = await client.post("/payment/status/", json={
        "idToken": "test-token", "payment_id": "pay-1",
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Enforcement: unpaid children cannot take tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unpaid_child_gets_402_on_spelling_submit(client, mock_firebase_auth, seed_user):
    resp = await client.post("/submit_words/", json={
        "idToken": "test-token",
        "child_id": "child-unpaid",
        "grade": "First",
        "words": [{"word": "cat", "user_input": "cat", "type": "regular"}],
    })
    assert resp.status_code == 402
    assert resp.json()["error"] == "payment_required"


@pytest.mark.asyncio
async def test_unpaid_child_gets_402_on_logic_test(client, mock_firebase_auth, seed_user):
    resp = await client.post("/logic/get_test/", json={
        "idToken": "test-token",
        "child_id": "child-unpaid",
        "grade": "First",
    })
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_get_children_includes_payment_status(client, mock_firebase_auth, seed_user):
    resp = await client.post("/get_children/", json={"idToken": "test-token"})
    assert resp.status_code == 200
    children = {c["child_id"]: c for c in resp.json()["children"]}
    assert children["child-1"]["payment_status"] == "paid"
    assert children["child-unpaid"]["payment_status"] == "unpaid"
