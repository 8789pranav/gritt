"""The Learning Snapshot bug list, end to end.

One Grade 2 child, modelled on the run in the bug report: nine of fifteen
words spelled correctly with three of the misses being spelling conventions
(clunck, graff, fone), inference worked out but recall and vocabulary missed,
one construct missed in the Logic Quest, and eight sentences read aloud.

Every test here names the bug it closes.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from app.services.snapshot_service import SnapshotService
from app.services.snapshot_writer import SnapshotWriter

GRADE = "Second"

#: What this child wrote. The three at the top are the whole point: every
#: sound is right and the spelling rule is the only thing missing.
SPELLING_ATTEMPTS = {
    "clunk": "clunck",
    "graph": "graff",
    "phone": "fone",
    "coast": "cost",
    "climax": "climacks",
    "said": "sed",
}


# ---------------------------------------------------------------------------
# Fixtures: run all four activities for one child
# ---------------------------------------------------------------------------
@pytest.fixture
async def child(client, seed_user, mock_firebase_client):
    """A paid Grade 2 child, with a name the letter can use."""
    mock_firebase_client.ref("users/test-uid/children/child-1").set(
        {
            "name": "Pranav",
            "age": 7,
            "grade": GRADE,
            "payment_status": "paid",
        }
    )
    return {"token": "test-token", "child_id": "child-1"}


async def _submit_spelling(client, child) -> Dict[str, Any]:
    r = await client.post("/grade/", json={"grade": GRADE})
    words = r.json()["words"]
    payload = [
        {
            "word": w["word"],
            "user_input": SPELLING_ATTEMPTS.get(w["word"], w["word"]),
            "type": w.get("type", "regular"),
            "time": 8.0,
            "hints_used": 0,
        }
        for w in words
    ]
    r = await client.post(
        "/submit_words/",
        json={
            "idToken": child["token"],
            "child_id": child["child_id"],
            "grade": GRADE,
            "words": payload,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _submit_logic(client, child) -> Dict[str, Any]:
    from app.domain.enums import Grade
    from app.engines.registry import logic_engine

    r = await client.post(
        "/logic/get_test/",
        json={
            "idToken": child["token"],
            "child_id": child["child_id"],
            "grade": GRADE,
        },
    )
    shown = r.json()["items"]
    # The answer key never leaves the server, so the test reads it from the
    # engine the way the other suites do.
    by_id = {i.item_id: i for i in logic_engine().get_items(Grade.SECOND)}

    responses = []
    for entry in shown:
        item = by_id[entry["item_id"]]
        correct = item.correct_answer_index
        # Miss the two systematic questions, work everything else out.
        missed = item.item_type in ("rule_boundary", "dual_rule")
        responses.append(
            {
                "item_id": item.item_id,
                "selected_answer_index": (correct + 1) % len(item.options)
                if missed
                else correct,
                # 11 seconds on the combining item: took time, got it right.
                "response_time_seconds": 11.0
                if item.item_type == "combining"
                else 7.0,
                "attempts": 1,
                "self_corrected": False,
            }
        )

    r = await client.post(
        "/logic/submit_test/",
        json={
            "idToken": child["token"],
            "child_id": child["child_id"],
            "grade": GRADE,
            "responses": responses,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _submit_comprehension(client, child) -> Dict[str, Any]:
    from app.domain.enums import Grade
    from app.engines.registry import comprehension_engine

    await client.post(
        "/comprehension/get_stories/",
        json={
            "idToken": child["token"],
            "child_id": child["child_id"],
            "grade": GRADE,
        },
    )
    stories = comprehension_engine().get_items(Grade.SECOND)

    story_answers = []
    for story in stories:
        answers = []
        for question in story.questions:
            kind = question.question_type.value
            correct = question.correct_index
            # Inference worked out; recall and vocabulary mostly missed.
            right = kind == "inferential" or question.question_id in (
                "s1_q1",
                "s2_q1",
                "s1_q6",
            )
            answers.append(
                {
                    "question_id": question.question_id,
                    "selected_index": correct
                    if right
                    else (correct + 1) % len(question.options),
                    "response_time_seconds": 12.5,
                }
            )
        story_answers.append({"story_id": story.story_id, "answers": answers})

    r = await client.post(
        "/comprehension/submit/",
        json={
            "idToken": child["token"],
            "child_id": child["child_id"],
            "grade": GRADE,
            "story_answers": story_answers,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _submit_speaking(client, child, mock_speech) -> Dict[str, Any]:
    r = await client.post(
        "/speaking/get_all_sentences/",
        json={
            "idToken": child["token"],
            "child_id": child["child_id"],
            "grade": GRADE,
        },
    )
    sentences = r.json()["sentences"]

    r = await client.post(
        "/speaking/submit/",
        json={
            "idToken": child["token"],
            "child_id": child["child_id"],
            "grade": GRADE,
            "submissions": [
                {
                    "sentence_id": s["sentence_id"],
                    "original_sentence": s["sentence"],
                    "audio_base64": "ZmFrZS1hdWRpbw==",
                    "audio_format": "wav",
                    "time_to_speak_ms": 800.0,
                }
                for s in sentences
            ],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
async def full_run(client, child, mock_speech, mock_tts):
    """All four activities submitted, as a real child would."""
    return {
        "spelling": await _submit_spelling(client, child),
        "logic": await _submit_logic(client, child),
        "comprehension": await _submit_comprehension(client, child),
        "speaking": await _submit_speaking(client, child, mock_speech),
        "child": child,
    }


@pytest.fixture
def evidence(full_run):
    return SnapshotService().build_evidence(
        full_run["child"]["token"], full_run["child"]["child_id"], GRADE
    )


def _compliant_opening(evidence) -> dict:
    """An opening built the way the specification asks.

    Test letters are skeletons. Without this they fail the opening checks for
    reasons that have nothing to do with what is under test.
    """
    return {
        "headline": "Pranav takes time over the hard ones.",
        "paragraph": (
            "Pranav " + _required_facts_sentence(evidence)
            + " Where Pranav is still working is the spelling rules that "
            "sound does not reach."
        ),
    }


def _enough_noticed(evidence) -> list:
    """As many observations as the evidence supports, up to four.

    The section has a floor as well as a ceiling: a letter that leaves it
    empty is one a parent opens to no cards at all. Skeleton letters have to
    carry it or they fail for a reason that is not under test.
    """
    material = (evidence.get("strengths") or []) + (
        evidence.get("neutral_observations") or []
    )
    flawless = evidence.get("flawless_activities") or []
    wanted = min(4, len(material) + len(flawless))
    items = [
        {
            "headline": "Pranav worked through this one.",
            "signals": [signal["signal_name"]],
            "seen_in": [signal["seen_in"]],
            "paragraph": "x",
        }
        for signal in material[:wanted]
    ]
    for activity in flawless[: max(0, wanted - len(items))]:
        items.append(
            {
                "headline": "Pranav went through this one cleanly.",
                "seen_in": [activity["activity"]],
                "paragraph": "x",
            }
        )
    return items


def _one_grouped_growth_item(evidence) -> list:
    """Every growth edge, covered by a single item.

    The rule is coverage, not one section per edge, so a skeleton letter
    carries them all in one place.
    """
    return [
        {
            "headline": "Some things are still settling.",
            "signals": [g["signal_name"] for g in evidence["growth_edges"]],
            "seen_in": sorted({g["seen_in"] for g in evidence["growth_edges"]}),
            "paragraph": "x",
            "suggestion": {"because": "This is why."},
        }
    ]


def _balanced_conference() -> dict:
    """Four items a parent could take to a meeting.

    One thing to be glad about and one thing to raise: the section is checked
    for both, because only good news is not a conversation.
    """
    return {
        "items": [
            {"point": "p1", "worth_asking": "Worth asking.",
             "about": "strength"},
            {"point": "p2", "worth_asking": "Worth asking.",
             "about": "still_growing"},
            {"point": "p3", "worth_asking": "Worth asking.",
             "about": "strength"},
            {"point": "p4", "worth_asking": "Worth asking.",
             "about": "still_growing"},
        ]
    }


def _required_facts_sentence(evidence) -> str:
    """One sentence carrying every fact Stage A says the letter must name.

    Test letters are skeletons, so they would otherwise fail the specificity
    guardrail for reasons that have nothing to do with what is under test.
    """
    said = [
        (required.get("any_of") or ["x"])[0]
        for required in evidence.get("must_mention") or []
    ]
    return ("wrote " + ", ".join(said) + ".") if said else ""


# ---------------------------------------------------------------------------
# LS9 - every growth edge reaches the parent
# ---------------------------------------------------------------------------
class TestLS9EveryGrowthEdgeReachesTheParent:
    def test_growth_edges_are_not_capped_at_two(self, evidence):
        """The old pipeline kept two and dropped the rest."""
        assert len(evidence["growth_edges"]) > 2

    def test_the_spelling_conventions_finding_is_present(self, evidence):
        tags = [g["tag"] for g in evidence["growth_edges"]]
        assert "spelling_convention_emerging" in tags

    def test_the_spelling_conventions_finding_ranks_first(self, evidence):
        """It is specific, actionable, and was the one the cap dropped."""
        assert evidence["growth_edges"][0]["tag"] == "spelling_convention_emerging"

    def test_the_writer_rejects_a_letter_that_drops_one(self, evidence):
        writer = SnapshotWriter()
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            # Two items covering one edge between them: the rest are dropped.
            "still_growing": [
                {
                    "signals": [evidence["growth_edges"][0]["signal_name"]],
                    "suggestion": {"because": "This is why."},
                },
                {"signals": [], "suggestion": {"because": "This is why."}},
            ],
            "for_the_conference": {"items": []},
        }
        violations = writer._validate(letter, evidence)
        assert any("leaves out growth edges" in v for v in violations)

    def test_related_edges_may_be_grouped_into_one_item(self, evidence):
        """Four read-aloud sounds are one thing to work on, not four.

        The old rule demanded one item per edge, which produced letters with
        seven near-identical sections. The rule is coverage: every edge is
        named, however few items carry them.
        """
        writer = SnapshotWriter()
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            "still_growing": [
                {
                    "signals": [g["signal_name"] for g in evidence["growth_edges"]],
                    "suggestion": {"because": "This is why."},
                }
            ],
            "for_the_conference": {"items": []},
        }
        violations = writer._validate(letter, evidence)
        assert not any("growth edge" in v for v in violations)

    def test_a_letter_of_seven_sections_is_rejected(self, evidence):
        """Stage A groups the edges; the letter carries one section each."""
        writer = SnapshotWriter()
        names = [g["signal_name"] for g in evidence["growth_edges"]]
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            "still_growing": [
                {"signals": names, "suggestion": {"because": "This is why."}}
                for _ in range(7)
            ],
            "for_the_conference": {"items": []},
        }
        violations = writer._validate(letter, evidence)
        # Worth asking again for, never worth withholding the letter: a long
        # letter is a worse read, a missing growth edge is a worse letter.
        assert any("the evidence groups into" in v and v.startswith("voice - ")
                   for v in violations)

    def test_stage_a_groups_the_edges_rather_than_the_writer(self, evidence):
        """Which findings are the same finding is a fact, not prose.

        Asking the writer to work it out is what lost eleven of seventeen
        growth edges for the child who needed the letter most.
        """
        clusters = evidence["growth_clusters"]
        assert clusters
        assert len(clusters) < len(evidence["growth_edges"])

        grouped = [name for c in clusters for name in c["signals"]]
        assert sorted(grouped) == sorted(
            g["signal_name"] for g in evidence["growth_edges"]
        )
        # One cluster per area, and each says which activities produced it.
        assert len({c["cluster"] for c in clusters}) == len(clusters)
        assert all(c["seen_in"] for c in clusters)

    def test_an_edge_the_writer_drops_is_filed_not_lost(self, evidence):
        """A dropped signal name is repaired, because it is not prose."""
        from app.services.snapshot_writer import _repair

        cluster = max(evidence["growth_clusters"], key=lambda c: len(c["signals"]))
        assert len(cluster["signals"]) > 1
        kept, dropped = cluster["signals"][0], cluster["signals"][1:]

        letter = _repair(
            {
                "opening": {"headline": "x", "paragraph": "y"},
                "what_i_noticed": [],
                "still_growing": [
                    {"headline": "h", "signals": [kept],
                     "seen_in": list(cluster["seen_in"]), "paragraph": "p",
                     "suggestion": {"because": "This is why."}}
                ],
                "for_the_conference": {"items": []},
            },
            evidence,
        )
        covered = {
            name for item in letter["still_growing"]
            for name in item["signals"]
        }
        assert set(dropped) <= covered


# ---------------------------------------------------------------------------
# LS1 - a praise headline must never sit over a growth edge
# ---------------------------------------------------------------------------
class TestLS1HeadlinePolarity:
    def test_praise_over_a_growth_edge_is_a_violation(self, evidence):
        growth = evidence["growth_edges"][0]
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [
                {
                    "headline": f"Pranav is strong here.",
                    "signals": [growth["signal_name"]],
                    "seen_in": [growth["seen_in"]],
                    "paragraph": "z",
                }
            ],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("which is a growth edge" in v for v in violations)

    def test_a_strength_filed_under_still_growing_is_a_violation(self, evidence):
        strength = evidence["strengths"][0]
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            "still_growing": [
                {
                    "headline": "h",
                    "signals": [strength["signal_name"]],
                    "seen_in": [strength["seen_in"]],
                    "paragraph": "z",
                    "suggestion": {"because": "Because of this."},
                }
            ],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("which is a strength" in v for v in violations)


# ---------------------------------------------------------------------------
# LS2 - an activity is only credited with what it measured
# ---------------------------------------------------------------------------
class TestLS2SeenInIsHonest:
    def test_every_signal_names_exactly_the_activity_that_fired_it(self, evidence):
        display = {
            "logic": "Logic Quest",
            "spelling": "Word Wizard",
            "speaking": "Voice Challenge",
            "comprehension": "Story Explorer",
        }
        for signal in evidence["strengths"] + evidence["growth_edges"]:
            assert signal["seen_in"] == display[signal["activity"]]

    def test_an_area_lists_only_activities_that_produced_its_tags(self, evidence):
        for area in evidence["areas"]:
            produced = {s["seen_in"] for s in area["signals"]}
            assert set(area["seen_in"]) == produced

    def test_crediting_an_activity_that_did_not_measure_it_is_a_violation(
        self, evidence
    ):
        spelling_signal = next(
            s for s in evidence["growth_edges"] if s["activity"] == "spelling"
        )
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            "still_growing": [
                {
                    "headline": "h",
                    "signals": [spelling_signal["signal_name"]],
                    # Voice Challenge did not measure spelling conventions.
                    "seen_in": ["Word Wizard", "Voice Challenge"],
                    "paragraph": "z",
                    "suggestion": {"because": "Because of this."},
                }
            ],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("did not produce" in v for v in violations)


# ---------------------------------------------------------------------------
# LS3 - there is no Listening Channel
# ---------------------------------------------------------------------------
class TestLS3NoListeningChannel:
    def test_the_area_is_gone(self, evidence):
        names = [a["area"] for a in evidence["areas"]]
        display = [a["area_display_name"] for a in evidence["areas"]]
        assert "listening_channel" not in names
        assert not any("Listening" in d for d in display)

    def test_comprehension_tags_sit_under_comprehension(self, evidence):
        areas_by_tag = {
            s["tag"]: s["area"]
            for s in evidence["strengths"] + evidence["growth_edges"]
        }
        for tag in ("literal_comprehension_emerging", "vocabulary_in_context_emerging"):
            if tag in areas_by_tag:
                assert areas_by_tag[tag] == "reasoning_and_meaning"


# ---------------------------------------------------------------------------
# LS4 - count questions, not activities
# ---------------------------------------------------------------------------
class TestLS4CountQuestionsNotActivities:
    def test_thirteen_comprehension_questions_is_not_one_observation(self, evidence):
        comprehension = [
            s
            for s in evidence["strengths"] + evidence["growth_edges"]
            if s["activity"] == "comprehension"
        ]
        assert comprehension
        for signal in comprehension:
            assert signal["questions_behind"] >= 3
            assert signal["badge"] == "seen_repeatedly"

    def test_the_count_is_of_questions_behind_the_tag(self, evidence):
        for signal in evidence["strengths"] + evidence["growth_edges"]:
            assert signal["questions_behind"] >= 1


# ---------------------------------------------------------------------------
# LS5 / LS3 - the invented sections are gone
# ---------------------------------------------------------------------------
class TestLS5NoInventedSections:
    def test_what_helped_is_rejected(self, evidence):
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
            "what_helped": {"headline": "Strategic tasks", "signals": ["x"]},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("'what_helped' no longer exists" in v for v in violations)

    def test_what_helped_is_stripped_even_if_it_slips_through(self, evidence):
        letter = SnapshotWriter()._finalise(
            {"what_helped": {"headline": "x"}, "full_picture": [{}], "closing": "c"},
            evidence,
        )
        assert "what_helped" not in letter
        assert "full_picture" not in letter


# ---------------------------------------------------------------------------
# LS6 - no invented week of observation
# ---------------------------------------------------------------------------
class TestLS6NoInventedWeek:
    def test_the_evidence_reports_the_real_span(self, evidence):
        session = evidence["session"]
        assert session["span_minutes"] is not None
        assert session["same_sitting"] is True

    def test_this_week_is_rejected(self, evidence):
        letter = {
            "opening": {
                "headline": "A good sitting.",
                "paragraph": "This week, I had the pleasure of observing Pranav.",
            },
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("invented observation period" in v for v in violations)


# ---------------------------------------------------------------------------
# LS7 - a flawless activity gets its own observation
# ---------------------------------------------------------------------------
class TestLS7FlawlessActivitiesAreNamed:
    async def test_a_perfect_spelling_run_is_reported(
        self, client, child, mock_speech, mock_tts
    ):
        r = await client.post("/grade/", json={"grade": GRADE})
        words = r.json()["words"]
        await client.post(
            "/submit_words/",
            json={
                "idToken": child["token"],
                "child_id": child["child_id"],
                "grade": GRADE,
                "words": [
                    {
                        "word": w["word"],
                        "user_input": w["word"],
                        "type": w.get("type", "regular"),
                        "time": 8.0,
                        "hints_used": 0,
                    }
                    for w in words
                ],
            },
        )
        evidence = SnapshotService().build_evidence(
            child["token"], child["child_id"], GRADE
        )
        flawless = [f["activity"] for f in evidence["flawless_activities"]]
        assert "Word Wizard" in flawless

    def test_a_run_with_misses_is_not_called_flawless(self, evidence):
        flawless = [f["activity"] for f in evidence["flawless_activities"]]
        assert "Word Wizard" not in flawless


# ---------------------------------------------------------------------------
# LS8 - one voice for the child, and it is never a guess
# ---------------------------------------------------------------------------
class TestLS8Pronouns:
    def test_a_gendered_pronoun_is_rejected(self, evidence):
        letter = {
            "opening": {"headline": "x", "paragraph": "He read every word."},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("gendered pronoun" in v for v in violations)

    def test_they_is_accepted(self, evidence):
        letter = {
            "opening": {"headline": "x", "paragraph": "They read every word."},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert not any("gendered pronoun" in v for v in violations)

    def test_the_disclaimer_uses_them(self, evidence):
        letter = SnapshotWriter()._finalise({"closing": "c"}, evidence)
        assert "compares them to no one" in letter["disclaimer"]


class TestTheLetterIsWrittenInTheSingular:
    """A letter about one child reads like it is about one child.

    "They worked it out and they were pleased" is a form letter. When the
    profile records the child's pronouns, the letter uses them; when it does
    not, it uses the name and they/them rather than guessing.
    """

    @staticmethod
    def _letter(paragraph):
        return {
            "opening": {"headline": "x", "paragraph": paragraph},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }

    @staticmethod
    def _knowing(evidence, key):
        from app.services.pronouns import pronouns_for

        known = dict(evidence)
        known["pronouns"] = pronouns_for({"gender": key})
        return known

    def test_the_profile_decides_the_pronouns(self):
        from app.services.pronouns import pronouns_for

        assert pronouns_for({"gender": "boy"})["subject"] == "he"
        assert pronouns_for({"gender": "girl"})["object"] == "her"
        assert pronouns_for({"pronouns": "she/her"})["possessive"] == "her"
        assert pronouns_for({})["subject"] == "they"
        assert pronouns_for({"gender": ""})["known"] is False

    def test_a_name_never_decides_them(self):
        """A name is not a pronoun, and guessing misgenders a real child."""
        from app.services.pronouns import pronouns_for

        assert pronouns_for({"name": "Manju"})["known"] is False

    def test_his_pronouns_are_used_and_they_is_flagged(self, evidence):
        known = self._knowing(evidence, "boy")
        assert not [
            v for v in SnapshotWriter()._validate(
                self._letter("He read every word without stopping."), known
            )
            if "pronoun" in v
        ]
        violations = SnapshotWriter()._validate(
            self._letter("They read every word without stopping."), known
        )
        assert any("plural pronoun" in v for v in violations)

    def test_a_plural_pronoun_never_costs_the_letter(self, evidence):
        """It is a voice slip. The generic letter belongs to no child."""
        known = self._knowing(evidence, "girl")
        violations = [
            v for v in SnapshotWriter()._validate(
                self._letter("Their spelling is secure."), known
            )
            if "pronoun" in v
        ]
        assert violations and all(v.startswith("voice - ") for v in violations)

    def test_the_repair_leaves_a_known_childs_prose_alone(self, evidence):
        from app.services.snapshot_writer import _repair

        known = self._knowing(evidence, "boy")
        repaired = _repair(self._letter("He held the sound and kept going."), known)
        assert "He held the sound" in repaired["opening"]["paragraph"]

    def test_an_unknown_child_still_gets_they(self, evidence):
        from app.services.snapshot_writer import _repair

        repaired = _repair(self._letter("He was pleased with himself."), evidence)
        assert repaired["opening"]["paragraph"] == "They were pleased with themselves."

    def test_the_disclaimer_follows_the_childs_pronouns(self, evidence):
        known = self._knowing(evidence, "boy")
        letter = SnapshotWriter()._finalise({"closing": "c"}, known)
        assert "compares him to no one" in letter["disclaimer"]
        assert letter["meta"]["pronouns"] == "he"
        assert letter["meta"]["pronouns_known"] is True


class TestTheOpening:
    """The first thing a parent reads describes HOW their child works.

    Not what they scored - a count is a score however it is spelled - and
    not what they are. An opening that avoids counting by labelling has
    fixed nothing, so both are checked.
    """

    @staticmethod
    def _letter(headline, paragraph):
        return {
            "opening": {"headline": headline, "paragraph": paragraph},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }

    def _opening(self, evidence, headline, paragraph):
        return SnapshotWriter()._check_opening(
            self._letter(headline, paragraph), evidence
        )

    def _real_opening(self, evidence):
        """One built the way the specification asks, from this child's run."""
        could = evidence["could_mention"]
        word = could["words_written"][0]
        puzzle = could["puzzles"][0]
        return (
            "Pranav takes his time, and it usually pays off.",
            f"He spent nearly a minute on one word and wrote {word}, every "
            f"sound in it right. He stayed with {puzzle} rather than "
            "guessing when it got hard. Where he is still working is the "
            "spelling rules that sound does not reach.",
        )

    def test_the_specified_opening_passes(self, evidence):
        assert self._opening(evidence, *self._real_opening(evidence)) == []

    def test_a_count_is_rejected(self, evidence):
        violations = self._opening(
            evidence,
            "Pranav answered all 13 questions about the stories correctly.",
            "He worked steadily throughout.",
        )
        assert any("counts what the child got right or wrong" in v
                   for v in violations)

    def test_a_count_spelled_out_is_still_a_count(self, evidence):
        violations = self._opening(
            evidence,
            "Pranav spelled fifteen of fifteen words.",
            "He worked steadily throughout.",
        )
        assert any("counts what the child got right or wrong" in v
                   for v in violations)

    @pytest.mark.parametrize(
        "headline",
        [
            "Pranav has a keen eye for patterns and structures.",
            "Pranav has a knack for spotting what comes next.",
            "Pranav is a strong reader.",
            "Pranav showed a strong understanding of the stories.",
        ],
    )
    def test_saying_what_the_child_is_is_rejected(self, evidence, headline):
        """The second failure mode: avoiding a count by labelling instead."""
        violations = self._opening(evidence, headline, "He worked steadily.")
        assert any("says what the child IS" in v for v in violations)

    def test_an_activity_name_is_rejected(self, evidence):
        violations = self._opening(
            evidence,
            "Pranav works slowly and carefully.",
            "In Word Wizard he took his time over every word.",
        )
        assert any("names an activity" in v for v in violations)

    def test_an_opening_that_rests_on_one_activity_is_sent_back(self, evidence):
        word = evidence["could_mention"]["words_written"][0]
        violations = self._opening(
            evidence,
            "Pranav takes his time.",
            f"He spent nearly a minute on one word and wrote {word}. He is "
            "still working on the rules that sound does not reach.",
        )
        assert any("rests on one activity" in v for v in violations)

    def test_an_opening_that_hides_the_growth_edge_is_sent_back(self, evidence):
        could = evidence["could_mention"]
        violations = self._opening(
            evidence,
            "Pranav takes his time.",
            f"He spent nearly a minute on one word and wrote "
            f"{could['words_written'][0]}. He stayed with "
            f"{could['puzzles'][0]} rather than guessing.",
        )
        assert any("names nowhere this child is still working" in v
                   for v in violations)

    def test_neither_judgement_ever_costs_the_letter(self, evidence):
        """Both are worth asking again for. Neither is worth the fallback."""
        violations = self._opening(
            evidence,
            "Pranav takes his time.",
            f"He wrote {evidence['could_mention']['words_written'][0]}.",
        )
        assert violations
        assert all(v.startswith("voice - ") for v in violations)

    def test_the_opening_is_checked_as_part_of_the_letter(self, evidence):
        headline, paragraph = self._real_opening(evidence)
        letter = self._letter(headline, "In Word Wizard, " + paragraph)
        assert any("names an activity" in v
                   for v in SnapshotWriter()._validate(letter, evidence))


