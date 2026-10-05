# TODO

Open issues found while investigating the 18 Sep report that paid parents
could not generate a Learning Snapshot. Everything here is **unfixed and
untouched in production** - recorded so it is not lost.

Two parents reported the same symptom and had two completely different
causes. The snapshot cause is fixed; the payment cause is not.

---

## 1. Deleting a child destroys what the parent paid for  — BILLING, HIGH

`payment_status: "paid"` is stored **on the child record**, and
`AuthService.delete_child` (`app/services/auth_service.py:191`) deletes that
record with no payment check:

```python
self._children.delete_subtree(uid, child_id, "scores")
self._children.delete(uid, child_id)
```

Delete a paid child and the entitlement goes with it. The payment record
survives saying `completed`, but nothing ever reads it to restore access, so
the parent is back at the 402 gate with no recovery path. Re-adding the child
does not help: the new record is `unpaid`, and `lifetime_paid_children` stays
where it was, so their *next* purchase is merely priced as an additional
child.

**Confirmed in production.** `ginaheaphy@outlook.com` paid **$9.00 on a live
Stripe session** (`cs_live_a1D6pY…`) at 2026-09-17 11:25:43 for child
`ae9c55cb-e00b-453b-a3d5-cfd43cba8be2`. That child no longer exists. She
re-added a child (`Ryleigh`, `aa315728…`) at 21:22:35 the same day; it is
`unpaid` with no assessment data. She is locked out and the money is in the
Stripe account.

Scope across the whole database - 18 completed payments have no unlocked
child, every one of them because the child was deleted:

| Mode | Count | Accounts |
|---|---|---|
| **Live (real money)** | **2, $12.00** | `ginaheaphy@outlook.com` ($9), `nandita@thedearparentproject.com` ($3, internal) |
| Test | 16 | `nandita@`, `pranavkaushlic@` - internal testing |

So one affected paying customer. The Stripe webhook itself is working
correctly in every case.

**Two things to decide, deliberately kept separate:**

- **Gina** needs her access restored. There is no admin "unlock child"
  endpoint today - `app/routers/admin.py` has make-admin, bypass-payment,
  stats, feedback and audio pre-generation, nothing for this - so it is
  currently a direct database write or a new endpoint.
- **The bug.** The option worth considering first is crediting the parent:
  deleting a paid child adds an unused paid slot to the parent record, and
  adding a child consumes one and unlocks automatically. Deletion stays
  allowed, the money is always honoured, and anyone already affected heals
  themselves on their next add. The alternatives are refusing to delete a
  paid child at all (trivial, but every real removal becomes a support
  ticket) or moving entitlements off the child record entirely (most
  correct, but touches the payment gate, the webhook, the pricing counter
  and needs a migration).

---

## 2. A paid child with no assessment data cannot get a letter  — UX, MEDIUM

If a paid child has no results, the evidence package is empty, there is
genuinely nothing to write about, and the snapshot endpoint returns
`success: true` with the generic letter. It is correctly never cached, so
the parent can press the button forever and always see the same empty page -
the *exact* symptom that was reported for the snapshot bug, from a completely
different cause.

Paid children with no or partial data today:

| Child | Tests completed |
|---|---|
| `serenaww`, `gupta`, `Finnlee` | 0 |
| `Child one` | 1 |
| `Amit Gupta`, `Hardik`, `Eko Test` ×2 | 3 |

The API should say "this child has not finished their activities yet" rather
than returning a letter shaped like a success, so the UI can tell the parent
what to actually do.

---

## 3. The test suite calls the real OpenAI API  — TESTING, MEDIUM

`app/core/config.py:26` runs `load_dotenv` at import, so pytest picks up the
live `OPENAI_API_KEY`, and there is no OpenAI mock in `tests/conftest.py`.
`SnapshotWriter.is_configured` is therefore `True` under test and the
snapshot tests make real, billed calls.

Two runs of *identical* code:

| Run | Failures | Time |
|---|---|---|
| 1 | 80 | 8:08 |
| 2 | 86 | 18:14 |

The suite is slow, non-deterministic and costs money on every run, and the
standing ~86-failure backlog cannot be read as signal until this is fixed.
Mocking the OpenAI client in `conftest.py` would make it fast, free and
repeatable.

---

## 4. Blocking work on the event loop  — PERFORMANCE, LOW

Every route is `async def` while doing entirely blocking work (Firebase,
OpenAI). `generate_snapshot` now also backs off up to 3s between API
retries, which freezes the whole server for that time. Changing the route to
a plain `def` hands it to FastAPI's threadpool and costs nothing; the wider
pattern is a separate conversation.

---

## Fixed already (18 Sep, for context)

The snapshot failure `jillianmbrand@gmail.com` reported. Her child *was*
paid and had all four activities; the letter had failed once and the failure
had been cached, so every retry returned the same empty page.

- `snapshot_writer.py` - a raised API call abandoned the whole retry loop and
  discarded any good draft already in hand. API failures now retry on their
  own budget (3, with backoff, 90s timeout) so the 3 drafting attempts stay 3.
- `snapshot_service.py` - results were filtered by the grade on the request,
  so a child whose profile grade had moved on since assessment produced no
  evidence at all. Falls back to their latest results.
- `snapshot.py` - a letter is saved only when the model wrote it, the child
  actually did something, and every section is filled in. A previously
  cached failure is regenerated rather than served, which heals the affected
  record without a database write.

Covered by `tests/test_snapshot_cache.py` and
`tests/test_snapshot_always_generates.py` (20 tests).
