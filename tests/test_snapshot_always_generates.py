"""A parent who asks for the snapshot gets a letter about their child.

Two things used to stand between a paid parent and their letter, and both
ended the same way: the generic fallback, which is warm, correct, and about
nobody.

* one raised call inside the writer's retry loop abandoned the whole loop,
  so a single network blip cost the letter - along with any good draft
  already in hand;
* the evidence fetch filtered results by the grade on the request, so a
  child whose profile grade had moved on since the day they were assessed
  produced no evidence at all, and no evidence is no letter.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import PropertyMock, patch

import pytest

from app.services.snapshot_service import SnapshotService
from app.services.snapshot_writer import SnapshotWriter

CHILD = "users/test-uid/children/child-1"


def _draft() -> Dict[str, Any]:
    return {
        "opening": {"headline": "h", "paragraph": "p"},
        "what_i_noticed": [],
        "still_growing": [],
        "for_the_conference": {"items": []},
        "closing": "c",
    }


def _signal(name: str, polarity: str) -> Dict[str, Any]:
    """One fired tag, shaped as Stage A hands it to the writer."""
    return {
        "tag": name,
        "signal_name": name,
        "polarity": polarity,
        "confidence": "medium",
        "description": "",
        "seen_in": "Word Wizard",
        "activity": "spelling",
        "questions_behind": 3,
        "badge": "seen_repeatedly",
        "measurements": {},
        "area": "patterns",
        "area_display_name": "Patterns & Structure",
    }


def _evidence() -> Dict[str, Any]:
    return {
        "child_name": "Sadie",
        "pronouns": {"key": "she", "object": "her", "known": True},
        "tests_completed": ["logic", "spelling"],
        "growth_edges": [],
        "strengths": [],
        "session": {},
    }


@pytest.fixture
def writer_stubs():
    """Let the loop run for real; only the model call and the rules are fake."""
    with patch.object(
        SnapshotWriter, "is_configured", new_callable=PropertyMock,
        return_value=True,
    ), patch.object(
        SnapshotWriter, "_validate", return_value=[],
    ), patch(
        "app.services.snapshot_writer._repair", side_effect=lambda l, e: l,
    ), patch(
        "app.services.snapshot_writer.specificity", return_value=99,
    ):
        yield


class TestATransientErrorDoesNotCostTheLetter:
    def test_a_failed_attempt_is_retried(self, writer_stubs):
        """The blip that hit one paid parent in production."""
        with patch.object(
            SnapshotWriter, "_generate",
            side_effect=[RuntimeError("connection reset"), _draft()],
        ) as generate, patch("app.services.snapshot_writer.time.sleep"):
            letter = SnapshotWriter().write(_evidence())

        assert generate.call_count == 2
        assert letter["meta"]["llm_generated"] is True

    def test_the_api_is_retried_three_times_before_giving_up(self, writer_stubs):
        """Three tries, not one, when the model keeps failing."""
        with patch.object(
            SnapshotWriter, "_generate", side_effect=RuntimeError("down"),
        ) as generate, patch("app.services.snapshot_writer.time.sleep"):
            letter = SnapshotWriter().write(_evidence())

        assert generate.call_count == 3
        assert letter["meta"]["llm_generated"] is False

    def test_a_failed_call_does_not_spend_a_drafting_attempt(self, writer_stubs):
        """The budgets are separate.

        A dropped connection is not a draft. While it shared the drafting
        budget, one blip left the writer a single try to get the letter
        right, and the retry prompt - which is what actually fixes a broken
        draft - never got used.
        """
        drafts = [_draft() for _ in range(3)]
        with patch(
            "app.services.snapshot_writer.specificity", return_value=0,
        ), patch.object(
            SnapshotWriter, "_generate",
            side_effect=[RuntimeError("reset"), drafts[0],
                         RuntimeError("reset"), drafts[1], drafts[2]],
        ) as generate, patch("app.services.snapshot_writer.time.sleep"):
            SnapshotWriter().write(_evidence())

        # 3 drafts still reached the guardrails, despite 2 failed calls.
        assert generate.call_count == 5

    def test_a_retry_waits_before_trying_again(self, writer_stubs):
        """A rate limit needs a pause, not an immediate second ask."""
        with patch.object(
            SnapshotWriter, "_generate", side_effect=RuntimeError("429"),
        ), patch("app.services.snapshot_writer.time.sleep") as sleep:
            SnapshotWriter().write(_evidence())

        # Backs off between tries, and never after the last one.
        assert [c.args[0] for c in sleep.call_args_list] == [1.0, 2.0]

    def test_a_late_failure_does_not_discard_a_good_draft(self, writer_stubs):
        """A draft already in hand survives a blip on a later attempt."""
        with patch(
            "app.services.snapshot_writer.specificity", return_value=0,
        ), patch(
            "app.services.snapshot_writer.time.sleep",
        ), patch.object(
            SnapshotWriter, "_generate",
            side_effect=[_draft(), RuntimeError("boom"), RuntimeError("boom"),
                         RuntimeError("boom")],
        ):
            letter = SnapshotWriter().write(_evidence())

        assert letter["meta"]["llm_generated"] is True


class TestTheGradeOnTheRequestDoesNotHideTheResults:
    """Sadie's profile said Third; all four of her results said Second."""

    @pytest.fixture
    def child_assessed_at_second(self, mock_firebase_client, seed_user):
        mock_firebase_client.ref(CHILD).set(
            {"name": "Sadie", "age": 8, "grade": "Third",
             "payment_status": "paid"}
        )
        for collection in ("scores", "logic_tests", "speaking_tests",
                           "comprehension_tests"):
            mock_firebase_client.ref(f"{CHILD}/{collection}/r1").set(
                {"grade": "Second", "timestamp": "2026-09-16T22:19:13+00:00",
                 "dear_parent_tags": []}
            )
        return mock_firebase_client.ref(CHILD).get()

    def _build(self, child, grade):
        return SnapshotService().build_evidence(
            "", "child-1", grade, uid="test-uid", child_data=child
        )

    def test_a_grade_with_no_results_still_finds_the_childs_work(
        self, child_assessed_at_second
    ):
        evidence = self._build(child_assessed_at_second, "Third")
        assert sorted(evidence["tests_completed"]) == [
            "comprehension", "logic", "speaking", "spelling",
        ]

    def test_the_matching_grade_is_still_preferred(
        self, child_assessed_at_second, mock_firebase_client
    ):
        """The fallback only fills a gap; it never overrides a real match."""
        mock_firebase_client.ref(f"{CHILD}/scores/r2").set(
            {"grade": "Third", "timestamp": "2026-09-17T10:00:00+00:00",
             "dear_parent_tags": [], "marker": "third-grade-run"}
        )
        child = mock_firebase_client.ref(CHILD).get()
        evidence = self._build(child, "Third")

        assert "spelling" in evidence["tests_completed"]


