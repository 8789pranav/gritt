"""End-to-end test of the Learning Snapshot pipeline.

Tests Stage A (deterministic evidence) with mocked assessment results,
and Stage B (guardrails) with a mocked LLM response.
"""
import sys
sys.path.insert(0, "Z:/grittt")

import json
from unittest.mock import MagicMock, patch

from app.services.snapshot_service import SnapshotService
from app.services.snapshot_writer import SnapshotWriter

passed = 0
failed = 0

def check(label, cond, extra=""):
    global passed, failed
    if cond:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label} {extra}")
        failed += 1


# ---------------------------------------------------------------------
# Mock assessment results — a child who did well overall
# ---------------------------------------------------------------------
LOGIC_RESULT = {
    "dear_parent_tags": [
        {"id": "pattern_detection_strong", "polarity": "strength", "description": "Recognises patterns."},
        {"id": "deliberate_pace", "polarity": "neutral", "description": "Takes time on hard items."},
        {"id": "relational_reasoning_present", "polarity": "strength", "description": "Connects ideas."},
    ],
    "signals": {
        "pattern_accuracy": 1.0, "pattern_items_count": 3,
        "relational_accuracy": 0.67, "relational_items_count": 3,
        "slow_and_correct_count": 2, "total_items": 15, "correct_answers": 13,
    },
    "per_item_tags": [{"item_id": f"l{i}", "answered": True, "is_correct": True, "tags": []} for i in range(15)],
    "scored_items": [],
}

SPELLING_RESULT = {
    "dear_parent_tags": [
        {"id": "phonetic_strategy_strong", "polarity": "strength", "description": "Builds words from sounds."},
        {"id": "blend_competent", "polarity": "strength", "description": "Handles blends."},
        {"id": "spelling_convention_emerging", "polarity": "growth_edge", "description": "Conventions developing."},
    ],
    "signals": {
        "vowel_accuracy": 0.94, "beginning_accuracy": 1.0,
        "convention_error_count": 3,
    },
    "per_word_tags": [],
    "scored_items": [],
}

SPEAKING_RESULT = {
    "dear_parent_tags": [
        {"id": "decoding_accurate", "polarity": "strength", "description": "Decodes accurately."},
        {"id": "expression_flat", "polarity": "growth_edge", "description": "Expression developing."},
        {"id": "self_corrects_while_reading", "polarity": "strength", "description": "Self-corrects."},
        {"id": "ending_sounds_emerging", "polarity": "growth_edge", "description": "Endings slip."},
    ],
    "signals": {
        "accuracy_score": 0.92, "prosody_score": 0.61, "fluency_score": 0.88,
    },
    "sentences": [],
}

COMPREHENSION_RESULT = {
    "dear_parent_tags": [
        {"id": "inferential_comprehension_strong", "polarity": "strength", "description": "Reads between lines."},
        {"id": "literal_comprehension_strong", "polarity": "strength", "description": "Recalls facts."},
        {"id": "vocabulary_in_context_strong", "polarity": "strength", "description": "Works out word meanings."},
    ],
    "signals": {
        "literal_accuracy": 1.0, "inferential_accuracy": 1.0,
        "vocabulary_accuracy": 1.0, "stories_attempted": 2,
    },
    "per_question_tags": [],
    "scored_items": [],
}

MOCK_RESULTS = {
    "logic": LOGIC_RESULT,
    "spelling": SPELLING_RESULT,
    "speaking": SPEAKING_RESULT,
    "comprehension": COMPREHENSION_RESULT,
}


print("=" * 70)
print("STAGE A: Deterministic evidence pipeline")
print("=" * 70)

svc = SnapshotService()

# Patch ScoreRepository.get_latest to return our mocks.
with patch.object(svc._scores, "get_latest", side_effect=lambda uid, cid, key, grade=None: MOCK_RESULTS.get(
    {"logic_tests": "logic", "scores": "spelling", "speaking_tests": "speaking", "comprehension_tests": "comprehension"}.get(key, key)
)):
    with patch("app.services.snapshot_service.verify_paid_child", return_value=("uid", {"name": "Aria"})):
        evidence = svc.build_evidence("token", "child_1", "kindergarten")

print(f"  Child: {evidence['child_name']}")
print(f"  Tests completed: {evidence['tests_completed']}")
print(f"  Observations (strengths): {len(evidence['observations'])}")
print(f"  Growth edges: {len(evidence['growth_edges'])}")
print(f"  Full picture areas: {len(evidence['full_picture_areas'])}")

check("child_name is Aria", evidence["child_name"] == "Aria")
check("all 4 tests completed", len(evidence["tests_completed"]) == 4)
check("at least 1 strength", len(evidence["observations"]) >= 1)
check("at least 1 growth edge", len(evidence["growth_edges"]) >= 1)
check("max 3 strengths", len(evidence["observations"]) <= 3)
check("max 3 growth edges", len(evidence["growth_edges"]) <= 3)

