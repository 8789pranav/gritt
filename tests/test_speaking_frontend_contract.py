"""The per-sentence result shape, and what the report reads from it.

Five things per sentence and nothing else: which sentence it is, whether it
was answered, what was actually said, every measurement, and its tags. Both
/speaking/submit/ and /speaking/complete_result/ return the same object,
built in app.engines.speaking.result, so the two cannot drift apart.

The previous shape mixed those together at the top level and repeated the same
score under three names, which is how a value ended up present in one place
and stale in another.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

#: path within one sentence -> what it is for
SENTENCE_FIELDS = {
    "sentence_id": "which sentence",
    "sentence": "the text the child was asked to read",
    "answered": "did the child attempt it",
    "status": "answered / not_attempted / needs_review",
    "reason": "why it was not scored, when it was not",

    "transcription.heard": "Azure recognition",
    "transcription.verbatim": "blind channel, keeps fillers",
    "transcription.spoken_sounds": "IPA actually produced",
    "transcription.matches_reference": "did it match the target",

    "analysis.overall.score": "headline percentage",
    "analysis.overall.level": "band name",
    "analysis.pronunciation.score": "percentage",
    "analysis.pronunciation.feedback": "one line",
    "analysis.fluency.score": "percentage",
    "analysis.fluency.feedback": "one line",
    "analysis.prosody.score": "percentage",
    "analysis.prosody.feedback": "one line",
    "analysis.completeness.score": "percentage",
    "analysis.completeness.feedback": "one line",
    "analysis.reading.wcpm": "words correct per minute",
    "analysis.timing.pause_count": "pauses",
    "analysis.disfluency.filler_count": "fillers",
    "analysis.errors.mispronounced": "counted errors",
    "analysis.phonics": "per phonics feature",
    "analysis.strengths": "list",
    "analysis.areas_to_improve": "list",
    "analysis.parent_tip": "one thing to do",

    "tags": "tags for this sentence",
}

TOP_FIELDS = {
    "sentences", "summary", "parent_summary", "dear_parent_tags", "signals",
    "grade", "child_id", "timestamp",
}

SUMMARY_FIELDS = {
    "sentences", "answered", "needs_review", "total_marks", "user_score",
    "average_score", "percentage", "level", "grade_placement",
}


def dig(obj, path):
    node = obj
    for part in path.split("."):
        assert isinstance(node, dict), f"{path}: {part} is not on a dict"
        assert part in node, f"missing: {path}"
        node = node[part]
    return node


async def _run(client, grade="Kindergarten", audio="cmVjb3JkaW5n"):
    from app.domain.enums import Grade
    from app.engines.registry import speaking_engine

    sentences = speaking_engine().get_items(Grade(grade))
    subs = [
        {"sentence_id": s.sentence_id, "original_sentence": s.sentence,
         "audio_base64": audio, "audio_format": "wav",
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


class TestSentenceShape:
    @pytest.mark.parametrize("path", sorted(TOP_FIELDS))
    async def test_top_level_field(
        self, client, mock_firebase_auth, seed_user, mock_speech, path
    ):
        _, data = await _run(client)
        assert path in data, path

    @pytest.mark.parametrize("path", sorted(SUMMARY_FIELDS))
    async def test_summary_field(
        self, client, mock_firebase_auth, seed_user, mock_speech, path
    ):
        _, data = await _run(client)
        assert path in data["summary"], path

    @pytest.mark.parametrize("path", sorted(SENTENCE_FIELDS))
    async def test_sentence_field(
        self, client, mock_firebase_auth, seed_user, mock_speech, path
    ):
        _, data = await _run(client)
        assert data["sentences"], "no sentences"
        for sentence in data["sentences"]:
            dig(sentence, path)

    async def test_a_sentence_holds_nothing_else(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        """Five keys per sentence. Anything more crept back in."""
        _, data = await _run(client)
        expected = {"sentence_id", "sentence", "answered", "status", "reason",
                    "transcription", "analysis", "tags"}
        for sentence in data["sentences"]:
            assert set(sentence) == expected, set(sentence) ^ expected

    async def test_submit_and_result_return_the_same_shape(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        submit, result = await _run(client)
        assert [s["sentence_id"] for s in submit["sentences"]] == \
               [s["sentence_id"] for s in result["sentences"]]
        for a, b in zip(submit["sentences"], result["sentences"]):
            assert set(a) == set(b)
            assert set(a["analysis"]) == set(b["analysis"])

    async def test_one_row_per_sentence_in_the_test(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        from app.domain.enums import Grade
        from app.engines.registry import speaking_engine

        _, data = await _run(client)
        expected = speaking_engine().get_items(Grade.KINDERGARTEN)
        assert len(data["sentences"]) == len(expected)
        assert [s["sentence_id"] for s in data["sentences"]] == \
               [s.sentence_id for s in expected]

    async def test_status_values_are_the_three_states(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        allowed = {"answered", "not_attempted", "needs_review"}
        for sentence in data["sentences"]:
            assert sentence["status"] in allowed, sentence["status"]
            assert sentence["answered"] == (sentence["status"] == "answered")

    async def test_level_is_never_blank(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        for sentence in data["sentences"]:
            assert sentence["analysis"]["overall"]["level"]

    async def test_feedback_is_never_blank(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        for sentence in data["sentences"]:
            analysis = sentence["analysis"]
            for key in ("pronunciation", "fluency", "prosody", "completeness"):
                assert analysis[key]["feedback"],                     f'{sentence["sentence_id"]}.{key}'
            assert analysis["parent_tip"]

    async def test_lists_are_lists_even_when_empty(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        """Firebase stores no empty containers, so these come back absent."""
        _, data = await _run(client)
        for sentence in data["sentences"]:
            assert isinstance(sentence["tags"], list)
            assert isinstance(sentence["analysis"]["strengths"], list)
            assert isinstance(sentence["analysis"]["areas_to_improve"], list)
            assert isinstance(sentence["analysis"]["disfluency"]["fillers"], list)


class TestUnattempted:
    async def test_nothing_recorded(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client, audio="")
        assert data["summary"]["answered"] == 0
        assert data["summary"]["percentage"] == 0
        assert not data["dear_parent_tags"]
        for sentence in data["sentences"]:
            assert sentence["answered"] is False
            assert sentence["status"] == "not_attempted"
            assert sentence["analysis"]["overall"]["score"] == 0.0
            assert sentence["transcription"]["heard"] == ""
            assert sentence["transcription"]["spoken_sounds"] == ""
            assert sentence["tags"] == []

    async def test_the_reference_is_never_echoed_back(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client, audio="")
        for sentence in data["sentences"]:
            assert sentence["transcription"]["heard"] == ""
            assert sentence["transcription"]["verbatim"] == ""

    async def test_an_unattempted_sentence_says_why(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client, audio="")
        for sentence in data["sentences"]:
            assert sentence["reason"], sentence["sentence_id"]


class TestHeadlineIsOneNumber:
    async def test_percentage_matches_the_average(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        """A child who read one sentence at 95.9 was reported at both 95.9 and
        12.0 - the second being how much of the test was attempted, not how
        well it was read."""
        _, data = await _run(client)
        summary = data["summary"]
        assert summary["percentage"] == summary["average_score"]

    async def test_attempted_is_reported_separately(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        summary = data["summary"]
        assert summary["answered"] <= summary["sentences"]
