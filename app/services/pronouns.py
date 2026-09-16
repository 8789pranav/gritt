"""The pronoun set the Learning Snapshot uses for one child.

A letter about one child is written in the singular. Writing "they worked it
out and they were pleased" about a single seven-year-old reads like a form
letter, and it is the first thing a parent notices.

The child's own pronouns are carried through the pipeline as data when the
profile is explicit. When it is not, the system guesses from the first name,
and only falls back to the child's name itself when the name is ambiguous.
The letter never uses "they", "their", or "them" for the child.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

#: What a profile might store, and the pronoun set it means.
_BY_VALUE: Dict[str, str] = {
    "he": "he", "him": "he", "his": "he", "he/him": "he",
    "boy": "he", "male": "he", "m": "he", "man": "he", "son": "he",
    "she": "she", "her": "she", "hers": "she", "she/her": "she",
    "girl": "she", "female": "she", "f": "she", "woman": "she",
    "daughter": "she",
    "they": "name", "them": "name", "they/them": "name",
    "nonbinary": "name", "non-binary": "name", "nb": "name",
    "other": "name", "prefer not to say": "name", "unspecified": "name",
}

#: Profile fields that could carry it, most explicit first.
_FIELDS = ("pronouns", "pronoun", "gender", "sex")

_SETS: Dict[str, Dict[str, Any]] = {
    "he": {
        "key": "he",
        "subject": "he",
        "object": "him",
        "possessive": "his",
        "possessive_pronoun": "his",
        "reflexive": "himself",
        "singular_verbs": True,
        "known": True,
    },
    "she": {
        "key": "she",
        "subject": "she",
        "object": "her",
        "possessive": "her",
        "possessive_pronoun": "hers",
        "reflexive": "herself",
        "singular_verbs": True,
        "known": True,
    },
    "name": {
        "key": "name",
        "subject": "this child",
        "object": "this child",
        "possessive": "this child's",
        "possessive_pronoun": "this child's",
        "reflexive": "this child",
        "singular_verbs": True,
        "known": True,
    },
}


def _load_guesser():
    """Lazy import so the module loads even when gender-guesser is not installed."""
    try:
        from gender_guesser.detector import Detector

        return Detector()
    except Exception:
        return None


_GUESSER = _load_guesser()

#: Words that sometimes prefix a child name in test data but are not names.
_PREFIXES = {"new", "old", "the", "a", "an"}


def _first_name(name: str) -> str:
    """The best token to guess gender from, with prefixes skipped."""
    name = str(name or "").strip()
    if not name:
        return ""
    parts = [
        p.strip('.,\'"-_')
        for p in name.split()
        if p.strip('.,\'"-_').isalpha()
    ]
    for part in parts:
        if part.lower() not in _PREFIXES:
            return part
    return parts[0] if parts else name.split()[0]


def _guess_pronoun(name: str) -> str:
    """Return he, she, or name based on the name tokens."""
    if _GUESSER is None:
        return "name"
    parts = [
        p.strip('.,\'"-_')
        for p in str(name or "").split()
        if p.strip('.,\'"-_').isalpha()
    ]
    for part in parts:
        if part.lower() in _PREFIXES:
            continue
        guess = _GUESSER.get_gender(part)
        if guess in ("male", "mostly_male"):
            return "he"
        if guess in ("female", "mostly_female"):
            return "she"
    return "name"


def pronouns_for(child_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve a child profile to the pronoun set the letter should use.

    An explicit he/she in the profile wins. Anything else (they/them,
    prefer not to say, missing) is guessed from the child's first name.
    If the name is ambiguous, the letter is written around the child by name.
    """
    for field in _FIELDS:
        raw = (child_data or {}).get(field)
        if raw is None:
            continue
        key = _BY_VALUE.get(str(raw).strip().lower())
        if key in ("he", "she"):
            return dict(_SETS[key])

    # Guess from the child's first name; fall back to referring by name.
    return dict(_SETS[_guess_pronoun(child_data.get("name", ""))])


def describe(pronouns: Dict[str, Any], child_name: str) -> str:
    """One line for the writer prompt, in the words it has to obey."""
    key = pronouns.get("key", "name")
    name = child_name or "this child"

    if key in ("he", "she"):
        return (
            f"{name} takes {pronouns['subject']}/"
            f"{pronouns['object']}/{pronouns['possessive']}. Use those and no "
            f"others for {name}: {pronouns['subject']} read, I asked "
            f"{pronouns['object']}, {pronouns['possessive']} spelling, "
            f"{pronouns['reflexive']}. Never write they, them, their or "
            f"themself about {name}, and keep the verbs singular: "
            f"{pronouns['subject']} was, {pronouns['subject']} has, "
            f"{pronouns['subject']} does."
        )

    return (
        f"No clear pronouns are recorded for {name}. Use {name} or "
        f"'this child' whenever you mean {name}. Never use he, she, they, "
        f"them, their or themself about {name}, and keep the verbs singular: "
        f"{name} was, {name} has, {name} does."
    )