for obs in evidence["observations"] + evidence["growth_edges"]:
    print(f"\n  Area: {obs['area_display_name']} ({obs['polarity']}, {obs['evidence_strength']})")
    print(f"    seen_in: {obs['seen_in']}")
    print(f"    tags: {obs['tags']}")
    check(f"{obs['area']}: has seen_in", len(obs["seen_in"]) >= 1)
    check(f"{obs['area']}: has tags", sum(len(v) for v in obs["tags"].values()) >= 1)
    check(f"{obs['area']}: has evidence_detail", len(obs.get("evidence_detail", {})) >= 1)
    if obs["evidence_strength"] == "seen_more_than_once":
        check(f"{obs['area']}: seen_more_than_once has 2+ tests", len(obs["tags"]) >= 2)


print()
print("=" * 70)
print("STAGE B: Guardrail validation")
print("=" * 70)

writer = SnapshotWriter()

# A letter that violates the guardrails.
BAD_LETTER = {
    "opening": {
        "headline": "Aria scored 95%.",
        "paragraph": "She is above grade level compared to other children.",
    },
    "what_i_noticed": [
        {"headline": "x", "area_display_name": "y", "paragraph": "z", "seen_in": ["Nowhere"], "learning_signals": []},
        {"headline": "x", "area_display_name": "y", "paragraph": "z", "seen_in": [], "learning_signals": []},
        {"headline": "x", "area_display_name": "y", "paragraph": "z", "seen_in": [], "learning_signals": []},
        {"headline": "x", "area_display_name": "y", "paragraph": "z", "seen_in": [], "learning_signals": []},
    ],
    "what_helped": {"headline": "Time.", "signals": []},
    "still_growing": [
        {"headline": "x", "paragraph": "y", "suggestion": {"title": "t", "body": "b", "because": ""}},
    ],
    "full_picture": [],
    "closing": "Done.",
}

violations = writer._validate(BAD_LETTER, evidence)
print(f"  Violations found: {violations}")
check("percentage detected", any("percentage" in v for v in violations))
check("grade label detected", any("grade label" in v for v in violations))
check("comparison detected", any("comparison" in v for v in violations))
check("too many noticed items detected", any("more than 3" in v for v in violations))
check("missing 'because' detected", any("because" in v for v in violations))
check("unknown seen_in detected", any("unknown test" in v for v in violations))

# A clean letter passes.
GOOD_LETTER = {
    "opening": {
        "headline": "Aria stayed with the hardest problems.",
        "paragraph": "She worked through them carefully.",
    },
    "what_i_noticed": [
        {
            "headline": "She stays with a hard problem",
            "area_display_name": "Pace & Approach",
            "paragraph": "She took her time and worked them out.",
            "seen_in": ["Logic Quest"],
            "learning_signals": ["Takes thinking time"],
        },
    ],
    "what_helped": {"headline": "Time.", "signals": ["Thinking time"]},
    "still_growing": [
        {
            "headline": "Growing into expression",
            "paragraph": "Expression is still developing.",
            "suggestion": {
                "title": "Read aloud together.",
                "body": "Make it fun.",
                "because": "Because expression is still developing.",
            },
        },
    ],
    "full_picture": [],
    "closing": "This is a starting point.",
}

violations = writer._validate(GOOD_LETTER, evidence)
print(f"  Clean letter violations: {violations}")
check("clean letter passes", violations == [], f"violations={violations}")


print()
print("=" * 70)
print("STAGE B: Fallback letter (LLM unavailable)")
print("=" * 70)

with patch.object(SnapshotWriter, "is_configured", property(lambda self: False)):
    fb_writer = SnapshotWriter()
    letter = fb_writer.write(evidence)
    print(f"  Fallback keys: {list(letter.keys())}")
    print(f"  meta: {letter.get('meta')}")
    check("fallback returns a letter", isinstance(letter, dict))
    check("fallback marks llm_generated=False", letter["meta"]["llm_generated"] is False)
    check("fallback has disclaimer", "not a diagnosis" in letter["disclaimer"].lower())
    check("fallback has branding", letter["branding"] == "The Dear Parent Project")


print()
print("=" * 70)
print("STAGE B: Finalise (name interpolation)")
print("=" * 70)

final = writer._finalise(json.loads(json.dumps(GOOD_LETTER)), evidence)
check("finalise adds branding", final["branding"] == "The Dear Parent Project")
check("finalise adds disclaimer with name", "Aria" in final["disclaimer"])
check("finalise adds meta", "meta" in final)
check("meta marks llm_generated", final["meta"]["llm_generated"] is True)


print()
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 70)
sys.exit(1 if failed else 0)
