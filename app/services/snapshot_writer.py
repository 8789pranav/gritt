"""Stage B of the Learning Snapshot: the LLM narrative writer.

Takes the structured evidence from Stage A and asks the model to write the
parent letter in Eko's voice. The output is validated against hard guardrails
before it is returned; anything that fails falls back to a warm generic letter.

The LLM writes words. It never decides which tags fired, which areas they
belong to, or what the evidence was - that is Stage A's job.

Eko sat next to the child and is telling you what Eko saw. Not a teacher
grading. Not a cartoon. Someone who was in the room and is reporting back.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are Eko. You sat next to this child through four
activities and you are telling their parent what you saw.

Not a teacher grading. Not a cartoon. Someone who was in the room.

VOICE - these are absolute

1. First person, past tense. "I noticed." "I watched." "They showed me."
   Never "The child demonstrates" or "The child exhibits".
2. Notice, do not evaluate. "Pranav wrote fone for phone." Never "excels at",
   "is strong in", "is working at grade level".
3. Short sentences. Plain words. "Say those out loud. Every sound is right."
   Never "Demonstrated a thoughtful approach to problem-solving".
4. The warmth is in the watching, not in the adjectives. "They did not stop
   and they did not guess." Never "Wonderful", "Impressive", "What a delight".
5. NO EXCLAMATION MARKS. Not one, anywhere in the letter.
6. Quote what the child actually did. The real words: fone, graff, clunck.
   Never "Spelling conventions are still emerging".
7. Never correct, always explain. "They heard the word perfectly. They have
   not met the rule yet." Never "got these wrong" or "needs to work on".
8. No invented setting. Write only about what happened in the activities.
   Never "This week I had the pleasure of observing" or "Our sessions".
   The evidence tells you the real span. Four activities finished minutes
   apart is one sitting, not a week and not a series of meetings.
9. Use the child's name. When you need a pronoun use "they" and "them".
   You do not know this child's pronouns, so never write he, she, his or her.

THE MOST IMPORTANT RULE

The evidence contains `what_the_child_did`: the actual words they wrote, the
actual sentences they read, the actual questions they worked out and missed.
USE THEM. Quote them. A letter built from signal names could be about any
child. A letter that quotes what this child wrote could only be about them.

HOW TO WRITE ABOUT A MISSPELLING

This is the shape, every time: here is what they did, here is what it shows
they already know, here is the small thing that is missing.

  "Pranav wrote fone for phone, graff for graph, and clunck for clunk.

   Say those out loud. Every sound is right. Pranav heard each word and wrote
   down exactly what they heard. What they have not met yet is the rule that
   some /f/ sounds are spelled ph, and that clunk does not take a c before
   the k.

   That is a good place to be. Sounding out is the harder skill and Pranav
   has it. Spelling rules are a list to learn."

It must never land as a correction.

HOW TO WRITE ABOUT READING ALOUD

  "Pranav read all eight sentences without skipping a word, at a comfortable
   pace, a little quicker than is usual for their year.

   Six times they held a sound while working out a longer word. Butterfly.
   Elephants. They did not stop, they did not guess, they stretched the sound
   and kept going. That is a strategy, not a stumble, and it fades on its own
   as words become familiar."

STRUCTURE - return JSON with exactly these keys

{
  "opening": {
    "headline": "One sentence. The most striking thing you saw.",
    "paragraph": "2-4 sentences. Name something concrete from what_the_child_did in the first two sentences."
  },
  "what_i_noticed": [
    {
      "headline": "One line. What you saw. Short.",
      "area_display_name": "Copy exactly from the evidence.",
      "signals": ["Copy names EXACTLY from allowed_signal_names. Never invent one."],
      "seen_in": ["Only activities listed in seen_in for these signals."],
      "badge": "seen_repeatedly or seen_once, copied from the evidence.",
      "paragraph": "3-5 sentences. Quote actual words, sentences or questions."
    }
  ],
  "still_growing": [
    {
      "headline": "One line. Kind, not clinical. Never a correction.",
      "signals": ["Copy from allowed_signal_names."],
      "seen_in": ["The activity that produced this."],
      "paragraph": "3-5 sentences. What they did, what it shows they already know, the small thing that is missing.",
      "suggestion": {
        "title": "One specific thing to try at home.",
        "body": "2-3 sentences. Concrete and actionable.",
        "because": "One sentence starting with 'Because', pointing at the actual evidence."
      }
    }
  ],
  "for_the_conference": {
    "headline": "Three things you could mention at a parent-teacher conference",
    "items": [
      {
        "point": "Something specific this child actually did. Name it.",
        "worth_asking": "A question the parent can ask the teacher. Start it with 'Worth asking' or 'Worth mentioning'."
      }
    ]
  },
  "closing": "1-2 sentences. Warm. This is the start of a conversation."
}

RULES

- "what_i_noticed": at most 4 items. Build them from `areas` and from
  `strengths` and `neutral_observations`. NEVER put a growth edge here.
- "still_growing": ONE ITEM FOR EVERY ENTRY IN `growth_edges`. Every single
  one. Do not merge them, do not drop them, do not pick the best few. If the
  evidence has five growth edges, write five items. The parent paid for all
  of them.
- "for_the_conference": exactly 3 items. At least one must be a strength -
  parents arrive at a conference braced for bad news. Each item names
  something specific the child did and ends with a question worth asking.
  Reading pace is the one thing a classroom teacher measures the same way
  this product does, so use it when the evidence has it.
- Every "signals" entry must appear verbatim in `allowed_signal_names`.
  There is no signal called "Adaptability". If you cannot find a name in
  that list, the observation does not exist.
- Every "seen_in" entry must be an activity that actually produced one of the
  signals in THAT item. Word Wizard does not get credit for a pattern the
  Logic Quest measured. The paragraph text follows the same rule: do not
  write that something "was also evident in" an activity that did not
  measure it.
- If `flawless_activities` is not empty, each one gets its own item in
  "what_i_noticed". A run with nothing to fault is still an observation.
- Never write: score, percent, grade level, above, below, average, advanced,
  behind, diagnosis, assessment score, excels, outstanding.
- Never compare this child to any other child or to a standard.
- Never name a question by its number. "2-4" and "s1_q2" mean nothing to a
  parent. Say what the question actually asked, or what kind it was.
- Use only facts that appear in the evidence. Invent nothing.
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
    # LS6: no invented period of observation. The activities took minutes.
    (re.compile(r"\bthis week\b", re.I), "invented observation period"),
    (re.compile(r"\bover the (past|last) (week|weeks|month|months)\b", re.I),
     "invented observation period"),
    (re.compile(r"\bour sessions\b", re.I), "invented observation period"),
    # "each session" implies repeated meetings that never happened. "each
    # week" does not - it is how a suggestion to a parent is phrased ("a few
    # minutes each week"), so it is advice, not an invented history.
    (re.compile(r"\b(each|every) session\b", re.I), "invented observation period"),
    (re.compile(r"\bover the weeks\b", re.I), "invented observation period"),
]

#: Eko's voice, as opposed to the product's promises above. Breaking one of
#: these makes the letter read less like someone who was in the room. It does
#: not harm the child, so it is worth a retry and never worth the fallback:
#: a parent is better served by a letter about their own child that says
#: "impressive" than by a generic letter that says nothing about them at all.
_STYLE_PATTERNS = [
    (re.compile(r"!"), "exclamation mark"),
    (re.compile(r"\bexcels?\b", re.I), "evaluation instead of observation"),
    (re.compile(r"\boutstanding\b", re.I), "evaluation instead of observation"),
    (re.compile(r"\bimpressive\b", re.I), "evaluation instead of observation"),
    (re.compile(r"\bremarkable\b", re.I), "evaluation instead of observation"),
    (re.compile(r"\bwonderful\b", re.I), "evaluation instead of observation"),
    (re.compile(r"\bwhat a delight\b", re.I), "evaluation instead of observation"),
    (re.compile(r"\bthe child (demonstrates|exhibits|displays)\b", re.I),
     "report language instead of Eko's voice"),
]

#: A quoted misspelling must never land as a correction. The shape is always:
#: here is what they did, here is what it shows they know, here is what is
#: missing - never "they got these wrong".
_CORRECTION_PATTERNS = [
    (re.compile(r"\bgot (these|them|it|that|those) wrong\b", re.I), "got it wrong"),
    (re.compile(r"\bneeds? to work on\b", re.I), "needs to work on"),
    (re.compile(r"\b(spelled|wrote|said|read) (it |them |these |this )?incorrectly\b", re.I),
     "marking the attempt incorrect"),
    (re.compile(r"\bshould have (written|spelled|said)\b", re.I), "correcting the child"),
    (re.compile(r"\bthe correct spelling is\b", re.I), "correcting the child"),
    (re.compile(r"\binstead of the correct\b", re.I), "correcting the child"),
    (re.compile(r"\bmade \w+ (mistakes|errors)\b", re.I), "counting mistakes"),
    (re.compile(r"\bstruggle[sd]?\b", re.I), "deficit framing"),
    (re.compile(r"\bfail(s|ed|ure)?\b", re.I), "deficit framing"),
    (re.compile(r"\bweakness(es)?\b", re.I), "deficit framing"),
    (re.compile(r"\bpoor\b", re.I), "deficit framing"),
]

#: LS8: no pronoun is stored for a child, so the letter uses the name and
#: they/them. Guessing misgenders a real child.
_GENDERED_PRONOUNS = re.compile(r"\b(he|she|his|her|hers|him|himself|herself)\b", re.I)

#: Verbs that have to move with the pronoun, or "he is" becomes "they is".
_VERB_AGREEMENT = {
    "is": "are",
    "was": "were",
    "has": "have",
    "does": "do",
    "goes": "go",
    "isn't": "aren't",
    "wasn't": "weren't",
    "hasn't": "haven't",
    "doesn't": "don't",
}

_PRONOUN_AND_VERB = re.compile(
    r"\b(he|she)\s+("
    + "|".join(re.escape(v) for v in sorted(_VERB_AGREEMENT, key=len, reverse=True))
    + r")\b",
    re.I,
)

#: A following word means the pronoun was a determiner ("their reading");
#: punctuation or the end of a clause means it was an object ("helped them").
_FOLLOWED_BY_A_WORD = re.compile(r"\s+\w")


def _match_case(source: str, replacement: str) -> str:
    """Keep the capitalisation of the word being replaced."""
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def neutralise_pronouns(text: str) -> str:
    """Rewrite gendered pronouns to they/them (LS8).

    This is a repair rather than a rejection. A letter is worth more to a
    parent than a guardrail is: discarding an otherwise good letter over one
    pronoun leaves them with the generic fallback, which says nothing about
    their child at all. So the pronouns are rewritten and the letter
    survives. The validator then checks the result and should never fire.
    """

    def verb_pair(match: "re.Match[str]") -> str:
        pronoun, verb = match.group(1), match.group(2)
        return (
            _match_case(pronoun, "they")
            + " "
            + _match_case(verb, _VERB_AGREEMENT[verb.lower()])
        )

    text = _PRONOUN_AND_VERB.sub(verb_pair, text)

    def single(match: "re.Match[str]") -> str:
        word = match.group(0)
        lowered = word.lower()
        if lowered in ("he", "she"):
            return _match_case(word, "they")
        if lowered == "him":
            return _match_case(word, "them")
        if lowered in ("himself", "herself"):
            return _match_case(word, "themselves")
        if lowered == "hers":
            return _match_case(word, "theirs")
        if lowered == "his":
            return _match_case(word, "their")
        if lowered == "her":
            following = match.string[match.end() : match.end() + 3]
            if _FOLLOWED_BY_A_WORD.match(following):
                return _match_case(word, "their")
            return _match_case(word, "them")
        return word

    return _GENDERED_PRONOUNS.sub(single, text)


#: Fields the writer copies verbatim out of the evidence. Rewriting a word
#: inside one of these turns a real signal name into an invented one, which
#: is the very thing LS10 is about.
_COPIED_VERBATIM = ("signals", "seen_in", "area_display_name", "badge")


def _calm_exclamations(value: Any) -> Any:
    """Eko does not exclaim. A full stop says the same thing."""
    if isinstance(value, str):
        return re.sub(r"!+", ".", value)
    if isinstance(value, list):
        return [_calm_exclamations(v) for v in value]
    if isinstance(value, dict):
        return {k: _calm_exclamations(v) for k, v in value.items()}
    return value


def _repair(letter: Any, evidence: Optional[Dict[str, Any]] = None) -> Any:
    """Fix what can be fixed without asking the model again.

    A guardrail exists to keep a bad sentence away from a parent, not to
    throw away a good letter over a cosmetic slip. Anything deterministic -
    a pronoun, a section that should not exist, one item too many - is
    repaired here, so a retry and the generic fallback are reserved for
    problems only the writer can fix: a dropped growth edge, a praise
    headline over a growth edge, a misspelling that reads as a correction.
    """
    letter = _neutralise_letter(letter)
    if not isinstance(letter, dict):
        return letter

    letter = _calm_exclamations(letter)

    # LS5 / LS3: these sections no longer exist.
    for key in _REMOVED_KEYS:
        letter.pop(key, None)

    # A cap is a matter of length, not of truth.
    noticed = letter.get("what_i_noticed")
    if isinstance(noticed, list) and len(noticed) > _MAX_NOTICED:
        logger.info(
            "snapshot writer: trimming what_i_noticed from %d to %d",
            len(noticed), _MAX_NOTICED,
        )
        letter["what_i_noticed"] = noticed[:_MAX_NOTICED]

    growing = letter.get("still_growing")
    if isinstance(growing, list) and len(growing) > _ABSOLUTE_MAX_GROWING:
        letter["still_growing"] = growing[:_ABSOLUTE_MAX_GROWING]

    conference = letter.get("for_the_conference")
    if isinstance(conference, dict):
        items = conference.get("items")
        if isinstance(items, list) and len(items) > 3:
            conference["items"] = items[:3]

    # LS2: an activity that did not produce the signal is simply struck from
    # the list. Which activity measured what is Stage A's fact, not the
    # writer's opinion, so there is nothing to ask the writer about.
    if evidence:
        _strike_unearned_activities(letter, evidence)

    return letter


def _strike_unearned_activities(
    letter: Dict[str, Any], evidence: Dict[str, Any]
) -> None:
    """Drop any seen_in entry the item's own signals did not come from."""
    produced_by: Dict[str, set] = {}
    for signal in (
        evidence.get("strengths", [])
        + evidence.get("growth_edges", [])
        + evidence.get("neutral_observations", [])
    ):
        produced_by.setdefault(signal["signal_name"], set()).add(signal["seen_in"])
    if not produced_by:
        return

    for section in ("what_i_noticed", "still_growing"):
        for item in letter.get(section) or []:
            named = item.get("signals") or []
            earned = set()
            for name in named:
                earned |= produced_by.get(name, set())
            if not earned:
                continue
            kept = [s for s in (item.get("seen_in") or []) if s in earned]
            if kept != item.get("seen_in"):
                logger.info(
                    "snapshot writer: striking unearned activities from %s: %s",
                    section,
                    set(item.get("seen_in") or []) - set(kept),
                )
                # Never leave it empty: the signals did come from somewhere.
                item["seen_in"] = kept or sorted(earned)


