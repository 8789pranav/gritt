"""The pronoun set the Learning Snapshot uses for one child.

A letter about one child is written in the singular. Writing "they worked it
out and they were pleased" about a single seven-year-old reads like a form
letter, and it is the first thing a parent notices.

So the child's own pronouns are carried through the pipeline as data. They
come from the child's profile - never from the name, which tells you nothing
and gets it wrong often enough to matter. When the profile does not say,
the letter leans on the child's name and falls back to they/them, which is
wrong for nobody.
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
    "they": "they", "them": "they", "they/them": "they",
    "nonbinary": "they", "non-binary": "they", "nb": "they",
    "other": "they", "prefer not to say": "they", "unspecified": "they",
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
    "they": {
        "key": "they",
        "subject": "they",
        "object": "them",
        "possessive": "their",
        "possessive_pronoun": "theirs",
        "reflexive": "themselves",
        "singular_verbs": False,
        "known": False,
    },
}


def pronouns_for(child_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve a child profile to the pronoun set the letter should use.

    Unknown or unreadable means they/them: the letter is then written around
    the child's name, which is always right.
    """
    for field in _FIELDS:
        raw = (child_data or {}).get(field)
        if raw is None:
            continue
        key = _BY_VALUE.get(str(raw).strip().lower())
        if key:
            return dict(_SETS[key])
    return dict(_SETS["they"])


def describe(pronouns: Dict[str, Any], child_name: str) -> str:
    """One line for the writer prompt, in the words it has to obey."""
    if not pronouns.get("known"):
        return (
            f"No pronouns are recorded for {child_name or 'this child'}. Use "
            f"{child_name or 'the child'}'s name wherever you can, and "
            "they/them only where a pronoun is unavoidable. Never guess he "
            "or she. Keep the verbs with they/them plural: they were, they "
            "have, they do."
        )
    return (
        f"{child_name or 'This child'} takes {pronouns['subject']}/"
        f"{pronouns['object']}/{pronouns['possessive']}. Use those and no "
        f"others for {child_name or 'the child'}: {pronouns['subject']} "
        f"read, I asked {pronouns['object']}, {pronouns['possessive']} "
        f"spelling, {pronouns['reflexive']}. Never write they, them or their "
        f"about {child_name or 'the child'}, and keep the verbs singular: "
        f"{pronouns['subject']} was, {pronouns['subject']} has, "
        f"{pronouns['subject']} does."
    )