class TestEveryObservationReachesTheParent:
    """The section had a ceiling of four and no floor at all.

    A letter went out with two items while a third observation sat unused in
    the evidence, so a parent was told less than the run had actually found.
    The floor is what the evidence supports, never a fixed four: a fourth
    item for a child with three observations could only be invented.
    """

    def _evidence_with(self, strengths=0, neutral=0, flawless=0):
        evidence = _evidence()
        evidence["strengths"] = [
            _signal(f"s{i}", "strength") for i in range(strengths)
        ]
        evidence["neutral_observations"] = [
            _signal(f"n{i}", "neutral") for i in range(neutral)
        ]
        evidence["flawless_activities"] = [
            {"activity": f"f{i}"} for i in range(flawless)
        ]
        return evidence

    def _noticed_violation(self, items, **material):
        letter = dict(_draft(), what_i_noticed=[{"headline": f"h{i}"}
                                                for i in range(items)])
        violations = SnapshotWriter()._validate(
            letter, self._evidence_with(**material)
        )
        return [v for v in violations if "what_i_noticed has" in v]

    def test_two_items_against_three_observations_is_rejected(self):
        """Exactly the letter that went out: 2 written, 3 available."""
        assert self._noticed_violation(2, strengths=2, neutral=1)

    def test_neutral_observations_and_flawless_runs_count_as_material(self):
        """All three lists feed the section, not just strengths."""
        assert self._noticed_violation(1, strengths=1, neutral=1, flawless=1)

    def test_the_floor_never_exceeds_the_evidence(self):
        """Three observations means three items, not a made-up fourth."""
        assert not self._noticed_violation(3, strengths=2, neutral=1)

    def test_the_section_still_stops_at_four(self):
        """A child with plenty of evidence does not get a sprawling page."""
        assert not self._noticed_violation(4, strengths=10)
        over = SnapshotWriter()._validate(
            dict(_draft(), what_i_noticed=[{"headline": f"h{i}"} for i in range(5)]),
            self._evidence_with(strengths=10),
        )
        assert any("more than 4 items" in v for v in over)

    def test_a_short_section_never_costs_the_parent_the_letter(self):
        """It is a voice slip, not a guardrail.

        A hard failure here would mean no draft was ever eligible, the
        parent would get the generic letter, and - because a failure is
        never saved - it would regenerate for ever.
        """
        from app.services.snapshot_writer import _STYLE_PREFIX

        assert all(v.startswith(_STYLE_PREFIX)
                   for v in self._noticed_violation(2, strengths=2, neutral=1))


