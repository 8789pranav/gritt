"""
A failed letter must never become the child's one letter.

The snapshot is generated once and cached so every later call returns the
same wording. The cache was written unconditionally, so when Stage B fell
back to the generic letter - model unreachable, or every draft breaking a
guardrail - that empty letter was frozen in place. The parent pressed the
button again, got the same page with nothing about their child on it, and
reported that the snapshot would not generate. That is the bug these tests
close: only a real letter is kept.

"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

import pytest

CHILD_PATH = "users/test-uid/children/child-1"


def _cached(mock_firebase_client) -> Any:
    """What the database actually kept for this child, if anything.

    Read through the repository rather than the raw node: the in-memory
    Firebase creates an empty dict for any path that is read, so the key
    existing proves nothing.
    """
    from app.infrastructure.repositories import SnapshotRepository

    return SnapshotRepository(mock_firebase_client).get("test-uid", "child-1")


def _letter(*, llm_generated: bool, **override: Any) -> Dict[str, Any]:
    """A finished letter: every part a parent actually reads is filled in."""
    letter = {
        "opening": {"headline": "h", "paragraph": "p"},
        "what_i_noticed": [{"point": "a strength"}],
        "still_growing": [{"point": "a growth edge", "because": "evidence"}],
        "for_the_conference": {"items": [{"point": "p", "worth_asking": "q"}]},
        "closing": "c",
        "salutation": "Dear Parent,",
        "signature": "Eko",
        "meta": {"llm_generated": llm_generated, "guardrails_passed": llm_generated},
    }
    letter.update(override)
    return letter


def _evidence(*, tests_completed, strengths=1, growth_edges=1) -> Dict[str, Any]:
    return {
        "child_name": "Test Child",
        "grade": "Second",
        "tests_completed": list(tests_completed),
        "strengths": [{"tag": f"s{i}"} for i in range(strengths)],
        "growth_edges": [{"tag": f"g{i}"} for i in range(growth_edges)],
    }


def _poison(mock_firebase_client) -> None:
    """Cache the generic fallback against this child, as production did."""
    from app.infrastructure.repositories import SnapshotRepository

    SnapshotRepository(mock_firebase_client).save(
        "test-uid",
        "child-1",
        {"success": True, "child_id": "child-1",
         "snapshot": _letter(llm_generated=False)},
    )


@pytest.fixture
def snapshot_stubs():
    """Drive the endpoint's two stages by hand."""
    with patch(
        "app.services.snapshot_service.SnapshotService.build_evidence"
    ) as build, patch(
        "app.services.snapshot_writer.SnapshotWriter.write"
    ) as write:
        yield build, write


async def _generate(client):
    return await client.post(
        "/snapshot/",
        json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
    )


class TestFailedLettersAreNotCached:
    async def test_generic_fallback_is_returned_but_not_saved(
        self, client, seed_user, mock_firebase_client, snapshot_stubs
    ):
        """The parent still sees something; the database keeps nothing."""
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=["logic", "spelling"])
        write.return_value = _letter(llm_generated=False)

        r = await _generate(client)

        assert r.status_code == 200
        assert r.json()["snapshot"]["meta"]["llm_generated"] is False
        assert not _cached(mock_firebase_client)

    async def test_a_letter_built_from_no_results_is_not_saved(
        self, client, seed_user, mock_firebase_client, snapshot_stubs
    ):
        """No results means a letter about nobody, however well written.

        This is what a grade mismatch produces: the request asks for a grade
        the child has no results under, so every fetch comes back empty.
        """
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=[])
        write.return_value = _letter(llm_generated=True)

        r = await _generate(client)

        assert r.status_code == 200
        assert not _cached(mock_firebase_client)

    async def test_a_failed_run_can_be_retried(
        self, client, seed_user, mock_firebase_client, snapshot_stubs
    ):
        """The whole point: the second press reaches the writer again."""
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=["logic", "spelling"])
        write.return_value = _letter(llm_generated=False)
        await _generate(client)

        write.return_value = _letter(llm_generated=True)
        r = await _generate(client)

        assert write.call_count == 2
        assert r.json()["snapshot"]["meta"]["llm_generated"] is True
        assert _cached(mock_firebase_client)


class TestRealLettersAreStillCached:
    async def test_a_real_letter_is_saved_and_reused(
        self, client, seed_user, mock_firebase_client, snapshot_stubs
    ):
        """One child, one letter: the writer is not asked twice."""
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=["logic", "spelling"])
        write.return_value = _letter(llm_generated=True)

        first = await _generate(client)
        second = await _generate(client)

        assert write.call_count == 1
        assert second.json()["snapshot"] == first.json()["snapshot"]
        assert _cached(mock_firebase_client)


class TestAPoisonedCacheHealsItself:
    """The records already saved before the writer stopped failing loudly.

    One paid child in production had the generic letter cached against her
    name. Every press of the button returned it, so from the parent's side
    the snapshot simply never generated. Serving a cached failure is the
    same bug as saving one.
    """

    async def test_a_cached_fallback_is_regenerated(
        self, client, seed_user, mock_firebase_client, snapshot_stubs
    ):
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=["logic", "spelling"])
        write.return_value = _letter(llm_generated=True)

        _poison(mock_firebase_client)
        r = await _generate(client)

        assert write.call_count == 1
        assert r.json()["snapshot"]["meta"]["llm_generated"] is True
        assert _cached(mock_firebase_client)["snapshot"]["meta"]["llm_generated"]

    async def test_a_cached_fallback_is_never_served(
        self, client, seed_user, mock_firebase_client, snapshot_stubs
    ):
        """Even when the retry fails too, the parent is not fobbed off."""
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=["logic", "spelling"])
        write.return_value = _letter(llm_generated=False)

        _poison(mock_firebase_client)
        await _generate(client)

        assert write.call_count == 1