class TestNoCountsReachTheParent:
    """No tally of what a child got right or wrong, in digits or in words."""

    @staticmethod
    def _letter(paragraph):
        return {
            "opening": {"headline": "x", "paragraph": paragraph},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }

    @pytest.mark.parametrize(
        "phrase",
        [
            "He spelled 15 of 15 words.",
            "Fifteen of fifteen, including amputate.",
            "He answered all thirteen questions correctly.",
            "He read all eight sentences.",
            "Three questions came back wrong.",
            "That is 80% of them.",
        ],
    )
    def test_a_tally_is_rejected(self, evidence, phrase):
        violations = SnapshotWriter()._validate(self._letter(phrase), evidence)
        assert any("count of right or wrong" in v or "percentage" in v
                   or "score ratio" in v for v in violations)

    @pytest.mark.parametrize(
        "phrase",
        [
            "I sat with them for about twenty minutes, across four activities.",
            "They sat with it for thirty-three seconds and worked it out.",
            "One word a day, out loud.",
            "Four words on the fridge, read together once a day.",
            "Every word they wrote was spelled correctly.",
        ],
    )
    def test_how_they_worked_is_not_a_tally(self, evidence, phrase):
        violations = SnapshotWriter()._validate(self._letter(phrase), evidence)
        assert not any("count of right or wrong" in v for v in violations)

    def test_stage_a_reports_a_flawless_run_without_counting_it(self):
        from app.services.snapshot_service import SnapshotService

        flawless = SnapshotService._flawless_activities(
            {
                "spelling": {
                    "words_total": 15,
                    "words_correct": 15,
                    "misspellings": [],
                }
            },
            {"spelling": "Word Wizard"},
        )
        assert flawless
        # A fact, in a few words, and not a sentence the writer can lift.
        note = flawless[0]["nothing_to_fault"]
        assert not any(c.isdigit() for c in note)
        assert not note.endswith(".")


