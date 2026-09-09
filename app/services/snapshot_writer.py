"""Stage B of the Learning Snapshot: the LLM narrative writer.

Takes the structured evidence from Stage A and asks GPT-4o to write the
parent letter. The output is validated against hard guardrails before it
is returned; anything that fails falls back to a warm generic letter.

The LLM writes words. It never decides which tags fired, which areas they
belong to, or what the evidence was — that is Stage A's job.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a teacher writing a letter to a parent about their child.

You will receive structured evidence from educational assessments the child
completed this week. Your job is to write a warm, specific, honest letter
about what the child did.

VOICE AND TONE
- Write in first person, as if you sat with the child through the activities.
- Be warm but never saccharine.
- Be specific: reference actual behaviors, actual items, actual outcomes from the evidence.
- Be honest: if something is still developing, say so plainly and kindly.
- Never use the words: "score", "percent", "grade level", "above", "below",
  "average", "normal", "advanced", "behind", "diagnosis", "assessment score".
- Never compare the child to other children or to a standard.
- Describe what the child DID, not what the child IS.

STRUCTURE
Return JSON with these exact keys:

{
  "opening": {
    "headline": "One sentence, the most striking thing about this child.",
    "paragraph": "2-3 sentences. Personal, narrative. Reference specific behaviors from the evidence."
  },
  "what_i_noticed": [
    {
      "headline": "One-line observation. Short.",
      "area_display_name": "Copy from the evidence.",
      "paragraph": "2-3 sentences. Reference specific items, counts, or timing from the evidence_detail.",
      "seen_in": ["Copy from the evidence."],
      "learning_signals": ["2-4 short phrases, e.g. 'Takes thinking time'"]
    }
  ],
  "what_helped": {
    "headline": "One sentence about what conditions helped.",
    "signals": ["2-3 short phrases"]
  },
  "still_growing": [
    {
      "headline": "One-line growth area. Kind, not clinical.",
      "paragraph": "2-3 sentences. What is still developing and why that's okay.",
      "suggestion": {
        "title": "One specific thing to try at home.",
        "body": "2-3 sentences. Concrete and actionable.",
        "because": "One sentence starting with 'Because' explaining why this follows from the evidence."
      }
    }
  ],
  "full_picture": [
    {
      "area_display_name": "Copy from the evidence.",
      "badge": "seen_repeatedly or seen_once",
      "paragraph": "2-3 sentences summarizing this area across all tests that contributed.",
      "seen_in": ["Copy from the evidence."]
    }
  ],
  "closing": "1-2 sentences. Warm. Reference that this is a starting point for a conversation."
}

RULES
- Maximum 3 items in "what_i_noticed".
- Maximum 3 items in "still_growing".
- Every "seen_in" must match the evidence exactly.
- Every suggestion must follow from a specific observation in the evidence.
- If evidence_strength is "seen_once", mention gently that this was observed in one context only.
- Use the child's name naturally, not in every sentence.
- Only use facts that appear in the evidence. Do not invent numbers, items, or behaviors.
"""

_FORBIDDEN_PATTERNS = [
    (re.compile(r"\d+\s*%", re.I), "percentage"),
    (re.compile(r"\d+\s*out of\s*\d+", re.I), "score ratio"),
    (re.compile(r"\babove grade\b", re.I), "grade label"),
    (re.compile(r"\bbelow grade\b", re.I), "grade label"),
    (re.compile(r"\bat grade\b", re.I), "grade label"),
    (re.compile(r"\bgrade level\b", re.I), "grade label"),
    (re.compile(r"\bdiagnos", re.I), "clinical language"),
    (re.compile(r"\bdisorder\b", re.I), "clinical language"),
    (re.compile(r"\bdeficit\b", re.I), "clinical language"),
    (re.compile(r"\bdelay(ed)?\b", re.I), "clinical language"),
    (re.compile(r"\btherapy\b", re.I), "clinical language"),
    # Only block comparisons to other children/peers/standards, not the
    # word "compared" in general (e.g. "compared to last week" is fine).
    (re.compile(r"\bcompared to (other|most|the average|peers|classmates|similar)", re.I), "comparison"),
    (re.compile(r"\bother children\b", re.I), "comparison"),
    (re.compile(r"\bmost children\b", re.I), "comparison"),
    (re.compile(r"\bpeers\b", re.I), "comparison"),
    (re.compile(r"\bclassmates\b", re.I), "comparison"),
]

_GENERIC_LETTER = {
    "opening": {
        "headline": "We had a good time working together.",
        "paragraph": (
            "Thank you for letting me spend this time with your child. "
            "There is plenty here worth talking about, and the notes below "
            "are a starting point for that conversation."
        ),
    },
    "what_i_noticed": [],
    "what_helped": {"headline": "Time and encouragement.", "signals": []},
    "still_growing": [],
    "full_picture": [],
    "closing": (
        "This is a starting point for a conversation about how your child "
        "learns. It is not a diagnosis or a formal assessment, and it "
        "compares your child to no one."
    ),
}


