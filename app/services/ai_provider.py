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

10. **Interpret spelling per-word tags correctly.** Spelling per-word tags
    distinguish between genuine misspellings and unrelated attempts:
    - `{feature}_correct` / `{feature}_error`: The child attempted the word
      and specific phonics features were evaluated (e.g., "beginning_consonant_error"
      means they got the starting sound wrong but tried to spell the same word).
    - `sight_word_correct` / `sight_word_error`: The child attempted a sight
      word and spelled it correctly or incorrectly.
    - `unrelated_attempt`: The child entered a completely different word that
      is not a misspelling of the target (e.g., "which" → "book"). This may
      indicate inattention, guessing, or not hearing the word properly. Do NOT
      interpret this as a phonics difficulty — the child did not attempt the
      target word at all.
    - `unrelated_attempt_sightword`: Same as above but for sight words.
    - `rushed_attempt`: The child answered too quickly (under 3 seconds) and
      got it wrong. May indicate impulsivity or lack of effort.
    When summarising spelling performance, distinguish between phonics
    difficulties (feature errors) and attention/guessing issues (unrelated
    attempts).

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


# ---------------------------------------------------------------------------
# Spelling convention classifier — uses GPT-4o-mini to detect phonetically
# correct but conventionally wrong spellings that rule-based phonetic keys
# miss (k/c, ow/ou, ur/er swaps). Batch call: one API call per submission.
# ---------------------------------------------------------------------------

_CONVENTION_SYSTEM_PROMPT = """\
You are a phonics and spelling convention expert for early-grade spelling assessment.

You will receive a JSON list of word pairs. Each pair has a "target" (the correct \
spelling) and an "attempt" (what the child wrote).

For each pair, classify the attempt into exactly one category:

- "spelling_convention": The attempt SOUNDS IDENTICAL or nearly identical to the \
target when spoken aloud, but is spelled differently. The child knows the sounds; \
they just used the wrong spelling convention. Examples: candle→kandle (k for c), \
outline→owtline (ow for ou), perplex→purplex (ur for er), turnstile→ternstile \
(er for ur), phone→fone (f for ph), graph→graff (f for gh), clunk→clunck (ck for k), \
candle→candel (el for le), standstill→standstil (dropped silent e on UNSTRESSED syllable).

- "phonics_error": The attempt sounds DIFFERENT from the target — wrong vowel sound, \
wrong consonant, missing sound, or extra sound. Examples: cat→cot (wrong vowel), \
bug→bag (wrong vowel), home→hom (dropped silent e SHORTENS the vowel — phonics error), \
turnstile→turnstil (dropped silent e SHORTENS the vowel — phonics error, NOT convention), \
entertain→entertan (dropped silent e shortens the vowel — phonics error).

- "exact_match": The attempt is spelled exactly the same as the target.

- "unrelated": The attempt is a completely different word, not a misspelling.

CRITICAL RULES — the silent 'e' distinction is the most important:

1. A dropped silent 'e' that SHORTENS or CHANGES the vowel sound is ALWAYS a \
PHONICS ERROR, never a convention error. The sound changed. Examples: \
home→hom (long o becomes short o), turnstile→turnstil (long i becomes short i), \
entertain→entertan (long a becomes short a), smile→smil (long i becomes short i).

2. A dropped silent 'e' on an UNSTRESSED syllable where the sound does NOT change \
IS a convention error. Example: standstill→standstil (the final syllable is \
unstressed, so dropping the 'e' doesn't change the sound).

3. To decide: pronounce both words aloud in your head. If they sound IDENTICAL, \
it's a convention error. If the vowel sound changes (especially long→short), \
it's a phonics error.

4. Letter swaps that produce the SAME sound (k/c before a/o/u, ow/ou, ur/er, \
ir/er, f/ph, f/gh, ck/k, c/k) are convention errors.

5. When in doubt, ask: "Would these two sound identical if read aloud by a \
teacher?" If yes, convention error. If the sound changes, phonics error.

Return a JSON object: {"results": [{"index": 0, "category": "spelling_convention"}, ...]}
The index is the 0-based position in the input list. Only include items where \
category is "spelling_convention" — omit all other categories.
"""

_CONVENTION_USER_TEMPLATE = """\
Classify each word pair below. Return JSON with "results" array.

Word pairs:
{pairs_json}
"""


class SpellingConventionClassifier:
    """Batch-classify spelling attempts as convention errors or phonics errors.

    Uses GPT-4o-mini for speed and cost. Falls back to rule-based
    ``sounds_like()`` when OpenAI is not configured or the call fails.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._openai: Optional[openai.OpenAI] = None
        if self._settings.openai.is_configured:
            self._openai = openai.OpenAI(api_key=self._settings.openai.api_key)

    @property
    def is_configured(self) -> bool:
        return self._openai is not None

    def classify_batch(
        self,
        pairs: List[Dict[str, str]],
    ) -> Dict[int, str]:
        """Classify a batch of (target, attempt) pairs.

        Parameters
        ----------
        pairs
            List of ``{"target": "candle", "attempt": "kandle"}`` dicts.

        Returns
        -------
        dict
            Mapping of index → category string. Only includes indices that
            are convention errors (category == "spelling_convention").
            Other categories are omitted so the caller falls back to
            rule-based logic for them.
        """
        if not self._openai or not pairs:
            return {}

        # Truncate to avoid token limits (typical submission has 10-20 words).
        pairs_to_send = pairs[:50]

        import json as _json
        user_prompt = _CONVENTION_USER_TEMPLATE.format(
            pairs_json=_json.dumps(pairs_to_send, indent=2)
        )

        try:
            response = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _CONVENTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=1000,
            )
        except Exception as exc:
            logger.warning("Spelling convention AI call failed: %s", exc)
            return {}

        raw = response.choices[0].message.content
        try:
            result = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            logger.warning("Spelling convention AI returned invalid JSON: %s", raw[:200])
            return {}

        convention_indices: Dict[int, str] = {}
        for item in result.get("results", []):
            idx = item.get("index")
            category = item.get("category", "")
            if idx is not None and category == "spelling_convention":
                convention_indices[int(idx)] = "spelling_convention"

        return convention_indices


def get_spelling_convention_classifier() -> SpellingConventionClassifier:
    """Factory for the spelling convention AI classifier."""
    return SpellingConventionClassifier()
