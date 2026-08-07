"""
Turns derived signals into emitted cognitive tags.

The emitter is deliberately generic: it knows nothing about any particular
assessment. Each engine derives its own signal dictionary, and this module
applies the declarative rules loaded from that test's tag config. Adding a new
assessment therefore requires no change here (open/closed principle).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from app.domain.enums import Polarity, TestType
from app.domain.models import PerItemTags, TagOutput
from app.tagging.config_loader import TagConfig, TagDefinition, load_tag_config
from app.tagging.evaluator import evaluate, referenced_signals

logger = logging.getLogger(__name__)


def _format_evidence(trigger: str, signals: Mapping[str, Any]) -> str:
    """Render the signal values that caused a trigger to fire."""
    parts = [
        f"{name}={signals[name]}"
        for name in referenced_signals(trigger)
        if name in signals
    ]
    return ", ".join(parts) if parts else trigger


def emit_tags(
    test: TestType,
    signals: Mapping[str, Any],
    *,
    config: Optional[TagConfig] = None,
) -> List[TagOutput]:
    """Evaluate every tag rule for ``test`` against ``signals``.

    Returns the tags whose triggers fired, ordered strengths first (most
    confident first), then neutral, then growth edges - which is the order the
    parent-facing summaries read best in.
    """
    config = config or load_tag_config(test)
    emitted: List[TagOutput] = []

    for definition in config.tags:
        if not evaluate(definition.trigger, signals):
            continue
        emitted.append(
            TagOutput(
                tag=definition.id,
                confidence=definition.confidence,
                polarity=definition.polarity,
                description=definition.description,
                evidence=_format_evidence(definition.trigger, signals),
            )
        )

    return sort_tags(emitted)


_POLARITY_ORDER = {
    Polarity.STRENGTH: 0,
    Polarity.NEUTRAL: 1,
    Polarity.GROWTH_EDGE: 2,
}


def sort_tags(tags: Sequence[TagOutput]) -> List[TagOutput]:
    """Order tags by polarity, then by descending confidence weight."""
    return sorted(
        tags,
        key=lambda tag: (_POLARITY_ORDER.get(tag.polarity, 99), -tag.weight, tag.tag),
    )


def suppress_redundant(
    tags: Sequence[TagOutput],
    *,
    supersedes: Mapping[str, str],
) -> List[TagOutput]:
    """Drop a weaker tag when its stronger counterpart also fired.

    ``supersedes`` maps a strong tag id to the weaker tag it replaces, e.g.
    ``{"pattern_detection_strong": "pattern_detection_emerging"}``.
    """
    present = {tag.tag for tag in tags}
    redundant = {
        weaker for stronger, weaker in supersedes.items() if stronger in present
    }
    return [tag for tag in tags if tag.tag not in redundant]


def apply_confidence_policy(
    tags: Sequence[TagOutput],
    *,
    never_standalone_if_low_confidence: bool = True,
    min_tags_for_headline: int = 2,
) -> List[TagOutput]:
    """Enforce the shared synthesis rules on a tag set.

    A single low-confidence tag on its own is misleading to a parent, so it is
    dropped unless corroborated by at least one other tag.
    """
    result = list(tags)

    if never_standalone_if_low_confidence and len(result) < min_tags_for_headline:
        result = [tag for tag in result if tag.weight > 0.3]

    return result


def to_payload(tags: Iterable[TagOutput]) -> List[Dict[str, Any]]:
    """Serialise tags into the API/Firebase representation."""
    return [
        {
            "id": tag.tag,
            "confidence": tag.confidence.value,
            "polarity": tag.polarity.value,
            "description": tag.description,
            "evidence": tag.evidence,
        }
        for tag in tags
    ]


def tag_ids(tags: Iterable[TagOutput]) -> List[str]:
    return [tag.tag for tag in tags]


def build_per_item_tags(
    entries: Iterable[Mapping[str, Any]],
) -> List[PerItemTags]:
    """Normalise per-item tag dictionaries into domain models."""
    return [
        PerItemTags(
            item_id=str(entry.get("item_id", "")),
            answered=bool(entry.get("answered", True)),
            is_correct=entry.get("is_correct"),
            tags=list(entry.get("tags", [])),
        )
        for entry in entries
    ]


def summarise(tags: Sequence[TagOutput]) -> Dict[str, Any]:
    """Produce a compact breakdown used by the parent summary sections."""
    strengths = [tag for tag in tags if tag.polarity is Polarity.STRENGTH]
    growth = [tag for tag in tags if tag.polarity is Polarity.GROWTH_EDGE]
    neutral = [tag for tag in tags if tag.polarity is Polarity.NEUTRAL]

    return {
        "total": len(tags),
        "strengths": [tag.description or tag.tag for tag in strengths],
        "growth_edges": [tag.description or tag.tag for tag in growth],
        "neutral": [tag.description or tag.tag for tag in neutral],
        "confidence_score": round(
            sum(tag.weight for tag in tags) / len(tags), 2
        ) if tags else 0.0,
    }