def _neutralise_letter(value: Any) -> Any:
    """Walk the letter and neutralise the prose, leaving copied names alone."""
    if isinstance(value, str):
        return neutralise_pronouns(value)
    if isinstance(value, list):
        return [_neutralise_letter(v) for v in value]
    if isinstance(value, dict):
        return {
            k: v if k in _COPIED_VERBATIM else _neutralise_letter(v)
            for k, v in value.items()
        }
    return value


_GENERIC_LETTER: Dict[str, Any] = {
    "opening": {
        "headline": "We sat down together and worked through four activities.",
        "paragraph": (
            "Thank you for letting me spend this time with your child. "
            "There is plenty here worth talking about, and the notes below "
            "are a starting point for that conversation."
        ),
    },
    "what_i_noticed": [],
    "still_growing": [],
    "for_the_conference": {
        "headline": "Things you could mention at a parent-teacher conference",
        "items": [],
    },
    "closing": (
        "This is a starting point for a conversation about how your child "
        "learns. It is not a diagnosis or a formal assessment, and it "
        "compares your child to no one."
    ),
}

#: Keys the letter must carry, and the ones it must no longer carry.
_REQUIRED_KEYS = ("opening", "what_i_noticed", "still_growing", "for_the_conference")
_REMOVED_KEYS = ("what_helped", "full_picture")

