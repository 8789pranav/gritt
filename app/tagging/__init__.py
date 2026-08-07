"""Declarative cognitive tagging: trigger evaluation and tag emission."""

from app.tagging.config_loader import (
    TagConfig,
    TagDefinition,
    load_shared_settings,
    load_tag_config,
)
from app.tagging.emitter import emit_tags, summarise, tag_ids, to_payload
from app.tagging.evaluator import evaluate, referenced_signals

__all__ = [
    "TagConfig",
    "TagDefinition",
    "load_tag_config",
    "load_shared_settings",
    "emit_tags",
    "to_payload",
    "tag_ids",
    "summarise",
    "evaluate",
    "referenced_signals",
]
