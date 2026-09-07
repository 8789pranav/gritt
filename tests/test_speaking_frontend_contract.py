"""The response fields the dpp-main report actually dereferences.

The Azure cutover changed the speaking response shape, and eight fields the
TestResults component reads went missing: fluency.score (the chain emitted
fluency_score), grammar.score, every *.feedback string, and overall.strengths,
areas_to_improve and parent_tip. overall.level came back as an empty string,
so every row rendered as "Not Attempted".

None of that raises on either side. The report just renders blanks. These
tests fail instead.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

#: path -> what the report uses it for
RESULT_FIELDS = {
    "status": "filter for Answered",
    "original_sentence": "table: word column",
    "transcribed_text": "table: attempt column",
    "overall.score": "table score, and the >= 85 correct test",
    "overall.level": "table: level column",
    "overall.strengths": "aggregated strengths list",
    "overall.areas_to_improve": "aggregated focus list",
    "overall.parent_tip": "per-row tip",
    "pronunciation.score": "score breakdown",
    "pronunciation.feedback": "expandable row",
    "fluency.score": "score breakdown",
    "fluency.feedback": "expandable row",
    "grammar.score": "score breakdown",
    "grammar.feedback": "expandable row",
}

TOP_FIELDS = {
    "all_results", "total_marks", "user_score", "answered_count",
    "average_score", "level", "dear_parent_tags", "per_sentence_tags",
    "parent_summary",
}


def dig(obj, path):
    node = obj
    for part in path.split("."):
        assert isinstance(node, dict), f"{path}: {part} is not on a dict"
        assert part in node, f"missing: {path}"
        node = node[part]
    return node


async def _run(client, grade="Kindergarten"):
    from app.domain.enums import Grade
    from app.engines.registry import speaking_engine

    sentences = speaking_engine().get_items(Grade(grade))
    subs = [
        {"sentence_id": s.sentence_id, "original_sentence": s.sentence,
         "audio_base64": "cmVjb3JkaW5n", "audio_format": "wav",
         "time_to_speak_ms": 700, "attempt": 1}
        for s in sentences
    ]
    submit = await client.post("/speaking/submit/", json={
        "idToken": "test-token", "child_id": "child-1",
        "grade": grade, "submissions": subs})
    assert submit.status_code == 200, submit.text
    result = await client.post("/speaking/complete_result/", json={
        "idToken": "test-token", "child_id": "child-1", "grade": grade})
    assert result.status_code == 200, result.text
    return submit.json(), result.json()


class TestReportContract:
    @pytest.mark.parametrize("path", sorted(TOP_FIELDS))
    async def test_top_level_field(
        self, client, mock_firebase_auth, seed_user, mock_speech, path
    ):
        _, data = await _run(client)
        assert path in data, f"the report reads {path!r}"

    @pytest.mark.parametrize("path", sorted(RESULT_FIELDS))
    async def test_per_result_field(
        self, client, mock_firebase_auth, seed_user, mock_speech, path
    ):
        _, data = await _run(client)
        rows = data["all_results"]
        assert rows, "no rows to check"
        for row in rows:
            dig(row, path)

    async def test_submit_and_result_agree_on_the_shape(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        submit, result = await _run(client)
        assert {r["sentence_id"] for r in submit["results"]} == {
            r["sentence_id"] for r in result["all_results"]}

    async def test_status_values_are_the_ones_the_report_filters_on(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        allowed = {"Answered", "Not Attempted", "Needs Review"}
        for row in data["all_results"]:
            assert row["status"] in allowed, row["status"]

    async def test_level_is_never_blank(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        """An empty level rendered every row as Not Attempted."""
        _, data = await _run(client)
        for row in data["all_results"]:
            assert row["overall"]["level"], row["sentence_id"]

    async def test_feedback_is_never_blank(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        for row in data["all_results"]:
            for dim in ("pronunciation", "fluency", "grammar"):
                assert row[dim]["feedback"], f"{row['sentence_id']}.{dim}"


class TestFeedbackIsTrue:
    """Feedback is generated from measurements, so it must not describe a
    reading that did not happen."""

    def _measured(self, status, **over):
        base = {
            "status": status,
            "scores": {"accuracy": 0.0, "fluency": 0.0, "completeness": 0.0,
                       "prosody": 0.0, "pron_score": 0.0},
            "reading": {"wcpm": 0.0, "rate_band": "no_reading"},
            "timing": {"pause_count": 0, "long_pause_count": 0},
            "disfluency": {"filler_count": 0, "repetitions": 0},
            "errors": {}, "findings": [], "words": [],
        }
        base.update(over)
        return base

    @pytest.mark.parametrize("status", ["not_attempted", "needs_review"])
    async def test_an_unscored_sentence_is_not_praised(self, status):
        from app.engines.speaking.feedback import build

        fb = build(self._measured(status))
        blob = " ".join(str(v) for v in fb.values()).lower()
        for praise in ("smoothly", "clearly", "natural expression",
                       "nothing skipped"):
            assert praise not in blob, f"{status} was praised: {praise}"
        assert fb["strengths"] == []
        assert fb["areas_to_improve"] == []

    async def test_a_needs_review_sentence_says_why(self):
        from app.engines.speaking.feedback import build

        fb = build(self._measured("needs_review"))
        assert "not been scored" in fb["pronunciation_feedback"]

    async def test_a_substituted_sound_is_named_in_the_feedback(self):
        from app.engines.speaking.feedback import build

        measured = self._measured(
            "answered",
            words=[{"word": "dog"}],
            findings=[{
                "word": "dog", "flags": ["clear_error", "sound_substituted"],
                "substitutions": [{"expected": "g", "said": "t",
                                   "accuracy": 0.0}],
            }],
            errors={"clear_error": 1},
        )
        fb = build(measured)
        assert "/g/" in fb["pronunciation_feedback"]
        assert "/t/" in fb["pronunciation_feedback"]
        assert "dog" in fb["parent_tip"]

    async def test_skipped_words_are_counted_not_guessed(self):
        from app.engines.speaking.feedback import build

        fb = build(self._measured("answered", words=[{"word": "a"}],
                                  errors={"omission": 3}))
        assert "3 words were skipped" in fb["completeness_feedback"]
        assert "Reading every word on the line" in fb["areas_to_improve"]