class TestTheLetterMatchesTheTemplate:
    """The frame every snapshot carries, and the note only some do."""

    def test_the_letter_is_framed_like_a_letter(self, evidence):
        letter = SnapshotWriter()._finalise({"closing": "c"}, evidence)
        assert letter["salutation"] == "Dear Parent,"
        assert letter["signature"] == "Eko"
        assert "trust yourself first" in letter["caveat"]

    def test_the_caveat_uses_the_real_length_of_the_sitting(self, evidence):
        from app.services.snapshot_writer import _caveat

        assert _caveat(
            {"child_name": "Sam", "session": {"span_phrase": "half an hour"}}
        ).startswith("Half an hour is a short time")
        assert "the Sam you know" in _caveat(
            {"child_name": "Sam", "session": {}}
        )

    def test_a_comfortable_set_earns_a_note_about_the_level(self):
        from app.services.snapshot_service import SnapshotService

        fit = SnapshotService._level_fit(
            {
                "spelling": {"words_total": 15, "words_correct": 15,
                             "misspellings": []},
                "comprehension": {"questions_answered": 14,
                                  "worked_out": [{}] * 13},
                "logic": {"questions_answered": 15,
                          "questions": [{"correct": True}] * 14
                          + [{"correct": False}]},
            },
            growth_edges=[],
        )
        assert fit["suggest"] == "the level above"

    def test_a_set_out_of_reach_points_downwards(self):
        from app.services.snapshot_service import SnapshotService

        fit = SnapshotService._level_fit(
            {
                "spelling": {"words_total": 15, "words_correct": 4,
                             "misspellings": [{}] * 11},
                "comprehension": {"questions_answered": 14,
                                  "worked_out": [{}] * 4},
                "logic": {"questions_answered": 15,
                          "questions": [{"correct": True}] * 6
                          + [{"correct": False}] * 9},
            },
            growth_edges=[{}] * 6,
        )
        assert fit["suggest"] == "the level below"

    def test_a_set_that_fitted_earns_no_note(self, evidence):
        assert not (evidence["level_fit"] or {}).get("suggest")

    def test_a_level_note_the_evidence_did_not_ask_for_is_dropped(self, evidence):
        from app.services.snapshot_writer import _repair

        letter = _repair(
            {
                "opening": {"headline": "x", "paragraph": "y"},
                "what_i_noticed": [],
                "still_growing": [],
                "for_the_conference": {"items": []},
                "level_note": {"headline": "One note about the level.",
                               "paragraph": "Try the level above."},
            },
            evidence,
        )
        assert "level_note" not in letter

    def test_a_quoted_spelling_the_child_never_wrote_is_dropped(self, evidence):
        from app.services.snapshot_writer import _repair

        real = evidence["what_the_child_did"]["spelling"]["misspellings"][0]
        letter = _repair(
            {
                "opening": {"headline": "x", "paragraph": "y"},
                "what_i_noticed": [
                    {
                        "headline": "h",
                        "quotes": [
                            {"wrote": real["attempt"], "for_word": real["word"]},
                            {"wrote": "skool", "for_word": "school"},
                        ],
                    }
                ],
                "still_growing": [],
                "for_the_conference": {"items": []},
            },
            evidence,
        )
        quotes = letter["what_i_noticed"][0]["quotes"]
        assert quotes == [{"wrote": real["attempt"], "for_word": real["word"]}]


