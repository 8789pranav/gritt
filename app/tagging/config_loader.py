"""
Loads and validates the per-test tag configuration files.

Each assessment owns one file under ``data/tags/<test>_tags.json`` plus a
shared ``shared_settings.json``. Configs are read once and cached, so adding a
new assessment means dropping in a new JSON file - no code change here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from app.core.config import get_settings
from app.core.exceptions import DataFileError
from app.domain.enums import Confidence, Polarity, TestType
from app.tagging.evaluator import referenced_signals

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TagDefinition:
    """One declarative tag rule."""

    id: str
    trigger: str
    confidence: Confidence
    polarity: Polarity
    description: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], source: str) -> "TagDefinition":
        try:
            return cls(
                id=raw["id"],
                trigger=raw["trigger"],
                confidence=Confidence(raw["confidence"]),
                polarity=Polarity(raw["polarity"]),
                description=raw.get("description", ""),
            )
        except KeyError as exc:
            raise DataFileError(f"{source}: tag is missing field {exc}") from exc
        except ValueError as exc:
            raise DataFileError(f"{source}: {exc}") from exc


@dataclass(frozen=True)
class TagConfig:
    """Parsed contents of one ``<test>_tags.json`` file."""

    test: TestType
    test_key: str
    display_name: str
    tags: List[TagDefinition]
    derived_signals: List[str] = field(default_factory=list)
    item_type_groups: Dict[str, List[str]] = field(default_factory=dict)
    question_type_mapping: Dict[str, str] = field(default_factory=dict)

    def get(self, tag_id: str) -> Optional[TagDefinition]:
        for tag in self.tags:
            if tag.id == tag_id:
                return tag
        return None

    @property
    def tag_ids(self) -> List[str]:
        return [tag.id for tag in self.tags]

    def group_for_item_type(self, item_type: str) -> Optional[str]:
        """Return the first group containing ``item_type``, if any."""
        for group, members in self.item_type_groups.items():
            if item_type in members:
                return group
        return None

    def groups_for_item_type(self, item_type: str) -> List[str]:
        """Return every group containing ``item_type``.

        Item types may legitimately belong to more than one group - for
        example ``comparison`` counts as both *relational* and *load*.
        """
        return [
            group
            for group, members in self.item_type_groups.items()
            if item_type in members
        ]


@dataclass(frozen=True)
class SharedSettings:
    """Cross-test thresholds and synthesis rules."""

    thresholds: Dict[str, Any] = field(default_factory=dict)
    synthesis_rules: Dict[str, Any] = field(default_factory=dict)
    confidence_weights: Dict[str, float] = field(default_factory=dict)

    def threshold(self, name: str, default: Any = None) -> Any:
        return self.thresholds.get(name, default)

    def rule(self, name: str, default: Any = None) -> Any:
        return self.synthesis_rules.get(name, default)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise DataFileError(f"Tag config not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataFileError(f"{path.name} contains invalid JSON: {exc}") from exc


def _validate(config: TagConfig) -> None:
    """Warn about triggers referencing signals the test never declares."""
    if not config.derived_signals:
        return

    declared = set(config.derived_signals)
    for tag in config.tags:
        unknown = [s for s in referenced_signals(tag.trigger) if s not in declared]
        if unknown:
            logger.warning(
                "%s: tag %r references undeclared signal(s): %s",
                config.test.value,
                tag.id,
                ", ".join(unknown),
            )


@lru_cache(maxsize=None)
def load_tag_config(test: TestType) -> TagConfig:
    """Load and cache the tag configuration for one assessment."""
    path = get_settings().paths.tags_dir / f"{test.value}_tags.json"
    raw = _read_json(path)

    config = TagConfig(
        test=test,
        test_key=raw.get("test_key", test.value),
        display_name=raw.get("display_name", test.display_name),
        tags=[TagDefinition.from_dict(tag, path.name) for tag in raw.get("tags", [])],
        derived_signals=list(raw.get("derived_signals", [])),
        item_type_groups={
            group: list(members)
            for group, members in (raw.get("item_type_groups") or {}).items()
        },
        question_type_mapping=dict(raw.get("question_type_mapping") or {}),
    )

    _validate(config)
    logger.debug("Loaded %d tags for %s", len(config.tags), test.value)
    return config


@lru_cache(maxsize=1)
def load_shared_settings() -> SharedSettings:
    """Load and cache ``shared_settings.json``."""
    path = get_settings().paths.tags_dir / "shared_settings.json"
    raw = _read_json(path)
    return SharedSettings(
        thresholds=dict(raw.get("thresholds") or {}),
        synthesis_rules=dict(raw.get("synthesis_rules") or {}),
        confidence_weights=dict(raw.get("confidence_weights") or {}),
    )


def all_tag_definitions() -> Dict[str, TagDefinition]:
    """Return every tag across every test, keyed by tag id."""
    definitions: Dict[str, TagDefinition] = {}
    for test in TestType:
        try:
            for tag in load_tag_config(test).tags:
                definitions[tag.id] = tag
        except DataFileError:
            logger.warning("No tag config for %s, skipping", test.value)
    return definitions


def clear_cache() -> None:
    """Drop cached configs so the next read picks up edited files."""
    load_tag_config.cache_clear()
    load_shared_settings.cache_clear()
