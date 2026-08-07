"""Question-bank loader for the Logic Quest assessment."""

from __future__ import annotations

from typing import Any, Mapping

from app.core.exceptions import DataFileError
from app.domain.enums import CognitiveTag, Difficulty, Grade, TestType
from app.domain.models import LogicItem, Option
from app.engines.base import QuestionLoader


class LogicQuestionLoader(QuestionLoader[LogicItem]):
    """Reads ``data/questions/logic/<grade>.json`` into :class:`LogicItem`."""

    items_key = "items"

    def __init__(self) -> None:
        super().__init__(TestType.LOGIC)

    def parse_item(self, raw: Mapping[str, Any], grade: Grade) -> LogicItem:
        item_id = raw.get("item_id")
        if not item_id:
            raise DataFileError(f"logic/{grade.file_stem}.json: item missing 'item_id'")

        try:
            primary_tag = CognitiveTag(raw["primary_tag"])
        except KeyError as exc:
            raise DataFileError(f"{item_id}: missing 'primary_tag'") from exc
        except ValueError as exc:
            raise DataFileError(
                f"{item_id}: unknown primary_tag {raw.get('primary_tag')!r}"
            ) from exc

        try:
            difficulty = Difficulty(raw.get("difficulty", "medium"))
        except ValueError as exc:
            raise DataFileError(
                f"{item_id}: unknown difficulty {raw.get('difficulty')!r}"
            ) from exc

        options = [
            Option(
                index=option.get("index", position),
                text=option.get("text", ""),
                image_url=option.get("image_url"),
            )
            for position, option in enumerate(raw.get("options", []))
        ]
        if not options:
            raise DataFileError(f"{item_id}: has no options")

        correct_index = raw.get("correct_answer_index")
        if not isinstance(correct_index, int) or not 0 <= correct_index < len(options):
            raise DataFileError(
                f"{item_id}: correct_answer_index {correct_index!r} is out of range"
            )

        conditional_tags = {
            condition: CognitiveTag(tag)
            for condition, tag in (raw.get("conditional_tags") or {}).items()
        }

        return LogicItem(
            item_id=item_id,
            grade=grade,
            item_number=raw.get("item_number", item_id),
            item_type=raw.get("item_type", "unknown"),
            question_text=raw.get("question_text", ""),
            options=options,
            correct_answer_index=correct_index,
            primary_tag=primary_tag,
            conditional_tags=conditional_tags,
            difficulty=difficulty,
            expected_latency_seconds=raw.get("expected_latency_seconds", 30),
        )
