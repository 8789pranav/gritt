"""Bug List v2, Part 2: the bugs inside the activities.

L-D11 to L-D15 (Logic Quest), A8 and A11 (Voice Challenge), 76 (Word Wizard)
and S5 (Story Explorer). Every test names the bug it closes.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from app.domain.enums import Grade, TestType
from app.engines.registry import comprehension_engine, logic_engine, spelling_engine
from app.tagging.config_loader import load_tag_config

GRADES = ["Kindergarten", "First", "Second", "Third"]
GRADE_ENUMS = {
    "Kindergarten": Grade.KINDERGARTEN,
    "First": Grade.FIRST,
    "Second": Grade.SECOND,
    "Third": Grade.THIRD,
}


async def _logic_run(client, grade: str, wrong_item_types=()) -> Dict[str, Any]:
    """Submit a Logic Quest run, missing the named item types."""
    items = logic_engine().get_items(GRADE_ENUMS[grade])
    responses = []
    for item in items:
        correct = item.correct_answer_index
        missed = item.item_type in wrong_item_types
        responses.append(
            {
                "item_id": item.item_id,
                "selected_answer_index": (correct + 1) % len(item.options)
                if missed
                else correct,
                # Slow enough that a missed item also looks laboured, which
                # is the condition L-D14 was reported under.
                "response_time_seconds": 90.0 if missed else 8.0,
                "attempts": 1,
                "self_corrected": False,
            }
        )
    r = await client.post(
        "/logic/submit_test/",
        json={
            "idToken": "test-token",
            "child_id": "child-1",
            "grade": grade,
            "responses": responses,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# L-D11 - the parent-facing accuracy figure read 0
# ---------------------------------------------------------------------------
class TestLD11LogicAccuracyReachesTheParent:
    @pytest.mark.parametrize("grade", GRADES)
    async def test_complete_result_reports_the_real_accuracy(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        await _logic_run(client, grade, wrong_item_types=("strategy",))

        r = await client.post(
            "/logic/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": grade},
        )
        assert r.status_code == 200, r.text
        data = r.json()

        correct = data["correct_answers"]
        total = data["total_items"]
        expected = round(correct / total * 100, 1)

        assert data["parent_summary"]["overall_accuracy"] == expected
        assert data["parent_summary"]["overall_accuracy"] > 0

    async def test_it_matches_the_internal_signal(
        self, client, mock_firebase_auth, seed_user
    ):
        submitted = await _logic_run(client, "Second", wrong_item_types=("strategy",))
        r = await client.post(
            "/logic/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
        )
        stored = r.json()
        assert (
            stored["parent_summary"]["overall_accuracy"]
            == stored["signals"]["overall_accuracy"]
            == submitted["signals"]["overall_accuracy"]
        )


# ---------------------------------------------------------------------------
# L-D12 - the teacher table printed tag names as error types
# ---------------------------------------------------------------------------
class TestLD12PlainEnglishErrorTypes:
    async def test_no_row_prints_a_raw_tag_name(
        self, client, mock_firebase_auth, seed_user
    ):
        data = await _logic_run(
            client, "Second", wrong_item_types=("rule_boundary", "dual_rule", "pattern")
        )
        rows = data["teacher_admin_detail"]["table_data"]
        wrong = [r for r in rows if not r["correct"]]
        assert wrong

        every_tag = {t.id for t in load_tag_config(TestType.LOGIC).tags}
        readable = {t.replace("_", " ") for t in every_tag}
        for row in wrong:
            error_type = row["error_type"]
            assert error_type
            assert error_type not in every_tag
            assert error_type not in readable
            # Plain English starts with a capital and is a phrase, not an id.
            assert error_type[0].isupper()
            assert "_" not in error_type

    async def test_a_missed_question_says_which_kind_was_missed(
        self, client, mock_firebase_auth, seed_user
    ):
        data = await _logic_run(client, "Second", wrong_item_types=("pattern",))
        rows = data["teacher_admin_detail"]["table_data"]
        missed = [r["error_type"] for r in rows if not r["correct"]]
        assert missed
        assert all(m == "Pattern question missed" for m in missed), missed

    async def test_the_stored_table_reads_the_same_as_the_submitted_one(
        self, client, mock_firebase_auth, seed_user
    ):
        submitted = await _logic_run(client, "Third", wrong_item_types=("syllogism",))
        r = await client.post(
            "/logic/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Third"},
        )
        stored = r.json()
        assert [
            row["error_type"] for row in submitted["teacher_admin_detail"]["table_data"]
        ] == [row["error_type"] for row in stored["teacher_admin_detail"]["table_data"]]


# ---------------------------------------------------------------------------
# L-D13 - hard items of each kind were counted as successes
# ---------------------------------------------------------------------------
class TestLD13HardItemCounts:
    @pytest.mark.parametrize("grade", GRADES)
    async def test_hard_counts_match_the_bank_however_the_child_answered(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        from app.domain.enums import CognitiveTag, Difficulty
        from app.engines.logic.signals import LOAD_TAGS, PATTERN_TAGS

        items = logic_engine().get_items(GRADE_ENUMS[grade])

        def expected_hard(predicate) -> int:
            return sum(
                1
                for i in items
                if predicate(i) and i.difficulty is Difficulty.HARD
            )

        # Answer EVERY question wrong: the counts must not move.
        data = await _logic_run(
            client, grade, wrong_item_types={i.item_type for i in items}
        )
        signals = data["signals"]

        assert signals["pattern_hard_count"] == expected_hard(
            lambda i: i.primary_tag in PATTERN_TAGS
        )
        assert signals["relational_hard_count"] == expected_hard(
            lambda i: i.primary_tag is CognitiveTag.RELATIONAL_REASONING_PRESENT
        )
        assert signals["systematic_hard_count"] == expected_hard(
            lambda i: i.primary_tag is CognitiveTag.SYSTEMATIC_PROBLEM_SOLVING
        )
        assert signals["flexibility_hard_count"] == expected_hard(
            lambda i: i.primary_tag is CognitiveTag.FLEXIBLE_STRATEGY_USE
        )
        assert signals["load_hard_count"] == expected_hard(
            lambda i: i.primary_tag in LOAD_TAGS
        )

    async def test_grade_three_has_its_hard_pattern_item(
        self, client, mock_firebase_auth, seed_user
    ):
        """3-1 is a hard pattern question. The count used to read 0."""
        data = await _logic_run(client, "Third", wrong_item_types=("pattern",))
        assert data["signals"]["pattern_hard_count"] >= 1


# ---------------------------------------------------------------------------
# L-D14 - one outcome tag per question
# ---------------------------------------------------------------------------
class TestLD14OneOutcomeTagPerQuestion:
    @pytest.mark.parametrize("grade", GRADES)
    async def test_no_question_carries_a_tag_and_its_own_missed_partner(
        self, client, mock_firebase_auth, seed_user, grade
    ):
        items = logic_engine().get_items(GRADE_ENUMS[grade])
        data = await _logic_run(
            client, grade, wrong_item_types={i.item_type for i in items}
        )
        for entry in data["per_item_tags"]:
            tags = set(entry["tags"])
            for tag in list(tags):
                if tag.endswith("_missed"):
                    assert tag[: -len("_missed")] not in tags, (
                        f"{entry['item_id']} carries both outcomes: {sorted(tags)}"
                    )

    async def test_a_missed_multistep_question_is_missed_and_nothing_else(
        self, client, mock_firebase_auth, seed_user
    ):
        data = await _logic_run(
            client, "Third", wrong_item_types=("transitive_reasoning",)
        )
        by_id = {e["item_id"]: e["tags"] for e in data["per_item_tags"]}
        tags = by_id["logic_3_2"]
        assert "reasoning_under_load_missed" in tags
        assert "reasoning_under_load" not in tags


# ---------------------------------------------------------------------------
# L-D15 - one weakness counted twice
# ---------------------------------------------------------------------------
class TestLD15RuleMaintenanceIsGone:
    def test_the_tag_no_longer_exists(self):
        ids = {t.id for t in load_tag_config(TestType.LOGIC).tags}
        assert "rule_maintenance_difficulty" not in ids

    def test_its_signals_are_no_longer_derived(self):
        config = load_tag_config(TestType.LOGIC)
        assert not [s for s in config.derived_signals if s.startswith("rule_maintenance")]

    def test_no_learning_area_still_points_at_it(self):
        areas = json.load(open("data/tags/learning_areas.json", encoding="utf-8"))
        for area in areas["areas"].values():
            for tag_ids in area["sources"].values():
                assert "rule_maintenance_difficulty" not in tag_ids

    async def test_a_missed_construct_produces_exactly_one_growth_edge(
        self, client, mock_firebase_auth, seed_user
    ):
        """The two systematic misses used to read as two separate findings."""
        data = await _logic_run(
            client, "Second", wrong_item_types=("rule_boundary", "dual_rule")
        )
        growth = [
            t["tag"] for t in data["dear_parent_tags"] if t["polarity"] == "growth_edge"
        ]
        assert growth.count("systematic_problem_solving_emerging") == 1
        assert not any("rule_maintenance" in t for t in growth)


# ---------------------------------------------------------------------------
# A11 - Voice Challenge still labelled the child
# ---------------------------------------------------------------------------
BANNED_SPEAKING_FIELDS = (
    "level",
    "grade_placement",
    "instructional_level",
    "percentage",
    "user_score",
    "total_marks",
)


async def _speaking_run(client, grade="Second") -> Dict[str, Any]:
    r = await client.post(
        "/speaking/get_all_sentences/",
        json={"idToken": "test-token", "child_id": "child-1", "grade": grade},
    )
    sentences = r.json()["sentences"]
    r = await client.post(
        "/speaking/submit/",
        json={
            "idToken": "test-token",
            "child_id": "child-1",
            "grade": grade,
            "submissions": [
                {
                    "sentence_id": s["sentence_id"],
                    "original_sentence": s["sentence"],
                    "audio_base64": "ZmFrZS1hdWRpbw==",
                    "audio_format": "wav",
                }
                for s in sentences
            ],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestA11NoLabelsOrScoresInVoiceChallenge:
    async def test_submit_carries_none_of_them_at_the_top_level(
        self, client, mock_firebase_auth, seed_user, mock_speech, mock_tts
    ):
        data = await _speaking_run(client)
        for field in BANNED_SPEAKING_FIELDS:
            assert field not in data, field
        assert field not in data["teacher_admin_detail"]

    async def test_complete_result_carries_none_of_them(
        self, client, mock_firebase_auth, seed_user, mock_speech, mock_tts
    ):
        await _speaking_run(client)
        r = await client.post(
            "/speaking/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
        )
        data = r.json()
        for section in ("summary", "parent_summary", "teacher_admin_detail"):
            for field in BANNED_SPEAKING_FIELDS:
                assert field not in data[section], f"{section}.{field}"

    async def test_no_speaker_label_or_placement_survives_anywhere(
        self, client, mock_firebase_auth, seed_user, mock_speech, mock_tts
    ):
        await _speaking_run(client)
        r = await client.post(
            "/speaking/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
        )
        text = json.dumps(r.json())
        for label in (
            "Excellent Speaker",
            "Good Speaker",
            "Developing Speaker",
            "Needs Improvement",
            "Above Grade Level",
            "At Grade Level",
            "Below Grade Level",
        ):
            assert label not in text, label

    async def test_the_counts_a_parent_can_act_on_are_still_there(
        self, client, mock_firebase_auth, seed_user, mock_speech, mock_tts
    ):
        data = await _speaking_run(client)
        assert data["answered_count"] > 0
        assert "average_score" in data
        assert data["signals"]["wcpm"] > 0


# ---------------------------------------------------------------------------
# Part 5 - Read Aloud can now reach the "still growing" half of the letter
# ---------------------------------------------------------------------------
class TestPart5ReadAloudGrowthEdges:
    def test_the_dead_band_between_70_and_85_is_covered(self):
        """Nothing between about 70 and 87 used to produce a tag either way."""
        from app.tagging.emitter import emit_tags

        signals = {
            "sentences_answered": 8,
            "avg_accuracy": 78.0,
            "avg_fluency": 78.0,
            "avg_prosody": 70.0,
            "avg_completeness": 100.0,
            "omission_count": 0,
            "wcpm_band": "in_band",
            "phonics_short_vowel": 78.0,
            "phonics_long_vowel": 78.0,
            "phonics_consonant_blend": 78.0,
            "phonics_consonant_digraph": 78.0,
        }
        tags = emit_tags(TestType.SPEAKING, signals)
        growth = {t.tag for t in tags if t.polarity.value == "growth_edge"}
        assert {
            "decoding_developing",
            "phrasing_developing",
            "expression_developing",
            "vowel_sounds_developing",
            "blends_developing",
            "digraphs_developing",
        } <= growth

    def test_a_flat_voice_at_75_now_fires(self):
        """Vedika scored 75.6 with "Read in a flat voice" and nothing fired."""
        from app.tagging.emitter import emit_tags

        tags = emit_tags(
            TestType.SPEAKING,
            {"sentences_answered": 8, "avg_prosody": 75.6, "avg_completeness": 100.0},
        )
        assert "expression_developing" in {t.tag for t in tags}

    def test_a_single_skipped_word_now_fires(self):
        """Vedika skipped words in two sentences and nothing fired."""
        from app.tagging.emitter import emit_tags

        tags = emit_tags(
            TestType.SPEAKING,
            {"sentences_answered": 8, "omission_count": 1, "avg_completeness": 96.0},
        )
        by_id = {t.tag: t for t in tags}
        assert "skips_words" in by_id
        assert by_id["skips_words"].polarity.value == "growth_edge"

    @pytest.mark.parametrize(
        "band,expected",
        [
            ("in_band", "reading_pace_in_band"),
            ("above_band", "reading_pace_above_band"),
            ("below_band", "reading_pace_below_band"),
        ],
    )
    def test_reading_pace_is_reported_and_is_never_a_judgement(self, band, expected):
        from app.tagging.emitter import emit_tags

        tags = emit_tags(
            TestType.SPEAKING,
            {"sentences_answered": 8, "wcpm_band": band, "avg_completeness": 100.0},
        )
        by_id = {t.tag: t for t in tags}
        assert expected in by_id
        assert by_id[expected].polarity.value == "neutral"
        # One measure, one tag: the old judgement-flavoured pair is gone.
        assert "reading_rate_on_track" not in by_id
        assert "reading_rate_slow" not in by_id

    async def test_a_real_run_produces_a_pace_tag(
        self, client, mock_firebase_auth, seed_user, mock_speech, mock_tts
    ):
        data = await _speaking_run(client)
        tags = {t["tag"] for t in data["dear_parent_tags"]}
        assert any(t.startswith("reading_pace_") for t in tags)

    def test_every_new_tag_has_a_learning_area_and_a_plain_english_name(self):
        areas = json.load(open("data/tags/learning_areas.json", encoding="utf-8"))
        placed = {
            tag
            for area in areas["areas"].values()
            for tag_ids in area["sources"].values()
            for tag in tag_ids
        }
        names = areas["tag_display_names"]
        for tag in (
            "decoding_developing",
            "phrasing_developing",
            "expression_developing",
            "vowel_sounds_developing",
            "blends_developing",
            "digraphs_developing",
            "reading_pace_in_band",
            "reading_pace_above_band",
            "reading_pace_below_band",
        ):
            assert tag in placed, tag
            assert tag in names, tag


# ---------------------------------------------------------------------------
# A8 - is pause detection actually connected
# ---------------------------------------------------------------------------
class TestA8PauseDetectionIsConnected:
    def test_a_gap_between_words_is_counted_as_a_pause(self):
        from app.engines.speaking.metrics import timing_metrics
        from app.infrastructure.azure_pronunciation import Word

        def word(text, offset_ms, duration_ms):
            return Word(
                word=text,
                accuracy=95.0,
                error_type="None",
                offset_ms=offset_ms,
                duration_ms=duration_ms,
                phonemes=[],
            )

        # Half a second of silence between "the" and "butterfly".
        words = [word("the", 0.0, 200.0), word("butterfly", 700.0, 400.0)]
        metrics = timing_metrics(words)

        assert metrics.pause_count == 1
        assert metrics.longest_pause_ms == 500.0
        assert metrics.speaking_span_ms == 1100.0

    def test_no_gap_means_no_pause(self):
        from app.engines.speaking.metrics import timing_metrics
        from app.infrastructure.azure_pronunciation import Word

        words = [
            Word("the", 95.0, "None", 0.0, 200.0, []),
            Word("cat", 95.0, "None", 210.0, 200.0, []),
        ]
        metrics = timing_metrics(words)
        assert metrics.pause_count == 0

    def test_the_chain_carries_the_count_all_the_way_to_the_signals(self):
        """Zeros in a report mean a fluent reader, not a disconnected metric."""
        from app.engines.speaking.metrics import timing_metrics
        from app.engines.speaking.pipeline import aggregate
        from app.infrastructure.azure_pronunciation import Word

        timing = timing_metrics(
            [
                Word("the", 95.0, "None", 0.0, 200.0, []),
                Word("butterfly", 95.0, "None", 900.0, 400.0, []),
            ]
        ).as_dict()
        assert timing["long_pause_count"] >= 1

        measured = [
            {
                "sentence_id": "t1",
                "status": "answered",
                "scores": {"accuracy": 90.0, "fluency": 90.0, "completeness": 100.0,
                           "prosody": 90.0, "pron_score": 90.0},
                "timing": timing,
                "reading": {"total_words": 2, "correct_words": 2, "wcpm": 60.0},
                "disfluency": {"filler_count": 0, "repetitions": 0},
                "errors": {},
                "phonics": {},
            }
        ]
        signals = aggregate(measured, "Second")
        assert signals["total_long_pause_count"] >= 1
        assert signals["total_pause_count"] >= 1


# ---------------------------------------------------------------------------
# 76 - Word Wizard overall_accuracy meant sounds, not words
# ---------------------------------------------------------------------------
class TestBug76AccuracyMeansWhatItSays:
    async def test_overall_accuracy_counts_whole_words(
        self, client, mock_firebase_auth, seed_user
    ):
        words = spelling_engine().get_items(Grade.SECOND)
        attempts = {"clunk": "clunck", "graph": "graff", "phone": "fone",
                    "coast": "cost", "climax": "climacks", "said": "sed"}

        await client.post(
            "/submit_words/",
            json={
                "idToken": "test-token",
                "child_id": "child-1",
                "grade": "Second",
                "words": [
                    {
                        "word": w.word,
                        "user_input": attempts.get(w.word, w.word),
                        "type": w.word_type.value,
                        "time": 6.0,
                        "hints_used": 0,
                    }
                    for w in words
                ],
            },
        )
        r = await client.post(
            "/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
        )
        summary = r.json()["parent_summary"]

        expected = round(summary["words_correct"] / summary["words_total"] * 100)
        assert summary["overall_accuracy"] == expected
        assert summary["words_correct"] == 15 - len(attempts)
        assert summary["words_total"] == 15

    async def test_the_sound_figure_keeps_its_own_name_and_explanation(
        self, client, mock_firebase_auth, seed_user
    ):
        words = spelling_engine().get_items(Grade.SECOND)
        attempts = {"clunk": "clunck", "graph": "graff", "phone": "fone",
                    "coast": "cost", "climax": "climacks", "said": "sed"}
        await client.post(
            "/submit_words/",
            json={
                "idToken": "test-token",
                "child_id": "child-1",
                "grade": "Second",
                "words": [
                    {
                        "word": w.word,
                        "user_input": attempts.get(w.word, w.word),
                        "type": w.word_type.value,
                        "time": 6.0,
                        "hints_used": 0,
                    }
                    for w in words
                ],
            },
        )
        r = await client.post(
            "/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
        )
        summary = r.json()["parent_summary"]

        # The number that used to be called overall_accuracy is still
        # reported, under a name that says what it counts.
        assert summary["sound_accuracy"] > summary["overall_accuracy"]
        assert "Sound accuracy counts the sounds" in summary["sound_accuracy_note"]

    async def test_a_perfect_run_reads_100_on_both(
        self, client, mock_firebase_auth, seed_user
    ):
        words = spelling_engine().get_items(Grade.SECOND)
        await client.post(
            "/submit_words/",
            json={
                "idToken": "test-token",
                "child_id": "child-1",
                "grade": "Second",
                "words": [
                    {"word": w.word, "user_input": w.word,
                     "type": w.word_type.value, "time": 6.0, "hints_used": 0}
                    for w in words
                ],
            },
        )
        r = await client.post(
            "/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
        )
        summary = r.json()["parent_summary"]
        assert summary["overall_accuracy"] == 100
        assert summary["sound_accuracy"] == 100


# ---------------------------------------------------------------------------
# S5 - the vocabulary word with no context
# ---------------------------------------------------------------------------
class TestS5RustHasContext:
    def test_the_passage_tells_a_child_what_rust_is(self):
        stories = comprehension_engine().get_items(Grade.SECOND)
        story = next(s for s in stories if "rust" in s.story_text)
        sentence = next(
            s for s in story.story_text.split(".") if "rust" in s
        ).lower()
        # The clue a child needs: the colour, and that it grows on old metal.
        assert "reddish-brown" in sentence
        assert "metal" in sentence

    def test_the_question_is_still_answerable_from_that_clue(self):
        stories = comprehension_engine().get_items(Grade.SECOND)
        story = next(s for s in stories if "rust" in s.story_text)
        question = next(q for q in story.questions if "rust" in q.question)
        answer = question.options[question.correct_index].lower()
        assert "reddish-brown" in answer

    @pytest.mark.parametrize("grade", GRADES)
    def test_every_vocabulary_word_appears_in_its_own_passage(self, grade):
        """A word a child cannot find in the story cannot be worked out."""
        import re

        for story in comprehension_engine().get_items(GRADE_ENUMS[grade]):
            text = story.story_text.lower()
            for question in story.questions:
                if question.question_type.value != "vocabulary":
                    continue
                quoted = re.findall(r"'([^']+)'", question.question)
                assert quoted, question.question
                word = quoted[0].lower()
                assert re.search(rf"\b{re.escape(word)}", text), (
                    f"{grade}: '{word}' is asked about but never appears in "
                    f"{story.title}"
                )


# ---------------------------------------------------------------------------
# C5 - Story Explorer response times
# ---------------------------------------------------------------------------
class TestC5ResponseTimesAreFilled:
    async def test_a_time_sent_by_the_client_survives_to_the_report(
        self, client, mock_firebase_auth, seed_user
    ):
        stories = comprehension_engine().get_items(Grade.SECOND)
        story_answers = [
            {
                "story_id": s.story_id,
                "answers": [
                    {
                        "question_id": q.question_id,
                        "selected_index": q.correct_index,
                        "response_time_seconds": 9.5,
                    }
                    for q in s.questions
                ],
            }
            for s in stories
        ]
        await client.post(
            "/comprehension/submit/",
            json={
                "idToken": "test-token",
                "child_id": "child-1",
                "grade": "Second",
                "story_answers": story_answers,
            },
        )
        r = await client.post(
            "/comprehension/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
        )
        data = r.json()

        rows = data["teacher_admin_detail"]["table_data"]
        assert rows
        assert all(row["time"] == 9.5 for row in rows)

        for story in data["story_breakdown"]:
            for question in story["questions"]:
                assert question["response_time_seconds"] == 9.5

    async def test_the_breakdown_says_what_kind_each_question_was(
        self, client, mock_firebase_auth, seed_user
    ):
        stories = comprehension_engine().get_items(Grade.SECOND)
        await client.post(
            "/comprehension/submit/",
            json={
                "idToken": "test-token",
                "child_id": "child-1",
                "grade": "Second",
                "story_answers": [
                    {
                        "story_id": s.story_id,
                        "answers": [
                            {
                                "question_id": q.question_id,
                                "selected_index": q.correct_index,
                                "response_time_seconds": 4.0,
                            }
                            for q in s.questions
                        ],
                    }
                    for s in stories
                ],
            },
        )
        r = await client.post(
            "/comprehension/complete_result/",
            json={"idToken": "test-token", "child_id": "child-1", "grade": "Second"},
        )
        for story in r.json()["story_breakdown"]:
            for question in story["questions"]:
                assert question["question_type"] in (
                    "literal",
                    "inferential",
                    "vocabulary",
                )