class SnapshotWriter:
    """Calls GPT-4o to write the snapshot letter, then validates it."""

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.openai.is_configured)

    # ------------------------------------------------------------------
    def write(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Write the letter. Falls back to a generic letter on any failure."""
        if not self.is_configured:
            logger.warning("snapshot writer: OpenAI not configured, using generic letter")
            return self._fallback(evidence)

        try:
            letter = self._generate(evidence)
            violations = self._validate(letter, evidence)
            if violations:
                logger.warning(
                    "snapshot writer: guardrail violations %s, retrying", violations
                )
                letter = self._generate(evidence, violations=violations)
                violations = self._validate(letter, evidence)
                if violations:
                    logger.warning(
                        "snapshot writer: still violating %s, using generic letter",
                        violations,
                    )
                    return self._fallback(evidence)
            return self._finalise(letter, evidence)
        except Exception as exc:
            logger.error("snapshot writer failed: %s", exc)
            return self._fallback(evidence)

    # ------------------------------------------------------------------
    def _generate(
        self,
        evidence: Dict[str, Any],
        violations: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        import openai

        client = openai.OpenAI(api_key=self._settings.openai.api_key)
        system = _SYSTEM_PROMPT
        if violations:
            system += (
                "\n\nPREVIOUS ATTEMPT FAILED THESE RULES — do not repeat them:\n"
                + "\n".join(f"- {v}" for v in violations)
            )

        user_prompt = (
            "Below is the structured evidence for one child. "
            "Write the letter now using ONLY this data.\n\n"
            "EVIDENCE (JSON):\n"
            f"{json.dumps(evidence, indent=2, ensure_ascii=False, default=str)}"
        )

        response = client.chat.completions.create(
            model=self._settings.openai.analysis_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=3000,
        )
        return json.loads(response.choices[0].message.content)

    # ------------------------------------------------------------------
    def _validate(
        self, letter: Dict[str, Any], evidence: Dict[str, Any]
    ) -> List[str]:
        """Return a list of guardrail violations (empty means it passed)."""
        violations: List[str] = []

        if not isinstance(letter, dict):
            return ["letter is not a JSON object"]

        # Structural checks.
        for key in ("opening", "what_i_noticed", "what_helped", "still_growing"):
            if key not in letter:
                violations.append(f"missing key: {key}")
        if violations:
            return violations

        noticed = letter.get("what_i_noticed") or []
        growing = letter.get("still_growing") or []
        if len(noticed) > 3:
            violations.append("more than 3 items in what_i_noticed")
        if len(growing) > 3:
            violations.append("more than 3 items in still_growing")
        for item in growing:
            suggestion = item.get("suggestion") or {}
            if not suggestion.get("because"):
                violations.append("a still_growing item has no 'because'")

        # seen_in must be a subset of the evidence's test display names.
        allowed = set()
        for obs in evidence.get("observations", []) + evidence.get("growth_edges", []):
            allowed.update(obs.get("seen_in", []))
        for item in noticed + growing:
            for seen in item.get("seen_in", []):
                if allowed and seen not in allowed:
                    violations.append(f"seen_in references unknown test: {seen}")

        # Forbidden language anywhere in the serialised letter.
        text = json.dumps(letter, ensure_ascii=False)
        for pattern, label in _FORBIDDEN_PATTERNS:
            match = pattern.search(text)
            if match:
                violations.append(f"forbidden {label}: {match.group(0)!r}")

        return violations

    # ------------------------------------------------------------------
    def _fallback(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        letter = json.loads(json.dumps(_GENERIC_LETTER))
        return self._finalise(letter, evidence, llm_generated=False)

    @staticmethod
    def _finalise(
        letter: Dict[str, Any], evidence: Dict[str, Any], llm_generated: bool = True
    ) -> Dict[str, Any]:
        name = evidence.get("child_name", "your child")
        closing = letter.get("closing") or _GENERIC_LETTER["closing"]
        if "{name}" in closing:
            closing = closing.replace("{name}", name)
        letter["closing"] = closing
        letter["branding"] = "The Dear Parent Project"
        letter["disclaimer"] = (
            f"This is a starting point for a conversation about how {name} "
            "learns. It is not a diagnosis or a formal assessment, and it "
            "compares them to no one."
        )
        letter["meta"] = {
            "llm_generated": llm_generated,
            "tests_completed": evidence.get("tests_completed", []),
            "guardrails_passed": llm_generated,
        }
        return letter


def get_snapshot_writer() -> SnapshotWriter:
    return SnapshotWriter()