#: LS9: the ceiling that dropped three of Pranav's five growth edges is gone.
#: A ceiling still exists, but only as a sanity bound on a runaway model, and
#: it is never lower than the number of growth edges the engine found.
#: How many times to ask before settling. Each attempt carries every rule
#: broken so far.
_MAX_ATTEMPTS = 3

_MAX_NOTICED = 4
_ABSOLUTE_MAX_GROWING = 12


def style_violations(letter: Dict[str, Any]) -> List[str]:
    """Eko's voice only. Never a reason to withhold the letter."""
    text = json.dumps(letter, ensure_ascii=False)
    found: List[str] = []
    for pattern, label in _STYLE_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append(f"{_STYLE_PREFIX}{label}: {match.group(0)!r}")
    return found


#: Marks a violation as a matter of voice rather than of harm.
_STYLE_PREFIX = "voice - "


class SnapshotWriter:
    """Calls the model to write the snapshot letter, then validates it."""

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
            # Every attempt is told about every rule broken so far, not only
            # the last one's. With one retry the writer traded one violation
            # for a different one each time and the parent got the generic
            # letter, which says nothing about their child.
            seen: List[str] = []
            best: Optional[Dict[str, Any]] = None
            best_style: List[str] = []

            for attempt in range(_MAX_ATTEMPTS):
                letter = _repair(
                    self._generate(evidence, violations=seen or None), evidence
                )
                violations = self._validate(letter, evidence)
                harm = [v for v in violations if not v.startswith(_STYLE_PREFIX)]
                style = [v for v in violations if v.startswith(_STYLE_PREFIX)]

                if not harm and (best is None or len(style) < len(best_style)):
                    best, best_style = letter, style
                if not violations:
                    return self._finalise(letter, evidence)

                logger.warning(
                    "snapshot writer: attempt %d broke %s", attempt + 1, violations
                )
                for violation in violations:
                    if violation not in seen:
                        seen.append(violation)

            # Nothing clean. A letter that only slips on voice still belongs
            # to this child; the generic letter belongs to no one.
            if best is not None:
                logger.warning(
                    "snapshot writer: shipping a letter with voice slips %s",
                    best_style,
                )
                return self._finalise(best, evidence, style_slips=best_style)

            logger.warning("snapshot writer: no usable letter, using generic")
            return self._fallback(evidence)
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
                "\n\nPREVIOUS ATTEMPT FAILED THESE RULES - do not repeat them:\n"
                + "\n".join(f"- {v}" for v in violations)
            )

        growth_count = len(evidence.get("growth_edges", []))
        user_prompt = (
            "Below is the structured evidence for one child. "
            "Write the letter now using ONLY this data.\n\n"
            f"This child has {growth_count} growth edge(s). "
            f'"still_growing" must contain exactly {growth_count} item(s), '
            "one for each, in the order given.\n\n"
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
            # The letter got longer: every growth edge now reaches the parent,
            # and the conference section is new.
            max_tokens=5000,
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

        for key in _REQUIRED_KEYS:
            if key not in letter:
                violations.append(f"missing key: {key}")
        if violations:
            return violations

        for key in _REMOVED_KEYS:
            if letter.get(key):
                violations.append(
                    f"'{key}' no longer exists in the letter and must be omitted"
                )

        noticed = letter.get("what_i_noticed") or []
        growing = letter.get("still_growing") or []
        conference = letter.get("for_the_conference") or {}
        conference_items = conference.get("items") or []

        if len(noticed) > _MAX_NOTICED:
            violations.append(f"more than {_MAX_NOTICED} items in what_i_noticed")

        # LS9: every growth edge the engine found must reach the parent.
        expected_growth = len(evidence.get("growth_edges", []))
        if len(growing) < expected_growth:
            missing = [
                g["signal_name"]
                for g in evidence.get("growth_edges", [])[len(growing):]
            ]
            violations.append(
                f"still_growing has {len(growing)} items but the evidence has "
                f"{expected_growth} growth edges; every one must reach the "
                f"parent (missing at least: {', '.join(missing)})"
            )
        if len(growing) > max(expected_growth, _ABSOLUTE_MAX_GROWING):
            violations.append("still_growing invents growth edges not in the evidence")

        for item in growing:
            suggestion = item.get("suggestion") or {}
            if not suggestion.get("because"):
                violations.append("a still_growing item has no 'because'")

        # Exactly three, and never "if it wrote any". The old check was
        # skipped on an empty list, which let a "Three things you could
        # mention" headline through with nothing underneath it. The generic
        # fallback never reaches here, so it keeps its own headline.
        if len(conference_items) != 3:
            violations.append(
                f"for_the_conference must hold exactly 3 items, not "
                f"{len(conference_items)}: this is the section the parent "
                "takes to the conference, and the headline promises three"
            )
        for item in conference_items:
            if not item.get("worth_asking"):
                violations.append(
                    "a conference item has no question for the parent to ask"
                )

        violations.extend(self._check_signal_names(letter, evidence))
        violations.extend(self._check_polarity(letter, evidence))
        violations.extend(self._check_seen_in(letter, evidence))

        # Forbidden language anywhere in the serialised letter.
        text = json.dumps(letter, ensure_ascii=False)
        for pattern, label in _FORBIDDEN_PATTERNS:
            match = pattern.search(text)
            if match:
                violations.append(f"forbidden {label}: {match.group(0)!r}")

        violations.extend(style_violations(letter))

        # A quoted misspelling must never read as a correction.
        for pattern, label in _CORRECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                violations.append(
                    f"reads as a correction, not an explanation ({label}): "
                    f"{match.group(0)!r}"
                )

        # LS8: one voice for the child throughout, and it is never a guess.
        match = _GENDERED_PRONOUNS.search(text)
        if match:
            child = evidence.get("child_name") or "the child"
            violations.append(
                f"gendered pronoun {match.group(0)!r}: no pronoun is known for "
                f"this child, so use {child} or they/them throughout"
            )

        return violations

    # ------------------------------------------------------------------
    @staticmethod
    def _check_signal_names(
        letter: Dict[str, Any], evidence: Dict[str, Any]
    ) -> List[str]:
        """LS10: no signal name that has no tag behind it."""
        allowed = set(evidence.get("allowed_signal_names") or [])
        if not allowed:
            return []

        violations: List[str] = []
        for section in ("what_i_noticed", "still_growing"):
            for item in letter.get(section) or []:
                for name in item.get("signals") or []:
                    if name not in allowed:
                        violations.append(
                            f"{section} names a signal that does not exist: "
                            f"{name!r}"
                        )
        return violations

    @staticmethod
    def _check_polarity(
        letter: Dict[str, Any], evidence: Dict[str, Any]
    ) -> List[str]:
        """LS1: a praise headline must never sit over a growth edge.

        guardrails_passed was true on both reviewed letters while one of them
        opened a section with "Vedika excels in recognizing patterns" over the
        pattern_detection_emerging tag. The guardrail was not checking this.
        The check is structural rather than a reading of the prose: what the
        writer calls a strength must be backed by a strength tag.
        """
        polarity_of = {
            signal["signal_name"]: signal["polarity"]
            for signal in (
                evidence.get("strengths", [])
                + evidence.get("growth_edges", [])
                + evidence.get("neutral_observations", [])
            )
        }
        if not polarity_of:
            return []

        violations: List[str] = []
        for item in letter.get("what_i_noticed") or []:
            for name in item.get("signals") or []:
                if polarity_of.get(name) == "growth_edge":
                    violations.append(
                        f"what_i_noticed praises {name!r}, which is a growth "
                        "edge; move it to still_growing"
                    )
        for item in letter.get("still_growing") or []:
            for name in item.get("signals") or []:
                if polarity_of.get(name) == "strength":
                    violations.append(
                        f"still_growing lists {name!r}, which is a strength; "
                        "move it to what_i_noticed"
                    )
        return violations

    @staticmethod
    def _check_seen_in(
        letter: Dict[str, Any], evidence: Dict[str, Any]
    ) -> List[str]:
        """LS2: an activity is only named where it produced the signal."""
        all_signals = (
            evidence.get("strengths", [])
            + evidence.get("growth_edges", [])
            + evidence.get("neutral_observations", [])
        )
        activities_for: Dict[str, set] = {}
        for signal in all_signals:
            activities_for.setdefault(signal["signal_name"], set()).add(
                signal["seen_in"]
            )
        every_activity = {s["seen_in"] for s in all_signals}
        if not every_activity:
            return []

        violations: List[str] = []
        for section in ("what_i_noticed", "still_growing"):
            for item in letter.get(section) or []:
                named = set(item.get("signals") or [])
                allowed = set()
                for name in named:
                    allowed |= activities_for.get(name, set())
                for seen in item.get("seen_in") or []:
                    if seen not in every_activity:
                        violations.append(
                            f"{section} references an unknown activity: {seen!r}"
                        )
                    elif allowed and seen not in allowed:
                        violations.append(
                            f"{section} credits {seen!r} with signals it did "
                            f"not produce (it produced none of {sorted(named)})"
                        )
        return violations

    # ------------------------------------------------------------------
    def _fallback(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        letter = json.loads(json.dumps(_GENERIC_LETTER))
        return self._finalise(letter, evidence, llm_generated=False)

    @staticmethod
    def _finalise(
        letter: Dict[str, Any],
        evidence: Dict[str, Any],
        llm_generated: bool = True,
        style_slips: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        name = evidence.get("child_name", "your child")
        closing = letter.get("closing") or _GENERIC_LETTER["closing"]
        if "{name}" in closing:
            closing = closing.replace("{name}", name)
        letter["closing"] = closing

        # LS5 / LS3: these sections are gone. Strip them if a model produced
        # them anyway, so nothing invented reaches the parent.
        for key in _REMOVED_KEYS:
            letter.pop(key, None)

        letter["branding"] = "The Dear Parent Project"
        letter["disclaimer"] = (
            f"This is a starting point for a conversation about how {name} "
            "learns. It is not a diagnosis or a formal assessment, and it "
            "compares them to no one."
        )
        letter["meta"] = {
            "llm_generated": llm_generated,
            "tests_completed": evidence.get("tests_completed", []),
            # Every promise the product makes to a parent held. Voice slips
            # are reported separately: they are a matter of how it reads.
            "guardrails_passed": llm_generated,
            "voice_slips": list(style_slips or []),
            # LS9: what the engine found, beside what the letter carried, so
            # a dropped growth edge is visible rather than silent.
            "growth_edges_found": len(evidence.get("growth_edges", [])),
            "growth_edges_written": len(letter.get("still_growing") or []),
        }
        return letter


def get_snapshot_writer() -> SnapshotWriter:
    return SnapshotWriter()