class TestEverySentenceReadsRight:
    def test_the_mechanical_slips_are_fixed(self):
        from app.services.snapshot_writer import tidy_prose

        assert tidy_prose("he read  well , and and then he stopped.") == (
            "He read well, and then he stopped."
        )
        assert tidy_prose("It took a hour. a apple. an big word.") == (
            "It took an hour. An apple. A big word."
        )

    def test_a_one_off_keeps_its_article(self):
        from app.services.snapshot_writer import tidy_prose

        assert tidy_prose("That is a one-off.") == "That is a one-off."

    def test_the_tidy_pass_runs_over_the_letter(self, evidence):
        from app.services.snapshot_writer import _repair

        letter = _repair(
            {
                "opening": {"headline": "x", "paragraph": "they read  well ."},
                "what_i_noticed": [],
                "still_growing": [],
                "for_the_conference": {"items": []},
            },
            evidence,
        )
        assert letter["opening"]["paragraph"] == "They read well."


# ---------------------------------------------------------------------------
# LS10 - only real tag names
# ---------------------------------------------------------------------------
class TestLS10NoInventedSignalNames:
    def test_adaptability_does_not_exist(self, evidence):
        assert "Adaptability" not in evidence["allowed_signal_names"]

    def test_an_invented_name_is_rejected(self, evidence):
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [
                {
                    "headline": "h",
                    "signals": ["Adaptability"],
                    "seen_in": ["Logic Quest"],
                    "paragraph": "z",
                }
            ],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("does not exist: 'Adaptability'" in v for v in violations)

    def test_no_signal_name_carries_a_pronoun(self, evidence):
        """A signal name is copied verbatim into the letter.

        A pronoun inside one is a pronoun the writer cannot choose, and the
        pronoun repair then rewrites it into a name no tag has - which is
        exactly the invented-signal-name bug, introduced by the fix for it.
        """
        import re as _re

        config = json.load(
            open("data/tags/learning_areas.json", encoding="utf-8")
        )
        gendered = _re.compile(
            r"(he|she|his|her|hers|him|himself|herself|they|them|their)",
            _re.I,
        )
        carrying = {
            tag: name
            for tag, name in config["tag_display_names"].items()
            if gendered.search(name)
        }
        assert not carrying, carrying

    def test_the_pronoun_repair_leaves_signal_names_alone(self, evidence):
        from app.services.snapshot_writer import _neutralise_letter

        name = evidence["allowed_signal_names"][0]
        repaired = _neutralise_letter(
            {
                "what_i_noticed": [
                    {
                        "signals": [name],
                        "seen_in": ["Word Wizard"],
                        "paragraph": "He wrote fone. His sounds were right.",
                    }
                ]
            }
        )
        item = repaired["what_i_noticed"][0]
        assert item["signals"] == [name]
        assert item["seen_in"] == ["Word Wizard"]
        assert item["paragraph"] == "They wrote fone. Their sounds were right."

    def test_every_allowed_name_comes_from_a_real_tag(self, evidence):
        from app.tagging.config_loader import all_tag_definitions

        config = json.load(
            open("data/tags/learning_areas.json", encoding="utf-8")
        )
        names = config["tag_display_names"]
        real = set(all_tag_definitions())
        assert set(names) <= real
        for name in evidence["allowed_signal_names"]:
            assert name in set(names.values())