class TestAnUnfinishedLetterIsNotSaved:
    """"LLM generated" is not the same as "finished".

    The writer ranks drafts on hard guardrails; a missing or empty section
    is only a voice slip, so a draft with nothing under "still growing" can
    still be the best one on offer and still be shipped. Shipping it is
    fine - the parent sees a letter - but it must not become the one letter
    this child ever gets.
    """

    @pytest.mark.parametrize(
        "missing",
        [
            pytest.param({"opening": {"headline": "", "paragraph": "p"}},
                         id="no headline"),
            pytest.param({"opening": {"headline": "h", "paragraph": ""}},
                         id="no opening paragraph"),
            pytest.param({"closing": ""}, id="no closing"),
            pytest.param({"for_the_conference": {"items": []}},
                         id="empty conference section"),
            pytest.param({"what_i_noticed": []}, id="nothing noticed"),
            pytest.param({"still_growing": []}, id="no growth edge written"),
        ],
    )
    async def test_an_incomplete_letter_is_returned_but_not_saved(
        self, client, seed_user, mock_firebase_client, snapshot_stubs, missing
    ):
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=["logic"])
        write.return_value = _letter(llm_generated=True, **missing)

        r = await _generate(client)

        assert r.status_code == 200
        assert not _cached(mock_firebase_client)

    async def test_an_empty_section_the_evidence_never_found_is_fine(
        self, client, seed_user, mock_firebase_client, snapshot_stubs
    ):
        """A child with no growth edges has nothing to put under that heading.

        Demanding one would mean this child's letter never saves, which is
        the same bug wearing the opposite coat.
        """
        build, write = snapshot_stubs
        build.return_value = _evidence(
            tests_completed=["logic"], strengths=1, growth_edges=0,
        )
        write.return_value = _letter(llm_generated=True, still_growing=[])

        await _generate(client)

        assert _cached(mock_firebase_client)


class TestTheGateStillHolds:
    """Unlocking a letter is the one thing the cache must never do."""

    async def test_an_unpaid_child_gets_no_letter(
        self, client, seed_user, snapshot_stubs
    ):
        build, write = snapshot_stubs
        r = await client.post(
            "/snapshot/",
            json={"idToken": "test-token", "child_id": "child-unpaid",
                  "grade": "First"},
        )
        assert r.status_code == 402
        assert write.call_count == 0

    async def test_a_child_that_does_not_exist_gets_no_letter(
        self, client, seed_user, snapshot_stubs
    ):
        build, write = snapshot_stubs
        r = await client.post(
            "/snapshot/",
            json={"idToken": "test-token", "child_id": "no-such-child",
                  "grade": "First"},
        )
        assert r.status_code == 404
        assert write.call_count == 0

    async def test_another_parents_cached_letter_is_never_served(
        self, client, seed_user, mock_firebase_client, snapshot_stubs
    ):
        """The cache is read under the caller's own uid, not the child id."""
        from app.infrastructure.repositories import SnapshotRepository

        SnapshotRepository(mock_firebase_client).save(
            "someone-else", "child-1",
            {"success": True, "snapshot": _letter(llm_generated=True),
             "child_name": "Not Theirs"},
        )
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=["logic"])
        write.return_value = _letter(llm_generated=True)

        r = await _generate(client)

        assert r.json()["child_name"] == "Test Child"
        assert write.call_count == 1


class TestACorruptedCacheIsNotTrusted:
    """Whatever is already in the database has to be read defensively.

    Letters were saved before any of these checks existed, and a half-written
    or legacy record must send the parent to a fresh letter rather than
    through an attribute error.
    """

    @pytest.mark.parametrize(
        "cached",
        [
            pytest.param({"success": True}, id="no snapshot key"),
            pytest.param({"success": True, "snapshot": None}, id="snapshot is null"),
            pytest.param({"success": True, "snapshot": "a letter"}, id="snapshot is a string"),
            pytest.param({"success": True, "snapshot": {}}, id="snapshot is empty"),
            pytest.param({"success": True, "snapshot": {"opening": {}}}, id="no meta"),
            pytest.param({"success": True, "snapshot": {"meta": None}}, id="meta is null"),
            pytest.param({"success": True, "snapshot": {"meta": {}}}, id="meta is empty"),
        ],
    )
    async def test_an_unreadable_cached_letter_is_regenerated(
        self, client, seed_user, mock_firebase_client, snapshot_stubs, cached
    ):
        from app.infrastructure.repositories import SnapshotRepository

        SnapshotRepository(mock_firebase_client).save("test-uid", "child-1", cached)
        build, write = snapshot_stubs
        build.return_value = _evidence(tests_completed=["logic"])
        write.return_value = _letter(llm_generated=True)

        r = await _generate(client)

        assert r.status_code == 200
        assert write.call_count == 1
        assert r.json()["snapshot"]["meta"]["llm_generated"] is True