class TestTheEvidenceStageNeverCrashes:
    """A 500 is the one outcome worse than a thin letter.

    Stage A is not wrapped in anything: an exception here escapes the
    endpoint, so the parent gets an error page rather than a letter. Two
    shapes of real production data did exactly that, and neither is
    recoverable by pressing the button again.
    """

    def test_measurements_stored_as_a_mapping_do_not_crash(self):
        """One child's tags carried a dict where a string was assumed."""
        from app.services.snapshot_service import _parse_evidence

        assert _parse_evidence({"pattern_items_count": 3}) == {
            "pattern_items_count": 3
        }

    @pytest.mark.parametrize("value", [None, 7, ["a=1"]])
    def test_measurements_of_any_other_shape_are_read_as_none(self, value):
        from app.services.snapshot_service import _parse_evidence

        assert _parse_evidence(value) == {}

    def test_the_string_form_still_parses(self):
        from app.services.snapshot_service import _parse_evidence

        assert _parse_evidence("pattern_accuracy=1.0, pattern_items_count=3") == {
            "pattern_accuracy": 1.0,
            "pattern_items_count": 3,
        }

    def test_old_results_without_a_timezone_do_not_crash(self):
        """Results written before the timestamps carried a zone.

        A child with one old result and one new one used to bring the whole
        letter down on the subtraction that measures the sitting.
        """
        service = SnapshotService()
        facts = service._session_facts(
            {
                "spelling": {"timestamp": "2025-11-10T16:16:47.953140"},
                "logic": {"timestamp": "2026-09-16T17:54:15.688551+00:00"},
            },
            {"spelling": "Word Wizard", "logic": "Logic Quest"},
        )

        assert facts["span_minutes"] > 0
        assert facts["same_sitting"] is False


class TestAThinRunStillGetsARealLetter:
    """A child can finish all four activities and produce almost nothing.

    One did: no strength, no neutral observation, one clean activity and one
    growth edge - two things in total. Three separate rules each demanded
    more than that existed, so no draft was ever eligible, every press
    returned the generic letter, and because a failure is never saved it
    regenerated for ever at six model calls a time.
    """

    def _thin(self):
        evidence = _evidence()
        evidence["strengths"] = []
        evidence["neutral_observations"] = []
        evidence["flawless_activities"] = [
            {"activity": "Word Wizard",
             "nothing_to_fault": "every word spelled correctly"}
        ]
        evidence["growth_edges"] = [_signal("Working out a new word", "growth_edge")]
        evidence["growth_clusters"] = [{"area_display_name": "Reasoning",
                                        "seen_in": ["Story Explorer"],
                                        "signals": ["Working out a new word"]}]
        return evidence

    def test_the_conference_floor_drops_to_what_the_run_found(self):
        """Two things found means two items, not an impossible four."""
        evidence = self._thin()
        letter = dict(_draft(), for_the_conference={"items": [
            {"point": "p1", "worth_asking": "q1", "about": "strength"},
            {"point": "p2", "worth_asking": "q2", "about": "still_growing"},
        ]})
        violations = SnapshotWriter()._validate(letter, evidence)
        assert not [v for v in violations if "for_the_conference must hold" in v]

    def test_a_full_run_still_owes_the_parent_four(self):
        """The floor only drops for a child who has less; it is not removed."""
        evidence = _evidence()
        evidence["strengths"] = [_signal(f"s{i}", "strength") for i in range(6)]
        letter = dict(_draft(), for_the_conference={"items": [
            {"point": "p1", "worth_asking": "q1", "about": "strength"},
            {"point": "p2", "worth_asking": "q2", "about": "still_growing"},
        ]})
        violations = SnapshotWriter()._validate(letter, evidence)
        assert [v for v in violations if "for_the_conference must hold" in v]

    def test_a_flawless_activity_may_be_named(self):
        """It fires no tag, so it appeared in none of the signal lists.

        Naming it read as naming an activity that never happened, which made
        the one honest item unwritable for a child whose only good news was
        a clean run.
        """
        evidence = self._thin()
        letter = dict(_draft(), what_i_noticed=[
            {"headline": "Every word came out right.",
             "seen_in": ["Word Wizard"], "paragraph": "x"}
        ])
        violations = SnapshotWriter()._validate(letter, evidence)
        assert not [v for v in violations if "unknown activity" in v]

    def test_an_activity_the_child_never_touched_is_still_caught(self):
        """The rule still does its job: this one is genuinely unearned."""
        evidence = self._thin()
        letter = dict(_draft(), what_i_noticed=[
            {"headline": "h", "seen_in": ["Logic Quest"], "paragraph": "x"}
        ])
        violations = SnapshotWriter()._validate(letter, evidence)
        assert [v for v in violations if "unknown activity" in v]