# ---------------------------------------------------------------------------
# The conference section
# ---------------------------------------------------------------------------
class TestConferenceSection:
    def test_a_conference_item_without_a_question_is_rejected(self, evidence):
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {
                "items": [
                    {"point": "a", "worth_asking": "Worth asking about X.",
                     "about": "strength"},
                    {"point": "b", "worth_asking": "Worth asking about Y.",
                     "about": "strength"},
                    {"point": "c"},
                    {"point": "d", "worth_asking": "Worth asking about Z.",
                     "about": "still_growing"},
                ]
            },
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("no question for the parent to ask" in v for v in violations)

    @pytest.mark.parametrize("count", [0, 1, 2, 3, 6])
    def test_a_section_that_is_not_four_or_five_items_is_rejected(self, evidence, count):
        """The headline promises four or five. Zero used to slip through.

        The count check was skipped when the list was empty, so a letter
        could carry a headline with nothing under it.

        This child's run found plenty, so the floor here is the full four.
        A run that found less lowers it - see the thin-run tests - because a
        floor the evidence cannot reach can only be met by inventing the
        difference.
        """
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {
                "headline": "Things you could mention",
                "items": [
                    {"point": str(i), "worth_asking": "Worth asking.",
                     "about": "strength" if i % 2 == 0 else "still_growing"}
                    for i in range(count)
                ],
            },
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("for_the_conference must hold" in v for v in violations), count

    @pytest.mark.parametrize("count", [4, 5])
    def test_four_or_five_items_is_accepted(self, evidence, count):
        letter = {
            "opening": {"headline": "x", "paragraph": "y"},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {
                "items": [
                    {"point": str(i), "worth_asking": "Worth asking.",
                     "about": "strength" if i % 2 == 0 else "still_growing"}
                    for i in range(count)
                ]
            },
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert not any("4 or 5 items" in v for v in violations), violations

    def test_the_generic_fallback_headline_promises_no_number(self, evidence):
        """It carries no items, so it must not say "three"."""
        letter = SnapshotWriter()._fallback(evidence)
        headline = letter["for_the_conference"]["headline"]
        assert not letter["for_the_conference"]["items"]
        assert "three" not in headline.lower()

    def test_reading_pace_is_available_to_the_conference_section(self, evidence):
        speaking = evidence["what_the_child_did"]["speaking"]
        assert speaking["words_correct_per_minute"] > 0
        assert speaking["pace_against_the_usual_band"] in (
            "in_band",
            "above_band",
            "below_band",
            "no_reading",
        )


# ---------------------------------------------------------------------------
# Part 4 - the words the child actually wrote
# ---------------------------------------------------------------------------
class TestPart4TheChildsOwnWords:
    def test_the_misspellings_reach_the_prompt(self, evidence):
        spelling = evidence["what_the_child_did"]["spelling"]
        attempts = {m["word"]: m["attempt"] for m in spelling["misspellings"]}
        assert attempts["clunk"] == "clunck"
        assert attempts["graph"] == "graff"
        assert attempts["phone"] == "fone"

    def test_the_convention_errors_are_named_as_such(self, evidence):
        spelling = evidence["what_the_child_did"]["spelling"]
        heard_right = {
            m["word"] for m in spelling["heard_right_spelled_by_another_rule"]
        }
        assert {"clunk", "graph", "phone"} <= heard_right

    def test_every_word_and_attempt_is_carried(self, evidence):
        spelling = evidence["what_the_child_did"]["spelling"]
        assert len(spelling["words"]) == 15
        assert all("word" in w and "attempt" in w for w in spelling["words"])

    def test_the_sentences_read_aloud_are_carried_with_their_tips(self, evidence):
        speaking = evidence["what_the_child_did"]["speaking"]
        assert speaking["sentences"]
        assert all(s["sentence"] for s in speaking["sentences"])
        # parent_tip used to be generated and thrown away.
        assert any(s["parent_tip"] for s in speaking["sentences"])

    def test_the_story_questions_are_carried_in_real_words(self, evidence):
        comprehension = evidence["what_the_child_did"]["comprehension"]
        assert comprehension["stories"]
        assert all(s["story_title"] for s in comprehension["stories"])
        worked_out = comprehension["worked_out"]
        assert worked_out
        assert all(w["question"] and w["answer"] for w in worked_out)
        assert any(w["kind"] == "inferential" for w in worked_out)

    def test_the_logic_items_carry_kind_difficulty_and_time(self, evidence):
        logic = evidence["what_the_child_did"]["logic"]
        assert logic["questions"]
        for question in logic["questions"]:
            assert question["kind"]
            assert question["difficulty"]
        assert logic["took_time_and_got_it_right"]


# ---------------------------------------------------------------------------
# The guardrail repairs what it can rather than discarding the letter
# ---------------------------------------------------------------------------
class TestRepairRatherThanDiscard:
    """A cosmetic slip must not cost the parent their whole letter.

    The generic fallback says nothing about this child. Falling back to it
    because the writer wrote one section too many, or one gendered pronoun,
    is a worse outcome than the slip. Anything deterministic is repaired;
    the fallback is kept for what only the writer can fix.
    """

    def test_too_many_noticed_items_are_trimmed_not_rejected(self, evidence):
        from app.services.snapshot_writer import _repair

        letter = _repair(
            {"what_i_noticed": [{"headline": str(i)} for i in range(9)]}
        )
        assert len(letter["what_i_noticed"]) == 4

    def test_a_leftover_section_is_dropped_not_rejected(self, evidence):
        from app.services.snapshot_writer import _repair

        letter = _repair(
            {"what_helped": {"headline": "Strategic tasks"}, "full_picture": [{}]}
        )
        assert "what_helped" not in letter
        assert "full_picture" not in letter

    def test_a_sixth_conference_item_is_trimmed(self, evidence):
        from app.services.snapshot_writer import _repair

        letter = _repair(
            {"for_the_conference": {"items": [{"point": str(i)} for i in range(7)]}}
        )
        assert len(letter["for_the_conference"]["items"]) == 5

    def test_a_repaired_letter_then_passes_the_guardrail(self, evidence):
        from app.services.snapshot_writer import _repair

        raw = {
            "opening": _compliant_opening(evidence),
            "what_i_noticed": [{"headline": str(i), "signals": [], "seen_in": []}
                               for i in range(9)],
            "still_growing": _one_grouped_growth_item(evidence),
            "for_the_conference": _balanced_conference(),
            "what_helped": {"headline": "Strategic tasks"},
        }
        violations = SnapshotWriter()._validate(_repair(raw), evidence)
        assert not violations, violations


class TestTheLetterIsSpecificEveryTime:
    """Consistency: the same evidence should not give a good letter one run
    and a vague one the next.

    The guardrails used to check only what must NOT appear, so a letter that
    said "they are developing this skill" about everything passed cleanly.
    What makes the letter worth paying for - the child's own words - was
    asked for in the prompt and never checked. Now it is checked.
    """

    def test_stage_a_names_the_facts_the_letter_must_carry(self, evidence):
        required = evidence["must_mention"]
        assert required
        words = next(
            r for r in required if "spelled by sound" in r["what"]
        )
        assert set(words["any_of"]) >= {"clunck", "graff", "fone"}

    def test_the_story_is_named_among_them(self, evidence):
        titles = [r for r in evidence["must_mention"] if "story" in r["what"]]
        assert titles
        assert "The Treasure Map" in titles[0]["any_of"]

    def test_a_vague_letter_is_rejected(self, evidence):
        """This is the run that used to reach a parent."""
        from app.services.snapshot_writer import missing_required_facts

        vague = {
            "opening": {
                "headline": "A good sitting.",
                "paragraph": "They are developing their skills nicely.",
            },
            "what_i_noticed": [],
            "still_growing": [
                {
                    "headline": g["signal_name"],
                    "signals": [g["signal_name"]],
                    "seen_in": [g["seen_in"]],
                    "paragraph": "This is still growing.",
                    "suggestion": {"because": "Because of this."},
                }
                for g in evidence["growth_edges"]
            ],
            "for_the_conference": {
                "items": [{"point": str(i), "worth_asking": "Worth asking."}
                          for i in range(3)]
            },
        }
        assert missing_required_facts(vague, evidence)
        assert SnapshotWriter()._validate(vague, evidence)

    def test_a_specific_letter_is_accepted(self, evidence):
        from app.services.snapshot_writer import missing_required_facts

        letter = {
            "opening": {
                "headline": "Pranav spells by sound.",
                "paragraph": (
                    "Pranav wrote fone for phone and graff for graph. In "
                    "The Treasure Map they chose The oak tree. Where they "
                    "are still working is the rules that sound does not "
                    "reach."
                ),
            },
            "what_i_noticed": [],
            "still_growing": _one_grouped_growth_item(evidence),
            "for_the_conference": _balanced_conference(),
        }
        assert not missing_required_facts(letter, evidence)
        assert not SnapshotWriter()._validate(letter, evidence)

    def test_a_specific_draft_outranks_a_vague_one(self, evidence):
        from app.services.snapshot_writer import specificity

        vague = {"opening": {"paragraph": "They are developing well."}}
        specific = {
            "opening": {
                "paragraph": (
                    "They wrote clunck for clunk and graff for graph, and in "
                    "The Treasure Map they chose The oak tree."
                )
            }
        }
        assert specificity(specific, evidence) > specificity(vague, evidence)
        assert specificity(vague, evidence) == 0

    def test_the_meta_reports_how_specific_the_letter_was(self, evidence):
        letter = SnapshotWriter()._finalise({"closing": "c"}, evidence, specificity=9)
        assert letter["meta"]["specificity"] == 9

    def test_a_child_with_nothing_to_quote_is_not_blocked(self, evidence):
        """A flawless speller has no misspellings. That must not fail."""
        from app.services.snapshot_writer import missing_required_facts

        empty = dict(evidence)
        empty["must_mention"] = []
        assert not missing_required_facts({"opening": {"paragraph": "x"}}, empty)


class TestVoiceSlipsNeverCostTheLetter:
    """A guardrail protects the child, not the prose.

    Every promise the product makes - no scores, no labels, no comparison,
    no correction, no praise over a growth edge - is worth withholding a
    letter for. "Impressive" is not. A parent handed the generic fallback
    learns nothing about their own child, which is a worse outcome than an
    adjective Eko would not have chosen.
    """

    @staticmethod
    def _otherwise_clean(evidence, paragraph):
        """A letter that breaks nothing except the sentence under test.

        It has to carry the required facts as well: since specificity became
        a guardrail, a letter that quotes nothing is no longer clean.
        """
        opening = _compliant_opening(evidence)
        opening["paragraph"] = paragraph + " " + opening["paragraph"]
        return {
            "opening": opening,
            "what_i_noticed": _enough_noticed(evidence),
            "still_growing": _one_grouped_growth_item(evidence),
            "for_the_conference": _balanced_conference(),
        }

    def test_an_adjective_is_reported_as_voice_not_harm(self, evidence):
        from app.services.snapshot_writer import _STYLE_PREFIX

        letter = self._otherwise_clean(evidence, "That was impressive.")
        violations = SnapshotWriter()._validate(letter, evidence)
        assert violations
        assert all(v.startswith(_STYLE_PREFIX) for v in violations), violations

    def test_a_score_is_reported_as_harm_not_voice(self, evidence):
        from app.services.snapshot_writer import _STYLE_PREFIX

        letter = self._otherwise_clean(evidence, "They scored 80%.")
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any(not v.startswith(_STYLE_PREFIX) for v in violations), violations

    def test_an_otherwise_clean_letter_breaks_nothing(self, evidence):
        letter = self._otherwise_clean(evidence, "Every sound is right.")
        assert not SnapshotWriter()._validate(letter, evidence)

    def test_an_exclamation_mark_is_repaired_not_reported(self, evidence):
        from app.services.snapshot_writer import _repair

        letter = _repair({"opening": {"paragraph": "They did it! Every word!"}})
        assert "!" not in letter["opening"]["paragraph"]
        assert letter["opening"]["paragraph"] == "They did it. Every word."

    def test_an_unearned_activity_is_struck_not_reported(self, evidence):
        """LS2 is Stage A's fact, so there is nothing to ask the writer."""
        from app.services.snapshot_writer import _repair

        signal = evidence["strengths"][0]
        letter = _repair(
            {
                "what_i_noticed": [
                    {
                        "signals": [signal["signal_name"]],
                        "seen_in": [signal["seen_in"], "Story Explorer",
                                    "Voice Challenge"],
                    }
                ]
            },
            evidence,
        )
        assert letter["what_i_noticed"][0]["seen_in"] == [signal["seen_in"]]

    def test_seen_in_is_never_emptied(self, evidence):
        from app.services.snapshot_writer import _repair

        signal = evidence["strengths"][0]
        letter = _repair(
            {"what_i_noticed": [{"signals": [signal["signal_name"]],
                                 "seen_in": ["Story Explorer"]}]},
            evidence,
        )
        assert letter["what_i_noticed"][0]["seen_in"] == [signal["seen_in"]]

    def test_the_meta_records_any_voice_slip(self, evidence):
        letter = SnapshotWriter()._finalise(
            {"closing": "c"}, evidence,
            style_slips=["voice - evaluation instead of observation: 'impressive'"],
        )
        assert letter["meta"]["voice_slips"]

    def test_a_clean_letter_records_no_slip(self, evidence):
        letter = SnapshotWriter()._finalise({"closing": "c"}, evidence)
        assert letter["meta"]["voice_slips"] == []


class TestSuggestionsMayTalkAboutWeeks:
    """LS6 is about an invented history, not about the word "week".

    "Read together for a few minutes each week" is advice to a parent. A
    guardrail that rejects it discards the letter over a suggestion doing
    exactly what a suggestion should do.
    """

    @pytest.mark.parametrize(
        "phrase,flagged",
        [
            ("Read together for a few minutes each week.", False),
            ("Practise this every week at bedtime.", False),
            ("This week, I had the pleasure of observing Pranav.", True),
            ("In each session we worked on this.", True),
            ("Our sessions covered a lot of ground.", True),
        ],
    )
    def test_only_an_invented_history_is_rejected(self, evidence, phrase, flagged):
        letter = {
            "opening": {"headline": "x", "paragraph": phrase},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        hit = any("invented observation period" in v for v in violations)
        assert hit is flagged, (phrase, violations)


# ---------------------------------------------------------------------------
# The correction-tone guardrail
# ---------------------------------------------------------------------------
class TestCorrectionTone:
    @pytest.mark.parametrize(
        "phrase",
        [
            "Pranav got these wrong.",
            "Pranav needs to work on spelling.",
            "The correct spelling is phone.",
            "Pranav struggled with the vowel sounds.",
            "This is a weakness.",
        ],
    )
    def test_a_correction_is_rejected(self, evidence, phrase):
        letter = {
            "opening": {"headline": "x", "paragraph": phrase},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("reads as a correction" in v for v in violations), phrase

    def test_an_explanation_is_accepted(self, evidence):
        letter = {
            "opening": {
                "headline": "Pranav spells what they hear.",
                "paragraph": (
                    "Pranav wrote fone for phone and graff for graph. Say "
                    "those out loud. Every sound is right. What they have "
                    "not met yet is the rule that some /f/ sounds are "
                    "spelled ph."
                ),
            },
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert not any("reads as a correction" in v for v in violations), violations

    def test_an_exclamation_mark_is_rejected(self, evidence):
        letter = {
            "opening": {"headline": "What a delight", "paragraph": "Wonderful work!"},
            "what_i_noticed": [],
            "still_growing": [],
            "for_the_conference": {"items": []},
        }
        violations = SnapshotWriter()._validate(letter, evidence)
        assert any("exclamation mark" in v for v in violations)
