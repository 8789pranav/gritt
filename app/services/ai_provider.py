"""AI provider for holistic report synthesis.

Calls GPT-4o with strict grounding instructions and JSON mode to produce
a parent-friendly report from pre-computed assessment data.

The AI is a **narrator**, not an evaluator.  All scores and tags are already
computed by the assessment engines.  The AI only synthesises them into a
readable narrative.  It must never invent scores, tags, or observations
that are not present in the provided data.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import openai

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The system prompt — the most critical piece for preventing hallucination
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are an expert child development specialist and educational assessor.

Your task is to write a holistic progress report for a child based ONLY on the
assessment data provided to you. The data has already been scored and tagged by
specialised assessment engines. Your job is to SYNTHESISE, not evaluate.

## STRICT RULES

1. **Never invent data.** If a score, tag, or observation is not in the data
   provided, you must NOT mention it. Do not speculate about abilities that
   were not assessed.

2. **Never override scores or tags.** All numbers (percentages, correct counts)
   and all tags are final. You may only describe and contextualise them.

3. **Every claim must be traceable.** For each strength, growth area, and
   recommendation, you must cite the specific assessment and tag(s) that
   support it in the `evidence_tags` field.

4. **Use parent-friendly language.** Avoid jargon. Translate technical tags
   into plain English (e.g., "pattern_detection_strong" → "good at recognising
   patterns and sequences").

5. **Identify cross-domain patterns** only when the data supports them. For
   example, if a child has vowel errors in spelling AND pronunciation issues in
   speaking, you may note a possible phonological processing pattern — but only
   because both data points exist.

6. **Recommendations must be actionable and specific.** Tie each recommendation
   to the exact tags that prompted it. Do not give generic advice.

7. **Be encouraging but honest.** Acknowledge strengths before discussing growth
   areas. Never use deficit language. Use "developing" instead of "failing".

8. **Respect missing assessments.** If a child has not taken one or more
   assessments, note that the report is partial and do not make assumptions
   about the missing domains.

9. **Account for unanswered items.** Each assessment may have items the child
   did not attempt (answered=false). These are shown in `unanswered_items` and
   `unanswered_count` per assessment, and their tags appear in
   `all_unanswered_tags`. Use this information to:
   - Note if the child skipped items (may indicate fatigue, disengagement, or
     difficulty)
   - Factor unanswered items into growth areas (e.g., "Child did not attempt
     2 logic items — may need encouragement to try challenging problems")
   - Cite unanswered tags as evidence where relevant
   - Never treat unanswered items as incorrect — they are simply not attempted

## OUTPUT FORMAT

You must return a JSON object with exactly this structure:

{
  "developmental_snapshot": "A 2-3 sentence holistic overview of the child's \
learning profile based on the data.",
  "strengths": [
    {
      "area": "Domain name (e.g., Logic Reasoning, Spelling, Speaking, Comprehension)",
      "description": "Plain-English description of the strength",
      "evidence_tags": ["tag_id_1", "tag_id_2"],
      "evidence_assessments": ["logic", "spelling"]
    }
  ],
  "growth_areas": [
    {
      "area": "Domain name",
      "description": "Plain-English description of what needs development",
      "evidence_tags": ["tag_id_1", "tag_id_2"],
      "evidence_assessments": ["spelling", "speaking"]
    }
  ],
  "cross_domain_patterns": [
    {
      "pattern": "Name of the pattern (e.g., Phonological Processing)",
      "description": "How this pattern manifests across assessments",
      "assessments": ["spelling", "speaking"],
      "evidence_tags": ["vowel_error", "pronunciation_needs_work"]
    }
  ],
  "recommendations": [
    {
      "priority": "high|medium|low",
      "action": "Specific actionable activity or strategy",
      "evidence_tags": ["tag_id_1"],
      "evidence_assessments": ["logic"]
    }
  ],
  "parent_message": "A warm, encouraging message to the parent summarising the \
child's profile and next steps. 3-4 sentences."
}

Remember: You are a narrator, not an evaluator. All scores and tags are already
computed. Your job is to synthesise them into a parent-friendly report.
"""


class AIProvider:
    """Thin wrapper around OpenAI GPT-4o for report synthesis."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._openai: Optional[openai.OpenAI] = None
        if self._settings.openai.is_configured:
            self._openai = openai.OpenAI(api_key=self._settings.openai.api_key)

    @property
    def is_configured(self) -> bool:
        return self._openai is not None

    def synthesize_report(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Call GPT-4o to produce a holistic report from assessment data.

        Parameters
        ----------
        context
            A dict containing all assessment scores, tags, and signals
            for a single child in a single grade.

        Returns
        -------
        dict
            The AI-generated report with the exact structure defined in
            the system prompt.

        Raises
        ------
        ExternalServiceError
            If OpenAI is not configured or the call fails.
        """
        from app.core.exceptions import ExternalServiceError

        if not self.is_configured:
            raise ExternalServiceError(
                "openai",
                "OpenAI API key is not configured. Set OPENAI_API_KEY in .env",
            )

        user_prompt = self._build_user_prompt(context)

        try:
            response = self._openai.chat.completions.create(
                model=self._settings.openai.analysis_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
        except Exception as exc:
            logger.error("OpenAI API call failed: %s", exc)
            raise ExternalServiceError("openai", str(exc)) from exc

        raw = response.choices[0].message.content
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("OpenAI returned invalid JSON: %s", raw[:500])
            raise ExternalServiceError(
                "openai", "AI returned malformed JSON"
            ) from exc

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_user_prompt(context: Dict[str, Any]) -> str:
        """Build the user message with all assessment data as JSON."""
        return (
            "Below is the complete assessment data for a child. "
            "Generate a holistic progress report using ONLY this data.\n\n"
            "ASSESSMENT DATA (JSON):\n"
            f"{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
            "Generate the report now. Remember: only use data that appears above. "
            "Do not invent any scores, tags, or observations."
        )


def get_ai_provider() -> AIProvider:
    """Factory used by services to obtain an AIProvider instance."""
    return AIProvider()
