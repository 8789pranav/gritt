"""Stage A of the Learning Snapshot: the deterministic evidence pipeline.

Fetches the latest result for each assessment, extracts the tags, maps them
to the five learning areas, and computes an evidence package that the LLM
writer (Stage B) turns into a parent letter.

This stage never calls an LLM. It produces facts; the writer produces words.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.domain.enums import TestType
from app.core.security import verify_paid_child
from app.infrastructure.repositories import ScoreRepository

logger = logging.getLogger(__name__)

_AREA_CONFIG_PATH = os.path.join("data", "tags", "learning_areas.json")

_AREA_CACHE: Optional[Dict[str, Any]] = None


def _load_area_config() -> Dict[str, Any]:
    """Load and cache the learning-areas mapping."""
    global _AREA_CACHE
    if _AREA_CACHE is None:
        with open(_AREA_CONFIG_PATH, encoding="utf-8") as f:
            _AREA_CACHE = json.load(f)
    return _AREA_CACHE


class SnapshotService:
    """Builds the structured evidence behind the Learning Snapshot."""

    def __init__(self) -> None:
        self._config = _load_area_config()
        self._scores = ScoreRepository()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def build_evidence(
        self,
        id_token: str,
        child_id: str,
        grade: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch all four results and synthesise the evidence package."""
        uid, child_data = verify_paid_child(id_token, child_id)
        child_name = child_data.get("name", "")

        # A1. Fetch the latest result for every assessment.
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for key, storage_key in (
            ("logic", TestType.LOGIC.storage_key),
            ("spelling", TestType.SPELLING.storage_key),
            ("speaking", TestType.SPEAKING.storage_key),
            ("comprehension", TestType.COMPREHENSION.storage_key),
        ):
            try:
                results[key] = self._scores.get_latest(
                    uid, child_id, storage_key, grade
                )
            except Exception as exc:  # a failed fetch must not sink the letter
                logger.warning("snapshot: could not fetch %s: %s", key, exc)
                results[key] = None

        completed = [k for k, v in results.items() if v]

        # A2-A5. Extract, map, rank.
        observations = self._collect_observations(results)
        strengths = [o for o in observations if o["polarity"] == "strength"]
        growth_edges = [o for o in observations if o["polarity"] == "growth_edge"]

        strengths.sort(key=self._observation_rank, reverse=True)
        growth_edges.sort(key=self._observation_rank, reverse=True)

        return {
            "child_name": child_name,
            "grade": grade,
            "tests_completed": completed,
            "observations": strengths[:3],
            "growth_edges": growth_edges[:3],
            "full_picture_areas": [
                {
                    "area": o["area"],
                    "area_display_name": o["area_display_name"],
                    "badge": "seen_repeatedly" if o["evidence_strength"] == "seen_more_than_once" else "seen_once",
                    "polarity": o["polarity"],
                    "seen_in": o["seen_in"],
                    "tags": o["tags"],
                }
                for o in observations
            ],
        }

    # ------------------------------------------------------------------
    # Stage A2/A3: extract tags per test and group them into areas
    # ------------------------------------------------------------------
    def _collect_observations(
        self, results: Dict[str, Optional[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Group the fired tags into learning areas with evidence counts."""
        areas = self._config["areas"]
        display = self._config["test_display_names"]

        # tag_id -> (test_key, polarity, description) for every fired tag
        fired: Dict[str, List[Dict[str, Any]]] = {}

        for test_key, result in results.items():
            if not result:
                continue
            for tag in result.get("dear_parent_tags", []):
                tag_id = tag.get("id") or tag.get("tag", "")
                if not tag_id:
                    continue
                fired.setdefault(tag_id, []).append(
                    {
                        "test": test_key,
                        "polarity": tag.get("polarity", "neutral"),
                        "description": tag.get("description", ""),
                    }
                )

        observations: List[Dict[str, Any]] = []
        for area_key, area_cfg in areas.items():
            per_test_tags: Dict[str, List[str]] = {}
            polarities: List[str] = []
            evidence_detail: Dict[str, Any] = {}

            for test_key, tag_ids in area_cfg["sources"].items():
                matched: List[str] = []
                for tag_id in tag_ids:
                    if tag_id in fired:
                        hits = fired[tag_id]
                        matched.append(tag_id)
                        for hit in hits:
                            polarities.append(hit["polarity"])
                if matched:
                    per_test_tags[test_key] = matched
                    result = results.get(test_key)
                    if result:
                        detail: Dict[str, Any] = {
                            "tags": [
                                {
                                    "id": t,
                                    "polarity": next(
                                        (h["polarity"] for h in fired.get(t, [])), "neutral"
                                    ),
                                    "description": next(
                                        (h["description"] for h in fired.get(t, [])), ""
                                    ),
                                }
                                for t in matched
                            ]
                        }
                        signals = result.get("signals", {})
                        if signals:
                            detail["signals"] = signals
                        per_items = result.get("per_item_tags") or result.get(
                            "per_word_tags"
                        ) or result.get("per_question_tags"
                        ) or []
                        if per_items:
                            detail["per_item_tags"] = per_items
                        scored = result.get("scored_items") or []
                        if scored:
                            detail["scored_items"] = scored
                        evidence_detail[test_key] = detail

            if not per_test_tags:
                continue  # no evidence for this area

            seen_in = [display[k] for k in per_test_tags if k in display]
            evidence_strength = (
                "seen_more_than_once" if len(per_test_tags) >= 2 else "seen_once"
            )
            # The area's polarity is whatever its tags lean towards.
            polarity = (
                "strength"
                if polarities.count("strength") >= polarities.count("growth_edge")
                else "growth_edge"
            )

            observations.append(
                {
                    "area": area_key,
                    "area_display_name": area_cfg["display_name"],
                    "polarity": polarity,
                    "evidence_strength": evidence_strength,
                    "seen_in": seen_in,
                    "tags": per_test_tags,
                    "evidence_detail": evidence_detail,
                }
            )

        return observations

    @staticmethod
    def _observation_rank(observation: Dict[str, Any]) -> float:
        """More tests, then more tags, rank higher."""
        tag_count = sum(len(v) for v in observation["tags"].values())
        strength_bonus = 1.0 if observation["evidence_strength"] == "seen_more_than_once" else 0.0
        return len(observation["tags"]) * 2 + tag_count + strength_bonus


def get_snapshot_service() -> SnapshotService:
    return SnapshotService()
