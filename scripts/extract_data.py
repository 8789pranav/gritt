"""
One-shot migration script.

Extracts hard-coded question banks out of the legacy ``main.py`` /
``logic_assessment.py`` modules and writes them as versioned JSON data files
under ``data/questions/<test>/<grade>.json``.

The legacy modules cannot simply be imported because ``main.py`` initialises
Firebase and AWS clients at module scope. Instead the module is parsed with
``ast`` and the relevant *literal* assignments are evaluated in isolation via
``ast.literal_eval``. This is both safe (no code executes) and lossless.

Run once from the repository root::

    python scripts/extract_data.py
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_DIR = REPO_ROOT / "data" / "questions"

# Legacy grade key -> canonical file stem used under data/questions/<test>/.
GRADE_FILE_STEMS: Dict[str, str] = {
    "Kindergarten": "kindergarten",
    "First": "grade_1",
    "Second": "grade_2",
    "Third": "grade_3",
}

# Logic items are keyed by GradeLevel enum values rather than display names.
LOGIC_GRADE_FILE_STEMS: Dict[str, str] = {
    "K-1": "kindergarten",
    "1-2": "grade_1",
    "2-3": "grade_2",
    "3-4": "grade_3",
}

SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------
def load_module_ast(path: Path) -> ast.Module:
    """Parse a Python source file into an AST without executing it."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def extract_literal_assignment(tree: ast.Module, name: str) -> Any:
    """Return the literal value assigned to a module-level ``name``.

    Raises ``KeyError`` if the name is not found and ``ValueError`` if the
    assigned expression is not a pure literal.
    """
    for node in tree.body:
        targets: List[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue

        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                value_node = node.value if isinstance(node, ast.Assign) else node.value
                try:
                    return ast.literal_eval(value_node)
                except ValueError as exc:  # pragma: no cover - defensive
                    raise ValueError(
                        f"{name} in {ast.dump(value_node)[:80]} is not a pure literal"
                    ) from exc

    raise KeyError(f"module-level assignment '{name}' not found")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    rel = path.relative_to(REPO_ROOT)
    print(f"  wrote {rel}")


def envelope(test: str, grade_key: str, items_key: str, items: Any) -> Dict[str, Any]:
    """Wrap a raw item collection in the standard data-file envelope."""
    count = len(items) if isinstance(items, (list, dict)) else 0
    return {
        "schema_version": SCHEMA_VERSION,
        "test": test,
        "grade": grade_key,
        "count": count,
        items_key: items,
    }


# ---------------------------------------------------------------------------
# Spelling
# ---------------------------------------------------------------------------
def extract_spelling(tree: ast.Module) -> None:
    print("spelling:")
    word_lists = extract_literal_assignment(tree, "word_lists")

    for grade_key, stem in GRADE_FILE_STEMS.items():
        grade_data = word_lists.get(grade_key)
        if grade_data is None:
            print(f"  !! missing spelling grade '{grade_key}', skipped")
            continue

        words: List[Dict[str, Any]] = []
        for word_type, bucket_key in (
            ("regular", "regular_words"),
            ("nonsense", "nonsense_words"),
            ("sight", "sight_words"),
        ):
            for word, attrs in (grade_data.get(bucket_key) or {}).items():
                attrs = dict(attrs)
                entry: Dict[str, Any] = {
                    "word": word,
                    "type": word_type,
                    "sentence": attrs.pop("sentence", ""),
                }
                # Remaining keys are phonics features scored per word.
                features = {
                    key: value
                    for key, value in attrs.items()
                    if str(value).strip() not in ("", "-")
                }
                if features:
                    entry["features"] = features
                words.append(entry)

        payload = envelope("spelling", grade_key, "words", words)
        payload["max_points"] = sum(
            len(w.get("features", {})) if w["type"] == "regular" else 1 for w in words
        )
        write_json(QUESTIONS_DIR / "spelling" / f"{stem}.json", payload)


# ---------------------------------------------------------------------------
# Speaking
# ---------------------------------------------------------------------------
def extract_speaking(tree: ast.Module) -> None:
    print("speaking:")
    speaking_sentences = extract_literal_assignment(tree, "speaking_sentences")

    for grade_key, stem in GRADE_FILE_STEMS.items():
        sentences = speaking_sentences.get(grade_key)
        if sentences is None:
            print(f"  !! missing speaking grade '{grade_key}', skipped")
            continue

        normalised = [
            {
                "sentence_id": s["id"],
                "sentence": s["sentence"],
                "word_count": s.get("word_count", len(s["sentence"].split())),
                "difficulty": s.get("difficulty", "medium"),
            }
            for s in sentences
        ]
        payload = envelope("speaking", grade_key, "sentences", normalised)
        payload["max_score_per_sentence"] = 100
        write_json(QUESTIONS_DIR / "speaking" / f"{stem}.json", payload)


# ---------------------------------------------------------------------------
# Comprehension
# ---------------------------------------------------------------------------
def extract_comprehension(tree: ast.Module) -> None:
    print("comprehension:")
    stories_by_grade = extract_literal_assignment(tree, "comprehension_stories")

    try:
        question_types = extract_literal_assignment(tree, "COMPREHENSION_QUESTION_TYPES")
    except KeyError:
        question_types = {}
        print("  .. COMPREHENSION_QUESTION_TYPES not found, continuing without it")

    for grade_key, stem in GRADE_FILE_STEMS.items():
        stories = stories_by_grade.get(grade_key)
        if stories is None:
            print(f"  !! missing comprehension grade '{grade_key}', skipped")
            continue

        normalised = []
        for story in stories:
            questions = []
            for q in story.get("questions", []):
                question = {
                    "question_id": q["id"],
                    "question": q["question"],
                    "options": q["options"],
                    "correct_index": q["correct_index"],
                }
                q_type = question_types.get(q["id"])
                if q_type:
                    question["question_type"] = q_type
                questions.append(question)

            normalised.append(
                {
                    "story_id": story["id"],
                    "title": story["title"],
                    "story_text": story["story"],
                    "duration_estimate": story.get("duration_estimate", "60 seconds"),
                    "questions": questions,
                }
            )

        payload = envelope("comprehension", grade_key, "stories", normalised)
        payload["total_questions"] = sum(len(s["questions"]) for s in normalised)
        write_json(QUESTIONS_DIR / "comprehension" / f"{stem}.json", payload)


# ---------------------------------------------------------------------------
# Logic Quest
# ---------------------------------------------------------------------------
_LOGIC_CALL_NAME = "_logic_quest_item"

# Positional signature of ``_logic_quest_item`` in logic_assessment.py.
_LOGIC_POSITIONAL_FIELDS = (
    "item_id",
    "grade_level",
    "item_number",
    "item_type",
    "question_text",
    "option_texts",
    "correct_answer_index",
    "primary_tag",
    "difficulty",
    "expected_latency_seconds",
)


def _literal(node: ast.expr) -> Any:
    """Evaluate a node, resolving ``Enum.MEMBER`` attributes to their name."""
    if isinstance(node, ast.Attribute):
        # GradeLevel.KINDERGARTEN_1 / CognitiveTag.PATTERN_DETECTION_STRONG
        return node.attr
    return ast.literal_eval(node)


def extract_logic(tree: ast.Module) -> None:
    print("logic:")

    # Map enum member names back to their string values so the JSON is
    # self-describing rather than referencing Python identifiers.
    enum_values: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in ("GradeLevel", "CognitiveTag"):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            enum_values[target.id] = stmt.value.value

    buckets: Dict[str, List[Dict[str, Any]]] = {
        stem: [] for stem in LOGIC_GRADE_FILE_STEMS.values()
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == _LOGIC_CALL_NAME):
            continue

        values: Dict[str, Any] = {}
        for field, arg in zip(_LOGIC_POSITIONAL_FIELDS, node.args):
            values[field] = _literal(arg)
        for kw in node.keywords:
            if kw.arg:
                values[kw.arg] = _literal(kw.value)

        grade_member = values.get("grade_level")
        grade_value = enum_values.get(grade_member, grade_member)
        stem = LOGIC_GRADE_FILE_STEMS.get(grade_value)
        if stem is None:
            print(f"  !! unknown grade '{grade_value}' for {values.get('item_id')}")
            continue

        tag_member = values.get("primary_tag")
        buckets[stem].append(
            {
                "item_id": values["item_id"],
                "item_number": values["item_number"],
                "item_type": values["item_type"],
                "question_text": values["question_text"],
                "options": [
                    {"index": i, "text": text, "image_url": None}
                    for i, text in enumerate(values["option_texts"])
                ],
                "correct_answer_index": values["correct_answer_index"],
                "primary_tag": enum_values.get(tag_member, tag_member),
                "difficulty": values.get("difficulty", "medium"),
                "expected_latency_seconds": values.get("expected_latency_seconds", 30),
            }
        )

    def sort_key(item: Dict[str, Any]) -> Any:
        match = re.search(r"(\d+)$", item["item_number"])
        return int(match.group(1)) if match else 0

    for grade_value, stem in LOGIC_GRADE_FILE_STEMS.items():
        items = sorted(buckets[stem], key=sort_key)
        if not items:
            print(f"  !! no logic items found for grade '{grade_value}'")
            continue

        payload = envelope("logic", grade_value, "items", items)
        payload["tag_coverage"] = _tag_coverage(items)
        write_json(QUESTIONS_DIR / "logic" / f"{stem}.json", payload)


def _tag_coverage(items: List[Dict[str, Any]]) -> Dict[str, int]:
    coverage: Dict[str, int] = {}
    for item in items:
        tag = item["primary_tag"]
        coverage[tag] = coverage.get(tag, 0) + 1
    return dict(sorted(coverage.items()))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main",
        type=Path,
        default=REPO_ROOT / "main.py",
        help="path to the legacy main.py",
    )
    parser.add_argument(
        "--logic",
        type=Path,
        default=REPO_ROOT / "logic_assessment.py",
        help="path to the legacy logic_assessment.py",
    )
    args = parser.parse_args()

    if not args.main.exists():
        print(f"error: {args.main} not found", file=sys.stderr)
        return 1
    if not args.logic.exists():
        print(f"error: {args.logic} not found", file=sys.stderr)
        return 1

    print(f"parsing {args.main.name} ...")
    main_tree = load_module_ast(args.main)
    print(f"parsing {args.logic.name} ...")
    logic_tree = load_module_ast(args.logic)

    extract_spelling(main_tree)
    extract_speaking(main_tree)
    extract_comprehension(main_tree)
    extract_logic(logic_tree)

    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
