"""Generate the learning areas config for the Learning Snapshot."""
import json

CONFIG = {
    "schema_version": "1.0",
    "areas": {
        "pace_and_approach": {
            "display_name": "Pace & Approach",
            "description": "How your child works: speed, persistence, and how they adapt when something is hard.",
            "sources": {
                "logic": [
                    "deliberate_pace", "impulsive_response", "self_correction_present",
                    "trial_and_error_strategy"
                ],
                "spelling": ["rushed_spelling"],
                "speaking": ["self_corrects_while_reading", "hesitates_before_starting"]
            }
        },
        "patterns_and_structure": {
            "display_name": "Patterns & Structure",
            "description": "Recognising patterns, building words from sounds, and switching rules when the task changes.",
            "sources": {
                "logic": [
                    "pattern_detection_strong", "pattern_detection_emerging",
                    "systematic_problem_solving", "systematic_problem_solving_emerging",
                    "flexible_strategy_use", "flexible_strategy_emerging",
                    "rule_maintenance_difficulty"
                ],
                "spelling": [
                    "phonetic_strategy_strong", "digraph_competent", "blend_competent",
                    "digraph_emerging", "blend_emerging",
                    "sight_word_recognition_strong", "sight_word_emerging"
                ],
                "speaking": [
                    "vowel_sounds_secure", "short_vowel_emerging", "long_vowel_emerging",
                    "blends_secure", "blends_emerging",
                    "digraphs_secure", "digraphs_emerging", "ending_sounds_emerging"
                ]
            }
        },
        "reasoning_and_meaning": {
            "display_name": "Reasoning & Meaning",
            "description": "Working out what a story implies, connecting ideas, and holding several things in mind at once.",
            "sources": {
                "logic": [
                    "relational_reasoning_present", "relational_reasoning_emerging",
                    "reasoning_under_load", "reasoning_under_load_emerging"
                ],
                "comprehension": [
                    "inferential_comprehension_strong", "inferential_comprehension_emerging"
                ]
            }
        },
        "language_and_expression": {
            "display_name": "Language & Expression",
            "description": "Reading aloud with expression, pronouncing words clearly, and spelling conventions.",
            "sources": {
                "speaking": [
                    "decoding_accurate", "decoding_emerging",
                    "reading_rate_on_track", "reading_rate_slow",
                    "phrasing_smooth", "phrasing_choppy",
                    "expression_present", "expression_flat",
                    "reads_every_word", "skips_words",
                    "stretches_words", "filler_habit_emerging"
                ],
                "spelling": ["spelling_convention_emerging", "vowel_accuracy_strong", "vowel_emerging"]
            }
        },
        "listening_channel": {
            "display_name": "Listening Channel",
            "description": "Following a story by ear and holding onto details across the whole passage.",
            "sources": {
                "comprehension": [
                    "literal_comprehension_strong", "literal_comprehension_emerging",
                    "vocabulary_in_context_strong", "vocabulary_in_context_emerging",
                    "inconsistent_across_stories"
                ]
            }
        }
    },
    "test_display_names": {
        "logic": "Logic Quest",
        "spelling": "Word Wizard",
        "speaking": "Voice Challenge",
        "comprehension": "Story Explorer"
    }
}

with open("Z:/grittt/data/tags/learning_areas.json", "w", encoding="utf-8") as f:
    json.dump(CONFIG, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("Wrote data/tags/learning_areas.json")

# Validate against actual tag files
for test in ["logic", "spelling", "speaking", "comprehension"]:
    tags_file = json.load(open(f"Z:/grittt/data/tags/{test}_tags.json", encoding="utf-8"))
    actual_ids = {t["id"] for t in tags_file["tags"]}
    mapped = set()
    for area in CONFIG["areas"].values():
        mapped.update(area["sources"].get(test, []))
    unknown = mapped - actual_ids
    unused = actual_ids - mapped
    print(f"\n{test}:")
    print(f"  mapped: {len(mapped)}, actual: {len(actual_ids)}")
    if unknown:
        print(f"  UNKNOWN (mapped but not in tag file): {sorted(unknown)}")
    if unused:
        print(f"  unused (in tag file but not mapped): {sorted(unused)}")
