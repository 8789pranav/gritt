"""End-to-end API tests for the two complete_result endpoints.

The engine-level tests prove the tag logic. These drive the real HTTP routes -
submit a test, then read it back through ``/complete_result/`` - so that the
fixes are verified through the payload a parent and a teacher actually receive,
including the storage round-trip in between.
"""

from __future__ import annotations

import pytest

from app.domain.enums import Grade, WordType
from app.engines.registry import logic_engine, spelling_engine

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _spelling_payload(grade: str, attempts: dict, time: float = 10.0):
    """Build a submit_words payload, defaulting every unlisted word to correct."""
    engine = spelling_engine()
    words = engine.get_items(Grade(grade))
    return {
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": grade,
        "words": [
            {
                "word": w.word,
                "user_input": attempts.get(w.word, w.word),
                "type": w.word_type.value,
                "time": time,
                "hints_used": 0,
            }
            for w in words
        ],
    }


def _logic_payload(grade: str, wrong=(), times=None, attempts=1):
    engine = logic_engine()
    items = engine.get_items(Grade(grade))
    return {
        "idToken": "test-token",
        "child_id": "child-1",
        "grade": grade,
        "responses": [
            {
                "item_id": i.item_id,
                "selected_answer_index": (
                    (i.correct_answer_index + 1) % len(i.options)
                    if i.item_id in wrong
                    else i.correct_answer_index
                ),
                "response_time_seconds": (times or {}).get(i.item_id, 10.0),
                "attempts": attempts,
                "self_corrected": False,
            }
            for i in items
        ],
    }


async def _spelling_round_trip(client, grade, attempts, time=10.0):
    submit = await client.post(
        "/submit_words/", json=_spelling_payload(grade, attempts, time)
    )
    assert submit.status_code == 200, submit.text
    result = await client.post(
        "/complete_result/",
        json={"idToken": "test-token", "child_id": "child-1", "grade": grade},
    )
    assert result.status_code == 200, result.text
    return submit.json(), result.json()


async def _logic_round_trip(client, grade, wrong=(), times=None, attempts=1):
    submit = await client.post(
        "/logic/submit_test/", json=_logic_payload(grade, wrong, times, attempts)
    )
    assert submit.status_code == 200, submit.text
    result = await client.post(
        "/logic/complete_result/",
        json={"idToken": "test-token", "child_id": "child-1", "grade": grade},
    )
    assert result.status_code == 200, result.text
    return submit.json(), result.json()


