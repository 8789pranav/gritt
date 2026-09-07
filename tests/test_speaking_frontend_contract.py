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


class TestReportDerivation:
    """What TestResults.tsx computes from the response, checked here.

    The component reads paths, so a rename is silent on both sides: the page
    renders blank rather than raising. These reproduce its derivation so a
    shape change fails in CI instead of in front of a parent.
    """

    async def _rows(self, client, **kwargs):
        _, data = await _run(client, **kwargs)
        summary = data.get("summary") or {}
        sentences = data.get("sentences") or []
        rows = []
        for result in sentences:
            analysis = result.get("analysis") or {}
            score = (analysis.get("overall") or {}).get("score") or 0
            rows.append({
                "word": result.get("sentence") or "",
                "attempt": (result.get("transcription") or {}).get("heard") or "",
                "correct": bool(result.get("answered")) and score >= 85,
                "time": (analysis.get("timing") or {}).get("duration_seconds") or 0,
                "score": score,
                "status": ("Answered" if result.get("status") == "answered"
                           else "Needs Review"
                           if result.get("status") == "needs_review"
                           else "Not Attempted"),
                "level": (analysis.get("overall") or {}).get("level") or "",
                "pronunciation": analysis.get("pronunciation"),
                "fluency": analysis.get("fluency"),
                "grammar": analysis.get("completeness"),
                "strengths": analysis.get("strengths") or [],
                "parent_tip": analysis.get("parent_tip") or "",
                "sentence_id": result.get("sentence_id") or "",
            })
        return summary, sentences, rows

    async def test_header_values_are_all_readable(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        summary, _, _ = await self._rows(client)
        for key in ("total_marks", "user_score", "answered",
                    "average_score", "level"):
            assert key in summary, key
        # .toFixed(1) on the score would throw if this were undefined
        assert isinstance(summary["user_score"], (int, float))
        assert summary["level"]

    async def test_one_row_per_sentence_with_text_and_level(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, sentences, rows = await self._rows(client)
        assert len(rows) == len(sentences)
        assert all(r["word"] for r in rows)
        assert all(r["level"] for r in rows)

    @pytest.mark.parametrize("dimension", ["pronunciation", "fluency", "grammar"])
    async def test_each_dimension_has_a_score_and_feedback(
        self, client, mock_firebase_auth, seed_user, mock_speech, dimension
    ):
        """The report renders row.<dimension>.score and .feedback."""
        _, _, rows = await self._rows(client)
        for row in rows:
            block = row[dimension]
            assert isinstance(block, dict), f'{row["sentence_id"]}.{dimension}'
            assert isinstance(block.get("score"), (int, float))
            assert block.get("feedback")

    async def test_tags_come_from_the_sentence_not_a_separate_array(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, sentences, _ = await self._rows(client)
        tag_map = {s["sentence_id"]: s["tags"] for s in sentences}
        assert len(tag_map) == len(sentences)
        assert all(isinstance(v, list) for v in tag_map.values())

    async def test_strengths_aggregate_from_answered_sentences(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, sentences, _ = await self._rows(client)
        answered = [s for s in sentences if s["answered"]]
        strengths = [
            item for s in answered
            for item in (s["analysis"].get("strengths") or [])
        ]
        assert isinstance(strengths, list)

    async def test_an_unattempted_row_still_renders(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        """Every value the row template touches must exist, not be undefined."""
        _, _, rows = await self._rows(client, audio="")
        assert rows
        for row in rows:
            assert row["status"] == "Not Attempted"
            assert row["score"] == 0
            assert row["level"]
            assert row["parent_tip"]
            assert isinstance(row["time"], (int, float))
            assert row["correct"] is False


class TestTeacherTable:
    """One row per sentence, derived from the sentences rather than stored
    beside them - the old response built this list from its own copy of the
    numbers, which gave the same fact two homes and two chances to go stale."""

    ROW_FIELDS = {
        "sentence_id", "sentence", "heard", "status", "correct",
        "overall_score", "level", "pronunciation", "fluency", "prosody",
        "completeness", "wcpm", "time", "pauses", "fillers",
        "error_type", "icon", "tags",
    }

    async def _table(self, client, **kwargs):
        _, data = await _run(client, **kwargs)
        return data, data["teacher_admin_detail"]

    async def test_the_block_is_present(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, detail = await self._table(client)
        for key in ("test_level", "sentences", "answered",
                    "instructional_level", "table_data"):
            assert key in detail, key

    async def test_one_row_per_sentence(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        data, detail = await self._table(client)
        rows = detail["table_data"]
        assert len(rows) == len(data["sentences"])
        assert [r["sentence_id"] for r in rows] == \
               [s["sentence_id"] for s in data["sentences"]]

    @pytest.mark.parametrize("field", sorted(ROW_FIELDS))
    async def test_every_row_field(
        self, client, mock_firebase_auth, seed_user, mock_speech, field
    ):
        _, detail = await self._table(client)
        for row in detail["table_data"]:
            assert field in row, f'{row.get("sentence_id")}.{field}'

    async def test_a_row_holds_nothing_else(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, detail = await self._table(client)
        for row in detail["table_data"]:
            assert set(row) == self.ROW_FIELDS, set(row) ^ self.ROW_FIELDS

    async def test_the_table_agrees_with_the_sentences(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        """The reason to derive it rather than store it."""
        data, detail = await self._table(client)
        by_id = {s["sentence_id"]: s for s in data["sentences"]}
        for row in detail["table_data"]:
            sentence = by_id[row["sentence_id"]]
            analysis = sentence["analysis"]
            assert row["overall_score"] == analysis["overall"]["score"]
            assert row["level"] == analysis["overall"]["level"]
            assert row["pronunciation"] == analysis["pronunciation"]["score"]
            assert row["fluency"] == analysis["fluency"]["score"]
            assert row["completeness"] == analysis["completeness"]["score"]
            assert row["tags"] == sentence["tags"]
            assert row["sentence"] == sentence["sentence"]

    async def test_answered_count_matches_the_summary(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        data, detail = await self._table(client)
        assert detail["answered"] == data["summary"]["answered"]

    async def test_an_unattempted_row_is_labelled_not_marked_wrong(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        """A child who never saw a sentence has not got it wrong."""
        _, detail = await self._table(client, audio="")
        for row in detail["table_data"]:
            assert row["status"] == "Not Attempted"
            assert row["icon"] == "Not answered"
            assert row["error_type"] == "Not attempted"
            assert row["correct"] is False

    async def test_a_wrong_answer_names_what_went_wrong(self):
        """error_type says which error, not just "incorrect"."""
        from app.engines.speaking.result import teacher_table

        sentence = {
            "sentence_id": "s1", "sentence": "The cat sat.", "answered": True,
            "status": "answered", "tags": [],
            "transcription": {"heard": "The cat sat."},
            "analysis": {
                "overall": {"score": 55.0, "level": "Developing"},
                "pronunciation": {"score": 55.0}, "fluency": {"score": 60.0},
                "prosody": {"score": 50.0}, "completeness": {"score": 70.0},
                "reading": {"wcpm": 30.0}, "timing": {},
                "disfluency": {}, "errors": {"skipped": 2},
            },
        }
        row = teacher_table([sentence])[0]
        assert row["error_type"] == "Skipped words"
        assert row["icon"] == "Incorrect"

    async def test_a_strong_reading_has_no_error_type(self):
        from app.engines.speaking.result import teacher_table

        sentence = {
            "sentence_id": "s1", "sentence": "The cat sat.", "answered": True,
            "status": "answered", "tags": [],
            "transcription": {"heard": "The cat sat."},
            "analysis": {
                "overall": {"score": 95.0, "level": "Excellent"},
                "pronunciation": {"score": 95.0}, "fluency": {"score": 95.0},
                "prosody": {"score": 90.0}, "completeness": {"score": 100.0},
                "reading": {"wcpm": 60.0}, "timing": {},
                "disfluency": {}, "errors": {},
            },
        }
        row = teacher_table([sentence])[0]
        assert row["error_type"] is None
        assert row["correct"] is True
        assert row["icon"] == "Correct"


class TestNoRawDetailInTheResponse:
    """The per-word and per-phoneme detail produces every score and is what
    the feedback quotes, but it is not carried in the response. Twenty phoneme
    accuracies per sentence bury the number and the one thing to do about it.
    /lab still exposes the detail for diagnosis."""

    async def test_no_findings_or_words_on_a_sentence(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        for sentence in data["sentences"]:
            analysis = sentence["analysis"]
            assert "findings" not in analysis
            assert "words" not in analysis
            assert "findings" not in analysis.get("pronunciation", {})
            assert "words" not in analysis.get("pronunciation", {})

    async def test_pronunciation_is_a_score_and_a_line(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        for sentence in data["sentences"]:
            block = sentence["analysis"]["pronunciation"]
            assert set(block) == {"score", "feedback"}, set(block)

    async def test_the_sounds_the_child_made_are_still_reported(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        """Dropping the detail must not drop what was actually said."""
        _, data = await _run(client)
        for sentence in data["sentences"]:
            assert "spoken_sounds" in sentence["transcription"]

    async def test_the_teacher_table_carries_no_raw_detail_either(
        self, client, mock_firebase_auth, seed_user, mock_speech
    ):
        _, data = await _run(client)
        for row in data["teacher_admin_detail"]["table_data"]:
            assert "findings" not in row
            assert "words" not in row
            assert "phonemes" not in row
