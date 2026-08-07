"""
Validates every question bank under ``data/questions``.

Checks structural invariants that the engines rely on at runtime:

* the standard envelope keys are present and ``count`` matches the payload
* identifiers are unique within a grade and across the whole test
* answer indices point at a real option
* logic items reference a known cognitive tag and difficulty

Exit code is non-zero when any check fails, so this is safe to wire into CI.

Run from the repository root::

    python scripts/verify_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_DIR = REPO_ROOT / "data" / "questions"
TAGS_DIR = REPO_ROOT / "data" / "tags"

VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_WORD_TYPES = {"regular", "nonsense", "sight"}

# Item collection key per test, plus the field holding each item's identifier.
# ``global_id`` marks tests whose identifiers must be unique across every grade
# file. Spelling is excluded because the same word may legitimately appear in
# more than one grade's word list.
TEST_SPECS: Dict[str, Dict[str, Any]] = {
    "logic": {"items_key": "items", "id_field": "item_id", "global_id": True},
    "spelling": {"items_key": "words", "id_field": "word", "global_id": False},
    "speaking": {"items_key": "sentences", "id_field": "sentence_id", "global_id": True},
    "comprehension": {"items_key": "stories", "id_field": "story_id", "global_id": True},
}


class Report:
    """Collects failures and warnings across all files."""

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")

    @property
    def ok(self) -> bool:
        return not self.errors


def load_known_tags() -> set[str]:
    """Collect every tag id declared across the per-test tag configs."""
    tags: set[str] = set()
    if not TAGS_DIR.exists():
        return tags
    for path in TAGS_DIR.glob("*_tags.json"):
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for tag in config.get("tags", []):
            tag_id = tag.get("id")
            if tag_id:
                tags.add(tag_id)
    return tags


def check_envelope(report: Report, where: str, doc: Dict[str, Any], test: str) -> List[Any]:
    """Validate the shared envelope and return the item collection."""
    for key in ("schema_version", "test", "grade", "count"):
        if key not in doc:
            report.error(where, f"missing envelope key '{key}'")

    if doc.get("test") != test:
        report.error(where, f"test is '{doc.get('test')}', expected '{test}'")

    items_key = TEST_SPECS[test]["items_key"]
    items = doc.get(items_key)
    if not isinstance(items, list):
        report.error(where, f"missing or invalid '{items_key}' list")
        return []

    if doc.get("count") != len(items):
        report.error(where, f"count={doc.get('count')} but found {len(items)} items")

    if not items:
        report.warn(where, "file contains no items")

    return items


def check_options(report: Report, where: str, item: Dict[str, Any], label: str) -> None:
    """Validate an options list and its correct-answer pointer."""
    options = item.get("options")
    if not isinstance(options, list) or not options:
        report.error(where, f"{label}: missing options")
        return

    if len(options) < 2:
        report.error(where, f"{label}: only {len(options)} option(s)")

    for position, option in enumerate(options):
        if isinstance(option, dict):
            if option.get("index") != position:
                report.error(
                    where,
                    f"{label}: option at position {position} has index {option.get('index')}",
                )
            if not str(option.get("text", "")).strip():
                report.error(where, f"{label}: option {position} has empty text")
        elif not str(option).strip():
            report.error(where, f"{label}: option {position} is empty")

    index_field = "correct_answer_index" if "correct_answer_index" in item else "correct_index"
    correct = item.get(index_field)
    if not isinstance(correct, int):
        report.error(where, f"{label}: missing '{index_field}'")
    elif not 0 <= correct < len(options):
        report.error(
            where,
            f"{label}: {index_field}={correct} out of range (0..{len(options) - 1})",
        )


def check_logic(report: Report, where: str, items: List[Any], known_tags: set[str]) -> None:
    for item in items:
        label = item.get("item_number") or item.get("item_id") or "<unknown>"

        for key in ("item_id", "item_number", "item_type", "question_text", "primary_tag"):
            if not str(item.get(key, "")).strip():
                report.error(where, f"{label}: missing '{key}'")

        check_options(report, where, item, label)

        difficulty = item.get("difficulty")
        if difficulty not in VALID_DIFFICULTIES:
            report.error(where, f"{label}: invalid difficulty '{difficulty}'")

        latency = item.get("expected_latency_seconds")
        if not isinstance(latency, int) or latency <= 0:
            report.error(where, f"{label}: invalid expected_latency_seconds '{latency}'")

        tag = item.get("primary_tag")
        if known_tags and tag not in known_tags:
            report.error(where, f"{label}: unknown primary_tag '{tag}'")


def check_spelling(report: Report, where: str, items: List[Any]) -> None:
    for item in items:
        label = item.get("word", "<unknown>")

        if not str(item.get("word", "")).strip():
            report.error(where, "an entry has an empty 'word'")

        word_type = item.get("type")
        if word_type not in VALID_WORD_TYPES:
            report.error(where, f"{label}: invalid type '{word_type}'")

        if not str(item.get("sentence", "")).strip():
            report.warn(where, f"{label}: no example sentence")

        if word_type == "regular" and not item.get("features"):
            report.warn(where, f"{label}: regular word has no scoreable features")


def check_speaking(report: Report, where: str, items: List[Any]) -> None:
    for item in items:
        label = item.get("sentence_id", "<unknown>")

        sentence = str(item.get("sentence", "")).strip()
        if not sentence:
            report.error(where, f"{label}: empty sentence")
            continue

        actual_words = len(sentence.split())
        declared = item.get("word_count")
        if declared != actual_words:
            report.warn(
                where, f"{label}: word_count={declared} but sentence has {actual_words}"
            )

        if item.get("difficulty") not in VALID_DIFFICULTIES:
            report.error(where, f"{label}: invalid difficulty '{item.get('difficulty')}'")


def check_comprehension(report: Report, where: str, items: List[Any]) -> None:
    seen_questions: set[str] = set()

    for story in items:
        label = story.get("story_id", "<unknown>")

        for key in ("story_id", "title", "story_text"):
            if not str(story.get(key, "")).strip():
                report.error(where, f"{label}: missing '{key}'")

        questions = story.get("questions")
        if not isinstance(questions, list) or not questions:
            report.error(where, f"{label}: has no questions")
            continue

        for question in questions:
            q_label = f"{label}/{question.get('question_id', '?')}"

            if not str(question.get("question", "")).strip():
                report.error(where, f"{q_label}: empty question text")

            q_id = question.get("question_id")
            if not q_id:
                report.error(where, f"{q_label}: missing question_id")
            elif q_id in seen_questions:
                report.error(where, f"{q_label}: duplicate question_id")
            else:
                seen_questions.add(q_id)

            check_options(report, where, question, q_label)


CHECKERS = {
    "spelling": check_spelling,
    "speaking": check_speaking,
    "comprehension": check_comprehension,
}


def main() -> int:
    if not QUESTIONS_DIR.exists():
        print(f"error: {QUESTIONS_DIR} not found", file=sys.stderr)
        return 1

    report = Report()
    known_tags = load_known_tags()
    if known_tags:
        print(f"loaded {len(known_tags)} known tag ids from data/tags/\n")
    else:
        print("no tag configs found - skipping primary_tag validation\n")

    total_items = 0

    for test, spec in TEST_SPECS.items():
        test_dir = QUESTIONS_DIR / test
        if not test_dir.exists():
            report.error(test, "directory not found")
            continue

        paths = sorted(test_dir.glob("*.json"))
        if not paths:
            report.error(test, "no JSON files found")
            continue

        global_ids: Dict[str, str] = {}
        test_count = 0

        for path in paths:
            where = f"{test}/{path.name}"
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                report.error(where, f"invalid JSON - {exc}")
                continue

            items = check_envelope(report, where, doc, test)
            test_count += len(items)

            if test == "logic":
                check_logic(report, where, items, known_tags)
            else:
                CHECKERS[test](report, where, items)

            # Identifiers must always be unique within a grade file, and for
            # most tests across the whole test as well.
            id_field = spec["id_field"]
            local_ids: set[str] = set()
            for item in items:
                item_id = item.get(id_field)
                if not item_id:
                    continue
                if item_id in local_ids:
                    report.error(where, f"duplicate {id_field} '{item_id}' within file")
                local_ids.add(item_id)

                if spec["global_id"]:
                    if item_id in global_ids and global_ids[item_id] != path.name:
                        report.error(
                            where,
                            f"{id_field} '{item_id}' also appears in {global_ids[item_id]}",
                        )
                    global_ids[item_id] = path.name

            print(f"  {where:<40} {len(items):>3} items")

        total_items += test_count
        print(f"  {'-' * 40} {test_count:>3} total ({test})\n")

    for warning in report.warnings:
        print(f"WARN  {warning}")
    if report.warnings:
        print()

    for error in report.errors:
        print(f"FAIL  {error}")

    if report.ok:
        print(f"OK - {total_items} items validated, {len(report.warnings)} warning(s)")
        return 0

    print(f"\n{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
