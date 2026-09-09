"""Show the exact API response from POST /snapshot/."""
import sys
sys.path.insert(0, "Z:/grittt")

import json
from unittest.mock import patch

from app.services.snapshot_service import SnapshotService
from app.services.snapshot_writer import SnapshotWriter

MOCK_RESULTS = {
    "logic": {
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
        "per_item_tags": [], "scored_items": [],
    },
    "spelling": {
        "dear_parent_tags": [
            {"id": "phonetic_strategy_strong", "polarity": "strength", "description": "Builds words from sounds."},
            {"id": "blend_competent", "polarity": "strength", "description": "Handles blends."},
            {"id": "spelling_convention_emerging", "polarity": "growth_edge", "description": "Conventions developing."},
        ],
        "signals": {
            "vowel_accuracy": 0.94, "beginning_accuracy": 1.0,
            "convention_error_count": 3,
        },
        "per_word_tags": [], "scored_items": [],
    },
    "speaking": {
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
    },
    "comprehension": {
        "dear_parent_tags": [
            {"id": "inferential_comprehension_strong", "polarity": "strength", "description": "Reads between lines."},
            {"id": "literal_comprehension_strong", "polarity": "strength", "description": "Recalls facts."},
            {"id": "vocabulary_in_context_strong", "polarity": "strength", "description": "Works out word meanings."},
        ],
        "signals": {
            "literal_accuracy": 1.0, "inferential_accuracy": 1.0,
            "vocabulary_accuracy": 1.0, "stories_attempted": 2,
        },
        "per_question_tags": [], "scored_items": [],
    },
}

KEY_MAP = {
    "logic_tests": "logic", "scores": "spelling",
    "speaking_tests": "speaking", "comprehension_tests": "comprehension",
}

svc = SnapshotService()

with patch.object(svc._scores, "get_latest",
                  side_effect=lambda uid, cid, key, grade=None: MOCK_RESULTS.get(KEY_MAP.get(key, key))):
    with patch("app.services.snapshot_service.verify_paid_child",
               return_value=("uid", {"name": "Aria"})):
        evidence = svc.build_evidence("token", "child_1", "kindergarten")

writer = SnapshotWriter()
letter = writer.write(evidence)

# The exact response shape POST /snapshot/ returns.
response = {
    "success": True,
    "child_id": "child_1",
    "child_name": evidence["child_name"],
    "grade": evidence.get("grade"),
    "tests_completed": evidence["tests_completed"],
    "snapshot": letter,
}

print(json.dumps(response, indent=2, ensure_ascii=False))