# ===========================================================================
# SPELLING
# ===========================================================================
class TestSpellingCompleteResult:
    async def test_75_convention_errors_reach_the_parent(
        self, client, mock_firebase_auth, seed_user
    ):
        """#75: the child who hears every sound but knows no spelling rules."""
        _, data = await _spelling_round_trip(
            client,
            "Second",
            {
                "graph": "graff",
                "phone": "fone",
                "standstill": "standstil",
                "said": "sed",
                "what": "wat",
            },
        )
        summary = data["parent_summary"]
        tags = {t["tag"] for t in data["dear_parent_tags"]}

        assert "spelling_convention_emerging" in tags
        assert "Spelling conventions" in summary["focus_areas"]
        # The report can no longer be strengths-only.
        assert any(
            t["polarity"] == "growth_edge" for t in data["dear_parent_tags"]
        )

    async def test_phonics_score_ignores_convention_errors(
        self, client, mock_firebase_auth, seed_user
    ):
        """Resolved decision: graff/fone/standstil are phonetically perfect."""
        _, data = await _spelling_round_trip(
            client,
            "Second",
            {"graph": "graff", "phone": "fone", "standstill": "standstil"},
        )
        assert data["parent_summary"]["phonics_score"] == 100

    async def test_genuine_phonics_errors_still_lower_the_score(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _spelling_round_trip(
            client, "Third", {"hamburger": "hambuger", "turnstile": "turnstil"}
        )
        assert data["parent_summary"]["phonics_score"] < 100

    async def test_73_dropped_letters_appear_in_per_word_tags(
        self, client, mock_firebase_auth, seed_user
    ):
        submit, data = await _spelling_round_trip(client, "First", {"home": "hom"})
        rows = {r["word"]: r for r in data["teacher_admin_detail"]["table_data"]}
        assert rows["home"]["correct"] is False
        assert rows["home"]["error_type"] == "Long vowel"

        home_id = next(
            r["item_id"] for r in submit["results"] if r["label"] == "home"
        )
        home_tags = next(
            p["tags"] for p in data["per_word_tags"] if p["item_id"] == home_id
        )
        assert "long_vowel_error" in home_tags, home_tags
        assert "long_vowel_correct" not in home_tags
        assert "spelling_convention_error" not in home_tags

    async def test_54_unanswered_word_shows_not_answered(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _spelling_round_trip(client, "First", {"chat": ""})
        rows = {r["word"]: r for r in data["teacher_admin_detail"]["table_data"]}
        assert rows["chat"]["icon"] == "Not answered"
        assert rows["chat"]["error_type"] is None

    async def test_54_blank_word_has_no_per_word_tags(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _spelling_round_trip(client, "First", {"chat": ""})
        blank = [p for p in data["per_word_tags"] if p["answered"] is False]
        assert blank
        assert all(not p["tags"] for p in blank)

    async def test_61_rushed_never_hides_a_better_error_type(
        self, client, mock_firebase_auth, seed_user
    ):
        """A fast convention error must read as Spelling convention, not Rushed."""
        _, data = await _spelling_round_trip(
            client, "Second", {"graph": "graff"}, time=1.0
        )
        rows = {r["word"]: r for r in data["teacher_admin_detail"]["table_data"]}
        assert rows["graph"]["error_type"] == "Spelling convention"

    async def test_63_added_letter_reads_as_a_convention_error(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _spelling_round_trip(client, "Second", {"clunk": "clunck"})
        rows = {r["word"]: r for r in data["teacher_admin_detail"]["table_data"]}
        assert rows["clunk"]["error_type"] == "Spelling convention"

    async def test_70_sight_words_reach_focus_areas(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _spelling_round_trip(
            client, "Second", {"does": "dose", "said": "zzz", "what": "qqq"}
        )
        assert "Sight words" in data["parent_summary"]["focus_areas"]

    async def test_every_emitted_tag_has_parent_copy(
        self, client, mock_firebase_auth, seed_user
    ):
        from app.services.report_service import ReportService

        _, data = await _spelling_round_trip(
            client, "Second", {"graph": "graff", "said": "sed", "what": "wat"}
        )
        for tag in data["dear_parent_tags"]:
            assert tag["tag"] in ReportService._TAG_SENTENCE_MAP, tag["tag"]

    # -- edge cases ---------------------------------------------------------
    @pytest.mark.parametrize(
        "grade", ["Kindergarten", "First", "Second", "Third"]
    )
    async def test_perfect_run_every_grade(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        _, data = await _spelling_round_trip(client, grade, {})
        summary = data["parent_summary"]
        assert summary["overall_accuracy"] == 100
        assert summary["phonics_score"] == 100
        assert summary["sight_word_score"] == 100
        assert not summary["focus_areas"]
        assert all(
            t["polarity"] != "growth_edge" for t in data["dear_parent_tags"]
        )

    @pytest.mark.parametrize(
        "grade", ["Kindergarten", "First", "Second", "Third"]
    )
    async def test_every_word_blank(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        engine = spelling_engine()
        blanks = {w.word: "" for w in engine.get_items(Grade(grade))}
        _, data = await _spelling_round_trip(client, grade, blanks)
        summary = data["parent_summary"]
        assert summary["overall_accuracy"] == 0
        rows = data["teacher_admin_detail"]["table_data"]
        assert all(r["icon"] == "Not answered" for r in rows)
        assert all(r["error_type"] is None for r in rows)
        assert all(not p["tags"] for p in data["per_word_tags"])

    @pytest.mark.parametrize(
        "grade", ["Kindergarten", "First", "Second", "Third"]
    )
    async def test_every_word_wrong(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        engine = spelling_engine()
        junk = {w.word: "zzqq" for w in engine.get_items(Grade(grade))}
        _, data = await _spelling_round_trip(client, grade, junk)
        assert data["parent_summary"]["overall_accuracy"] == 0
        rows = data["teacher_admin_detail"]["table_data"]
        assert all(r["icon"] == "Incorrect" for r in rows)
        # Every wrong answer must carry an explanation.
        assert all(r["error_type"] for r in rows), [
            r for r in rows if not r["error_type"]
        ]

    async def test_payload_shape_is_complete(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _spelling_round_trip(client, "Third", {})
        for key in (
            "parent_summary",
            "dear_parent_tags",
            "per_word_tags",
            "teacher_admin_detail",
        ):
            assert key in data, key
        for key in (
            "overall_accuracy",
            "phonics_score",
            "sight_word_score",
            "confidence",
            "strengths",
            "focus_areas",
            "recommendation",
        ):
            assert key in data["parent_summary"], key

    async def test_missing_result_is_a_clean_error(
        self, client, mock_firebase_auth, seed_user
    ):
        resp = await client.post(
            "/complete_result/",
            json={
                "idToken": "test-token",
                "child_id": "child-1",
                "grade": "Third",
            },
        )
        assert resp.status_code in (404, 400), resp.status_code


# ===========================================================================
# LOGIC
# ===========================================================================
class TestLogicCompleteResult:
    @pytest.mark.parametrize("grade", ["First", "Second", "Third"])
    async def test_g5_perfect_run_reports_pattern_strong(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        _, data = await _logic_round_trip(client, grade)
        tags = {t["tag"] for t in data["dear_parent_tags"]}
        assert "pattern_detection_strong" in tags
        assert "pattern_detection_emerging" not in tags

    @pytest.mark.parametrize("grade", ["First", "Second", "Third"])
    async def test_cap_perfect_run_carries_every_strength(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        """More than three tags must survive to the parent payload."""
        _, data = await _logic_round_trip(client, grade)
        assert len(data["dear_parent_tags"]) >= 5, data["dear_parent_tags"]
        assert len(data["parent_summary"]["strengths"]) >= 5

    async def test_ld7_perfect_run_has_no_growth_edge(
        self, client, mock_firebase_auth, seed_user
    ):
        """A Grade 2 child who got both load items right was told it was a gap."""
        _, data = await _logic_round_trip(client, "Second")
        tags = {t["tag"] for t in data["dear_parent_tags"]}
        assert "reasoning_under_load" in tags
        assert "reasoning_under_load_emerging" not in tags
        assert not data["parent_summary"]["focus_areas"]

    async def test_ld7_both_load_items_wrong_is_a_growth_edge(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _logic_round_trip(
            client, "Second", wrong={"logic_2_3", "logic_2_7"}
        )
        tags = {t["tag"] for t in data["dear_parent_tags"]}
        assert "reasoning_under_load_emerging" in tags
        assert "reasoning_under_load" not in tags
        assert data["parent_summary"]["focus_areas"]

    async def test_ld1_teacher_table_carries_time_and_indices(
        self, client, mock_firebase_auth, seed_user
    ):
        """Every row read null / null / 0.0 before the key names were fixed."""
        times = {f"logic_3_{i}": float(i + 4) for i in range(1, 9)}
        _, data = await _logic_round_trip(
            client, "Third", wrong={"logic_3_3"}, times=times
        )
        rows = data["teacher_admin_detail"]["table_data"]
        assert rows
        for row in rows:
            assert row["selected_index"] is not None, row
            assert row["correct_index"] is not None, row
            assert row["time"] > 0, row

    async def test_ld1_submit_path_also_carries_them(
        self, client, mock_firebase_auth, seed_user
    ):
        submit, _ = await _logic_round_trip(client, "Third", wrong={"logic_3_3"})
        for row in submit["teacher_admin_detail"]["table_data"]:
            assert row["selected_index"] is not None, row
            assert row["correct_index"] is not None, row
            assert row["time"] > 0, row

    async def test_ld1_selected_and_correct_differ_on_a_wrong_answer(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _logic_round_trip(client, "Third", wrong={"logic_3_3"})
        wrong_rows = [
            r for r in data["teacher_admin_detail"]["table_data"] if not r["correct"]
        ]
        assert wrong_rows
        for row in wrong_rows:
            assert row["selected_index"] != row["correct_index"]

    async def test_g1_fast_wrong_answers_reach_the_payload(
        self, client, mock_firebase_auth, seed_user
    ):
        times = {f"logic_3_{i}": 10.0 for i in range(1, 9)}
        times.update({"logic_3_3": 1.0, "logic_3_4": 1.0})
        _, data = await _logic_round_trip(
            client, "Third", wrong={"logic_3_3", "logic_3_4"}, times=times
        )
        tags = {t["tag"] for t in data["dear_parent_tags"]}
        assert "impulsive_response" in tags
        rows = {
            r["question"]: r for r in data["teacher_admin_detail"]["table_data"]
        }
        assert any(r["error_type"] == "Impulsive response" for r in rows.values())

    async def test_ln1_missed_skills_reach_the_parent(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _logic_round_trip(
            client, "Third", wrong={"logic_3_4", "logic_3_8"}
        )
        tags = {t["tag"] for t in data["dear_parent_tags"]}
        assert "systematic_problem_solving_emerging" in tags
        assert "flexible_strategy_emerging" in tags
        assert data["parent_summary"]["focus_areas"]

    async def test_lb3_load_error_type_still_resolves(
        self, client, mock_firebase_auth, seed_user
    ):
        """The item tag was renamed; the teacher table must still label it."""
        engine = logic_engine()
        item = next(
            i for i in engine.get_items(Grade.SECOND) if i.item_id == "logic_2_3"
        )
        slow = (item.expected_latency_seconds or 30) * 3
        _, data = await _logic_round_trip(
            client, "Second", wrong={"logic_2_3"}, times={"logic_2_3": slow}
        )
        rows = data["teacher_admin_detail"]["table_data"]
        assert any(r["error_type"] == "Reasoning under load" for r in rows), rows

    async def test_every_emitted_tag_has_parent_copy(
        self, client, mock_firebase_auth, seed_user
    ):
        from app.services.report_service import ReportService

        _, data = await _logic_round_trip(
            client, "Third", wrong={"logic_3_4", "logic_3_8"}
        )
        for tag in data["dear_parent_tags"]:
            assert tag["tag"] in ReportService._TAG_SENTENCE_MAP, tag["tag"]

    async def test_ld5_dead_signals_are_absent_from_the_payload(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _logic_round_trip(client, "Third")
        assert "shift_result" not in data["signals"]
        assert "rule_inferred" not in data["signals"]
        tags = {t["tag"] for t in data["dear_parent_tags"]}
        assert "cognitive_flexibility_intact" not in tags
        assert "strategy_shift_difficulty" not in tags

    async def test_ld6_evidence_never_cites_rule_inferred(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _logic_round_trip(client, "Third")
        for tag in data["dear_parent_tags"]:
            assert "rule_inferred" not in tag.get("evidence", "")

    # -- edge cases ---------------------------------------------------------
    @pytest.mark.parametrize(
        "grade", ["Kindergarten", "First", "Second", "Third"]
    )
    async def test_every_answer_wrong(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        engine = logic_engine()
        every = {i.item_id for i in engine.get_items(Grade(grade))}
        _, data = await _logic_round_trip(client, grade, wrong=every)
        assert data["percentage"] == 0.0
        assert data["parent_summary"]["focus_areas"]
        # G2: never a growth edge with no strength shown at all.
        assert data["parent_summary"]["strengths"]
        rows = data["teacher_admin_detail"]["table_data"]
        assert all(r["error_type"] for r in rows), [
            r for r in rows if not r["error_type"]
        ]

    @pytest.mark.parametrize(
        "grade", ["Kindergarten", "First", "Second", "Third"]
    )
    async def test_perfect_run_has_no_focus_areas(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        _, data = await _logic_round_trip(client, grade)
        assert data["percentage"] == 100.0
        assert not data["parent_summary"]["focus_areas"]
        assert all(
            r["error_type"] is None
            for r in data["teacher_admin_detail"]["table_data"]
        )

    async def test_zero_response_times_do_not_flag_impulsive(
        self, client, mock_firebase_auth, seed_user
    ):
        """L-D4: never fires without timing data."""
        times = {f"logic_3_{i}": 0.0 for i in range(1, 9)}
        _, data = await _logic_round_trip(
            client, "Third", wrong={"logic_3_3", "logic_3_4"}, times=times
        )
        tags = {t["tag"] for t in data["dear_parent_tags"]}
        assert "impulsive_response" not in tags

    async def test_whole_second_times_still_work(
        self, client, mock_firebase_auth, seed_user
    ):
        """L-D4: rounded times must not break the median-relative threshold."""
        times = {f"logic_3_{i}": 12.0 for i in range(1, 9)}
        times.update({"logic_3_3": 1.0, "logic_3_4": 1.0})
        _, data = await _logic_round_trip(
            client, "Third", wrong={"logic_3_3", "logic_3_4"}, times=times
        )
        assert "impulsive_response" in {t["tag"] for t in data["dear_parent_tags"]}

    async def test_trial_and_error_survives_the_round_trip(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _logic_round_trip(client, "Second", attempts=3)
        assert "trial_and_error_strategy" in {
            t["tag"] for t in data["dear_parent_tags"]
        }

    async def test_payload_shape_is_complete(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _logic_round_trip(client, "Kindergarten")
        for key in (
            "parent_summary",
            "dear_parent_tags",
            "per_item_tags",
            "teacher_admin_detail",
            "signals",
            "scored_items",
            "timestamp",
        ):
            assert key in data, key
        assert "Test completed" not in str(data), "G6: raw score string is back"

    async def test_missing_result_is_a_clean_error(
        self, client, mock_firebase_auth, seed_user
    ):
        resp = await client.post(
            "/logic/complete_result/",
            json={
                "idToken": "test-token",
                "child_id": "child-1",
                "grade": "Third",
            },
        )
        assert resp.status_code in (404, 400), resp.status_code


# ===========================================================================
# Cross-cutting: submit and complete_result must not disagree
# ===========================================================================
class TestSubmitAndResultAgree:
    @pytest.mark.parametrize(
        "grade,wrong_id",
        [("First", "logic_1_3"), ("Second", "logic_2_3"), ("Third", "logic_3_3")],
    )
    async def test_logic_tags_match_across_both_endpoints(
        self, client, mock_firebase_auth, seed_user, grade, wrong_id
    ):
        submit, result = await _logic_round_trip(client, grade, wrong={wrong_id})
        assert {t["tag"] for t in submit["dear_parent_tags"]} == {
            t["tag"] for t in result["dear_parent_tags"]
        }

    @pytest.mark.parametrize("grade", ["First", "Second", "Third"])
    async def test_spelling_tags_match_across_both_endpoints(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        submit, result = await _spelling_round_trip(client, grade, {})
        assert {t["tag"] for t in submit["dear_parent_tags"]} == {
            t["tag"] for t in result["dear_parent_tags"]
        }

    async def test_logic_per_item_tags_match(
        self, client, mock_firebase_auth, seed_user
    ):
        submit, result = await _logic_round_trip(
            client, "Third", wrong={"logic_3_3"}
        )
        assert submit["per_item_tags"] == result["per_item_tags"]


# ===========================================================================
# Storage round-trip: Firebase stores no empty containers
# ===========================================================================
class TestFirebaseDropsEmptyContainers:
    """The Realtime Database omits empty arrays, so a stored ``tags: []``
    comes back with no ``tags`` key at all. That only bites on unanswered
    items - which is exactly what #54 was about - and the in-memory test
    double stores dicts verbatim, so it never reproduced here. These tests
    strip the key the way real storage does.
    """

    @staticmethod
    def _strip_empty(entries):
        return [
            {k: v for k, v in entry.items() if v != [] and v != {}}
            for entry in entries
        ]

    async def test_spelling_per_word_tags_survive_a_dropped_key(self):
        from app.services.assessment_service import _restore_per_item_tags

        stored = self._strip_empty([
            {"item_id": "a", "answered": False, "is_correct": None, "tags": []},
            {"item_id": "b", "answered": True, "is_correct": True,
             "tags": ["short_vowel_correct"]},
        ])
        assert "tags" not in stored[0], "test double did not reproduce the drop"

        restored = _restore_per_item_tags(stored)
        assert restored[0]["tags"] == []
        assert restored[1]["tags"] == ["short_vowel_correct"]
        assert restored[0]["answered"] is False

    async def test_restore_handles_a_missing_list_entirely(self):
        from app.services.assessment_service import _restore_per_item_tags

        assert _restore_per_item_tags(None) == []
        assert _restore_per_item_tags([]) == []

    async def test_blank_words_expose_tags_as_a_list(
        self, client, mock_firebase_auth, seed_user
    ):
        """Whatever storage does, the payload must always carry a list."""
        _, data = await _spelling_round_trip(client, "First", {"chat": ""})
        for entry in data["per_word_tags"]:
            assert isinstance(entry["tags"], list), entry

    async def test_logic_per_item_tags_expose_tags_as_a_list(
        self, client, mock_firebase_auth, seed_user
    ):
        _, data = await _logic_round_trip(client, "Third")
        for entry in data["per_item_tags"]:
            assert isinstance(entry["tags"], list), entry
