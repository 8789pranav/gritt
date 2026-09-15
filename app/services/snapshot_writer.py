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
from app.services.pronouns import describe as describe_pronouns

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are Eko. You sat next to this child through four
activities and you are telling their parent what you saw.

Not a teacher grading. Not a cartoon. Someone who was in the room.

VOICE - these are absolute

1. First person, past tense. "I noticed." "I watched." "I sat with."
   Never "The child demonstrates" or "The child exhibits".
2. Notice, do not evaluate. "Pranav wrote fone for phone." Never "excels at",
   "is strong in", "is working at grade level".
3. Short sentences. Plain words. "Say those out loud. Every sound is right."
   Never "Demonstrated a thoughtful approach to problem-solving".
4. The warmth is in the watching, not in the adjectives. "He did not stop
   and he did not guess." Never "Wonderful", "Impressive", "What a delight".
5. NO EXCLAMATION MARKS. Not one, anywhere in the letter.
6. Quote what the child actually did. The real words: fone, graff, clunck.
   Never "Spelling conventions are still emerging".
7. Never correct, always explain. "He heard the word perfectly. He has not
   met the rule yet." Never "got these wrong" or "needs to work on".
8. No invented setting. Write only about what happened in the activities.
   Never "This week I had the pleasure of observing" or "Our sessions".
   The evidence tells you the real span. Four activities finished minutes
   apart is one sitting, not a week and not a series of meetings.

GRAMMAR - check every sentence on its own

Read each sentence back before you keep it. It must be a complete sentence
with a subject and a verb, it must end in a full stop, and the verb must
agree with its subject. Past tense for what happened in the room, present
tense for what is true of the child now, and never both in one sentence
without reason. One idea per sentence. No fragments, no comma splices, no
sentence that says the previous one again in different words.

PRONOUNS

The `pronouns` block in the evidence gives the pronouns for THIS child. Use
those and no others when you mean the child, and keep every verb agreeing
with them. Other people in the letter keep their own pronouns: a grandmother
in a story is still "she", and the parent you are writing to is "you".

NEVER COUNT

This letter carries no scores and no tallies. Not "15 of 15", not "fifteen
words", not "all fifteen", not "three questions", not a percentage, not
"most of them". Say what happened instead: "Every word he wrote was spelled
correctly." "He worked out the ones the story only hints at." "A few sounds
came out differently." Times are fine, because they describe how he worked:
"thirty-three seconds", "longer than he spent on anything else all session".
Counting what a child got right or wrong is not.

THE MOST IMPORTANT RULE

The evidence contains `what_the_child_did`: the actual words they wrote, the
actual sentences they read, the actual questions they worked out and missed.
USE THEM. Quote them. A letter built from signal names could be about any
child. A letter that quotes what this child wrote could only be about them.

HOW TO WRITE ABOUT A MISSPELLING

This is the shape, every time: here is what they did, here is what it shows
they already know, here is the small thing that is missing.

  "Pranav wrote fone for phone, graff for graph, and clunck for clunk.

   Say those out loud. Every sound is right. He heard each word and wrote
   down exactly what he heard. What he has not met yet is the rule that some
   /f/ sounds are spelled ph, and that clunk does not take a c before the k.

   That is a good place to be. Sounding out is the harder skill and he has
   it. Spelling rules are a list to learn."

It must never land as a correction.

HOW TO WRITE ABOUT READING ALOUD

  "Pranav read every sentence without skipping a word, at a comfortable
   pace.

   Twice he held a sound while working out a longer word. Butterfly.
   Elephants. He did not stop, he did not guess, he stretched the sound and
   kept going. That is a strategy, not a stumble, and it fades on its own as
   words become familiar."

THE OPENING

The first thing a parent reads describes HOW their child works. Not what
they scored, and not what they are. It is the only part of the letter that
is allowed to be about the whole child, and it is the hardest to write.

Four steps, in this order:

1. Lead with the way this child approaches things, seen across the whole
   sitting. Slowly and carefully. Quickly and confidently. Stays with hard
   things. Moves on fast. One sentence, and it is the headline.
2. Prove it with one concrete thing they did, with the real detail: a time
   in seconds, a word they wrote, a puzzle they stayed with. Never a count
   of right answers.
3. Draw on at least TWO activities. A way of working that shows up in only
   one activity is an activity result wearing a disguise.
4. Name one place they are still working, plainly, in a clause or a short
   sentence, inside the opening. Not a section and not a worry - just the
   honest thing, so the parent knows the letter is straight with them before
   they read any praise.

Two ways to get this wrong, and both are rejected:

  COUNTING. "Answered all 13 questions correctly." "Spelled every word
  correctly." "With perfect accuracy." A count is a score, and spelling the
  number out does not change that.

  LABELLING. "Has a keen eye for patterns." "Has a knack for..." "Is a
  strong reader." "Showed a strong understanding of..." These say what the
  child IS. This product says what a child DID.

Never name an activity in the opening. Word Wizard, Logic Quest, Story
Explorer and Voice Challenge are our names, not the parent's, and they make
the letter read as a test report. Say what happened, not which module it
happened in.

These numbers are still welcome, because they describe how the child worked
rather than how much they got right: time spent ("a minute and a half on one
word"), how many times something happened ("twice he held a sound"), pace in
words rather than digits ("faster than most children her age"), and above
all the child's own words - stand, pie, fone.

The test: could this opening be moved onto another child? If yes, rewrite
it. And if the data does not support a way of working - an ordinary pace, no
long pauses, no fast guesses - do not invent one. Open with the strongest
concrete thing they did instead. An honest small opening beats a confident
invented one.

STRUCTURE - return JSON with exactly these keys

{
  "opening": {
    "headline": "One sentence. The way this child works. No count, no activity name, and never what the child IS.",
    "paragraph": "3-5 sentences. The proof: one concrete thing they did with the real detail, drawing on at least two activities, and one plain clause naming where they are still working. You may open it with a single short sentence about the sitting and how long it took, using the span in `session`."
  },
  "what_i_noticed": [
    {
      "headline": "One line. What you saw. Short.",
      "area_display_name": "Copy exactly from the evidence.",
      "signals": ["Copy names EXACTLY from allowed_signal_names. Never invent one."],
      "seen_in": ["Only activities listed in seen_in for these signals."],
      "badge": "seen_repeatedly or seen_once, copied from the evidence.",
      "quotes": [{"wrote": "stand", "for_word": "strand"}],
      "paragraph": "3-5 sentences. Quote actual words, sentences or questions."
    }
  ],
  "still_growing": [
    {
      "headline": "One line. Kind, not clinical. Never a correction.",
      "signals": ["Every signal this item covers. Copy from allowed_signal_names."],
      "seen_in": ["The activities that produced these signals."],
      "paragraph": "3-5 sentences. What they did, what it shows they already know, the small thing that is missing.",
      "suggestion": {
        "title": "One specific thing to try at home. Four or five words.",
        "body": "2-3 sentences. Concrete and actionable.",
        "because": "One sentence closing the item, pointing at the evidence in this item. Plain English, not a formula."
      }
    }
  ],
  "level_note": {
    "headline": "One note about the level.",
    "paragraph": "2-3 sentences. ONLY when the evidence asks for it - see the rules. Otherwise omit this key or set it to null."
  },
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
- "quotes" is optional and only for spellings. Each pair must be a word and
  the attempt this child actually wrote for it, copied exactly from
  `what_the_child_did`. Invent nothing; omit the key when there is nothing
  to quote.
- "still_growing": THREE items where the evidence allows it, and never more
  than five. Every growth edge in the evidence must be covered by one of
  them - list its signal name in that item's "signals". Growth edges that
  are really the same finding belong in ONE item: four read-aloud sounds are
  one thing to work on at home, not four. Merging them is how the letter
  stays readable. Dropping one is not allowed.
- Order the still_growing items so the most useful to the parent comes first.
- "level_note": include it ONLY when `level_fit` carries a "suggest" value,
  and write it from the "why" given there, in your own plain words. When
  `level_fit` has no suggestion, the key must be absent or null.
- "for_the_conference": exactly 3 items. At least one must be a strength -
  parents arrive at a conference braced for bad news. Each item names
  something specific the child did and ends with a question worth asking.
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

BEING SPECIFIC IS NOT OPTIONAL

`must_mention` lists facts this letter has to contain. A letter without them
is rejected and you will be asked again. Quote them exactly as written.

`could_mention` holds the rest of what this child actually did: the words
they wrote, the sentences they read, the stories, the questions they worked
out and the answers they chose. Use as many as fit naturally. Every one you
use is a sentence a parent recognises as their own child.

Never write a paragraph that would be true of any child. "They are
developing this skill" says nothing. "He chose The oak tree when the story
said The tomato plants" says everything. If a paragraph could be moved into
another child's letter unchanged, rewrite it.
"""


#: The part of the brief that changes with the child in front of you: their
#: pronouns, how long the sitting actually took, and whether this set fitted
#: them. None of it is hardcoded in the prompt, because none of it is true
#: of every child.
def _child_specific_rules(evidence: Dict[str, Any]) -> str:
    name = evidence.get("child_name") or "this child"
    pronouns = evidence.get("pronouns") or {}
    session = evidence.get("session") or {}
    level = evidence.get("level_fit") or {}

    lines = ["THIS CHILD", "", describe_pronouns(pronouns, name)]

    span = session.get("span_phrase")
    activities = session.get("activities") or evidence.get("activities_completed") or []
    if span and activities:
        lines.append(
            "\nThe sitting took about %s, across %s activities, one after "
            "another. Open the letter with that, in your own words, and "
            "invent no other occasion."
            % (span, _spell_small_number(len(activities)))
        )

    if level.get("suggest"):
        lines.append(
            "\nWrite a level_note. What it has to say, in your own plain "
            "words: %s Name %s as the thing to try next time, and do not "
            "turn it into a judgement about this child."
            % (level["why"], level["suggest"])
        )
    else:
        lines.append("\nThis set fitted this child. Omit level_note entirely.")

    return "\n".join(lines)


_SMALL_NUMBERS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}


def _spell_small_number(value: int) -> str:
    return _SMALL_NUMBERS.get(value, str(value))


#: Written-out numbers count exactly as much as digits do. "Fifteen of
#: fifteen" is the same tally as "15/15", and it is the one a model reaches
#: for once digits are blocked.
_NUMBER_WORD = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty)"
)

#: The things a snapshot could be caught counting.
_COUNTABLE = (
    r"(?:words?|questions?|puzzles?|sentences?|answers?|items?|stories|"
    r"story|spellings?)"
)

_FORBIDDEN_PATTERNS = [
    (re.compile(r"\d+\s*%", re.I), "percentage"),
    (re.compile(r"\d+\s*out of\s*\d+", re.I), "score ratio"),
    # A tally of what the child got right or wrong, however it is spelled.
    (re.compile(_NUMBER_WORD + r"\s+(?:of|out of)\s+" + _NUMBER_WORD, re.I),
     "count of right or wrong"),
    (re.compile(
        r"\b(?:all|only|just|every one of|the first|the last)\s+"
        + _NUMBER_WORD + r"\s+" + _COUNTABLE, re.I),
     "count of right or wrong"),
    (re.compile(
        r"\b" + _NUMBER_WORD + r"\s+(?:of\s+(?:the|his|her|their)\s+)?"
        + _COUNTABLE
        + r"\s+(?:were\s+|was\s+|came\s+back\s+)?"
        r"(?:correct|right|wrong|correctly|incorrectly|spelled correctly)",
        re.I),
     "count of right or wrong"),
    (re.compile(
        r"\b(?:spelled|wrote|answered|read|worked out|got|missed|named)\s+"
        r"(?:all\s+)?" + _NUMBER_WORD + r"\s+" + _COUNTABLE, re.I),
     "count of right or wrong"),
    (re.compile(
        r"\b" + _COUNTABLE + r"\s+(?:correct|right|wrong)\b", re.I),
     "count of right or wrong"),
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

#: The pronouns a letter may not use when nothing is known about the child:
#: guessing misgenders a real child, so the letter uses the name and
#: they/them instead.
_GENDERED_PRONOUNS = re.compile(r"\b(he|she|his|her|hers|him|himself|herself)\b", re.I)

#: The plural forms, for the opposite check: once a child's pronouns ARE
#: known, "they worked it out and they were pleased" reads like a form letter
#: about nobody, which is the complaint this exists to catch.
_PLURAL_PRONOUNS = re.compile(
    r"\b(they|them|their|theirs|themselves|themself)\b", re.I
)

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


#: Slips that are a matter of typing rather than of writing. Fixing them
#: here is cheaper than asking the model again, and catches the cases it
#: would only fix some of the time.
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:?])")
_MISSING_SPACE_AFTER = re.compile(r"([,;:])(?=[^\s\d])")
_REPEATED_WORD = re.compile(r"\b(\w+)(\s+\1)\b", re.I)
_DOUBLE_SPACE = re.compile(r"[ \t]{2,}")
_SENTENCE_START = re.compile(r"(^|[.?]\s+)([a-z])")
_A_BEFORE_VOWEL = re.compile(r"\b(a)\s+([aeiou]\w+)", re.I)
_AN_BEFORE_CONSONANT = re.compile(r"\ban\s+([bcdfgjklmnpqrstvwxyz]\w+)", re.I)
#: "a hour" - a consonant letter with a vowel sound behind it.
_A_BEFORE_SILENT_H = re.compile(
    r"\b(a)\s+(hour|hours|honest|honestly|honour|honourable|honor|heir)\b",
    re.I,
)

#: Words that start with a vowel letter but a consonant sound, and the other
#: way round. Getting these wrong is worse than leaving them alone.
_SOUNDS_LIKE_CONSONANT = ("one", "once", "uniform", "unique", "universal",
                          "unit", "united", "usual", "useful", "user", "use",
                          "european", "eucalyptus")
_SOUNDS_LIKE_VOWEL = ("hour", "honest", "honour", "honor", "heir")


def tidy_prose(text: str) -> str:
    """Fix the mechanical half of a sentence: spacing, caps, a/an.

    The model is asked to check its own grammar, and mostly does. These are
    the slips that survive that check - a doubled word, a space before a
    comma, a lower-case sentence opening - and every one of them is a thing
    a parent notices in a letter about their child.
    """
    if not text:
        return text

    text = _DOUBLE_SPACE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    text = _MISSING_SPACE_AFTER.sub(r"\1 ", text)
    text = _REPEATED_WORD.sub(r"\1", text)

    def fix_article(match: "re.Match[str]") -> str:
        article, word = match.group(1), match.group(2)
        if word.lower().startswith(_SOUNDS_LIKE_CONSONANT):
            return match.group(0)
        return _match_case(article, "an") + " " + word

    text = _A_BEFORE_VOWEL.sub(fix_article, text)
    text = _A_BEFORE_SILENT_H.sub(
        lambda m: _match_case(m.group(1), "an") + " " + m.group(2), text
    )

    def fix_an(match: "re.Match[str]") -> str:
        word = match.group(1)
        if word.lower().startswith(_SOUNDS_LIKE_VOWEL):
            return match.group(0)
        return ("An " if match.group(0)[0].isupper() else "a ") + word

    text = _AN_BEFORE_CONSONANT.sub(fix_an, text)
    text = _SENTENCE_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return text.strip()


def _tidy(value: Any) -> Any:
    """Walk the letter and tidy every piece of prose in it."""
    if isinstance(value, str):
        return tidy_prose(value)
    if isinstance(value, list):
        return [_tidy(v) for v in value]
    if isinstance(value, dict):
        return {k: v if k in _COPIED_VERBATIM else _tidy(v) for k, v in value.items()}
    return value


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
#: "quotes" is here for a different reason: it holds the child's own
#: spelling, and tidying "stand" into "Stand" edits what the child wrote.
_COPIED_VERBATIM = ("signals", "seen_in", "area_display_name", "badge", "quotes")


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
    letter = _conform_pronouns(letter, evidence)
    if not isinstance(letter, dict):
        return letter

    letter = _calm_exclamations(letter)
    letter = _tidy(letter)

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
        _strike_unsupported_level_note(letter, evidence)
        _strike_invented_quotes(letter, evidence)

    return letter


def _strike_unsupported_level_note(
    letter: Dict[str, Any], evidence: Dict[str, Any]
) -> None:
    """A note about the level only exists when the level did not fit.

    Whether it fitted is Stage A's arithmetic, not the writer's impression,
    so a note written over a well-matched set is simply removed rather than
    argued about.
    """
    if (evidence.get("level_fit") or {}).get("suggest"):
        return
    if letter.pop("level_note", None):
        logger.info("snapshot writer: dropping a level note the evidence did not ask for")


def _strike_invented_quotes(
    letter: Dict[str, Any], evidence: Dict[str, Any]
) -> None:
    """Keep only spelling quotes this child actually produced."""
    spelling = (evidence.get("what_the_child_did") or {}).get("spelling") or {}
    real = {
        (str(w.get("attempt", "")).strip().lower(),
         str(w.get("word", "")).strip().lower())
        for w in (spelling.get("words") or [])
        if w.get("attempt")
    }
    if not real:
        for item in letter.get("what_i_noticed") or []:
            item.pop("quotes", None)
        return

    for item in letter.get("what_i_noticed") or []:
        quotes = item.get("quotes")
        if not isinstance(quotes, list):
            item.pop("quotes", None)
            continue
        kept = [
            q for q in quotes
            if isinstance(q, dict)
            and (str(q.get("wrote", "")).strip().lower(),
                 str(q.get("for_word", "")).strip().lower()) in real
        ]
        if kept:
            item["quotes"] = kept
        else:
            item.pop("quotes", None)


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


def _conform_pronouns(letter: Any, evidence: Optional[Dict[str, Any]]) -> Any:
    """Make the letter speak about this child in this child's pronouns.

    When the profile records them, the writer was told them and the check is
    left to the validator: a "they" in the prose might belong to a pair of
    stories or a set of words rather than to the child, and a blind rewrite
    would turn "they are not easy words" into nonsense. When the profile
    records nothing, a gendered pronoun is a guess about a real child, and
    that is rewritten here rather than shipped.
    """
    pronouns = (evidence or {}).get("pronouns") or {}
    if pronouns.get("known"):
        return letter
    return _neutralise_letter(letter)


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

#: Concrete facts about this child a letter should carry before it is called
#: finished. Below this it reads like a letter about any child, so the writer
#: asks again rather than settling for the first draft that breaks no rule.
_ENOUGH_DETAIL = 6

_MAX_NOTICED = 4

#: Three growth edges is what a parent can act on. More than five is a list
#: nobody finishes, so related findings are grouped rather than dropped.
_ABSOLUTE_MAX_GROWING = 5


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

#: What the child IS, rather than what the child did. The second way to get
#: an opening wrong: it avoids counting by labelling, which fixes nothing.
_LABELLING = re.compile(
    r"\b(?:"
    r"ha[sd] (?:a|an) (?:knack|keen eye|gift|flair|natural ear|good ear|head|"
    r"talent|aptitude)\b"
    r"|\bis (?:a|an) (?:strong|natural|gifted|confident|able|talented|bright)\s+\w+"
    r"|ha[sd] (?:strong|excellent|good|advanced) \w+ (?:skills|ability|abilities)"
    r"|show(?:s|ed|n)? (?:a )?(?:strong|excellent|good|remarkable|impressive)\s+"
    r"(?:understanding|grasp|command|ability|aptitude)"
    r"|demonstrat(?:es|ed) (?:a )?(?:remarkable|strong|clear|impressive)"
    r"|\bis (?:very |quite )?(?:intelligent|clever|bright|gifted)\b"
    r")",
    re.I,
)

#: Some way of saying "and here is where they are still working". The
#: opening names one, plainly, before any praise.
_NAMES_A_GROWTH_EDGE = re.compile(
    r"\b(?:still|not yet|yet to|has not (?:met|found|come)|"
    r"have not (?:met|found|come)|where (?:he|she|they) (?:is|are) still|"
    r"working on|settling|has(?:n't| not) (?:started|arrived))\b",
    re.I,
)

#: The evidence buckets that belong to different activities, for the check
#: that an opening draws on more than one of them.
_ACTIVITY_BUCKETS = {
    "words_written": "spelling",
    "sentences_read": "speaking",
    "story_titles": "comprehension",
    "questions_worked_out": "comprehension",
    "questions_missed": "comprehension",
    "puzzles": "logic",
}


def specificity(letter: Dict[str, Any], evidence: Dict[str, Any]) -> int:
    """How many of this child's concrete facts the draft actually used.

    Not a guardrail - a ranking. Two drafts can both break no rule while one
    quotes the words the child wrote and the other talks about "developing
    skills". This is how the writer tells them apart instead of keeping
    whichever arrived first.
    """
    text = json.dumps(letter, ensure_ascii=False).lower()
    could = evidence.get("could_mention") or {}
    score = 0
    for key, facts in could.items():
        if isinstance(facts, str):
            facts = [facts] if facts else []
        for fact in facts:
            fact = str(fact).strip().lower()
            # Long sentences count if a distinctive chunk of them appears.
            probe = fact if len(fact) <= 40 else fact[:40]
            if len(probe) >= 4 and probe in text:
                score += 1
    return score


def missing_required_facts(
    letter: Dict[str, Any], evidence: Dict[str, Any]
) -> List[str]:
    """Facts the letter had to use and did not.

    This is what keeps quality from swinging between runs. Asking the model
    to be specific produces a specific letter most of the time; checking it
    produces one every time.
    """
    text = json.dumps(letter, ensure_ascii=False).lower()
    missing: List[str] = []
    for required in evidence.get("must_mention") or []:
        options = [str(o).strip().lower() for o in required.get("any_of") or []]
        options = [o for o in options if o]
        if not options:
            continue
        if not any(o in text for o in options):
            missing.append(
                f"the letter never names {required['what']} "
                f"({', '.join(required['any_of'][:4])}) - {required['why']}"
            )
    return missing


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
            best_rank: tuple = ()
            best_style: List[str] = []

            for attempt in range(_MAX_ATTEMPTS):
                letter = _repair(
                    self._generate(evidence, violations=seen or None), evidence
                )
                violations = self._validate(letter, evidence)
                harm = [v for v in violations if not v.startswith(_STYLE_PREFIX)]
                style = [v for v in violations if v.startswith(_STYLE_PREFIX)]
                detail = specificity(letter, evidence)

                # Rank every draft that breaks no rule: fewest voice slips
                # first, then the one that used most of this child's own
                # words. Keeping whichever arrived first is what made the
                # letter good some runs and vague others.
                rank = (-len(style), detail)
                if not harm and (best is None or rank > best_rank):
                    best, best_rank, best_style = letter, rank, style

                logger.info(
                    "snapshot writer: attempt %d - %d violation(s), "
                    "specificity %d", attempt + 1, len(violations), detail,
                )
                if not violations and detail >= _ENOUGH_DETAIL:
                    return self._finalise(letter, evidence, specificity=detail)

                if violations:
                    logger.warning(
                        "snapshot writer: attempt %d broke %s", attempt + 1, violations
                    )
                for violation in violations:
                    if violation not in seen:
                        seen.append(violation)
                if not violations:
                    # Clean but thin. Ask once more for the child's own words.
                    nudge = (
                        "the letter breaks no rule but is not specific enough: "
                        "quote more of what this child actually wrote, read, "
                        "and answered, from `could_mention`"
                    )
                    if nudge not in seen:
                        seen.append(nudge)

            # Nothing perfect. A letter that only slips on voice, or is a
            # little thin, still belongs to this child; the generic letter
            # belongs to no one.
            if best is not None:
                if best_style:
                    logger.warning(
                        "snapshot writer: shipping with voice slips %s", best_style
                    )
                return self._finalise(
                    best, evidence, style_slips=best_style,
                    specificity=best_rank[1] if best_rank else 0,
                )

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
        system = _SYSTEM_PROMPT + "\n\n" + _child_specific_rules(evidence)
        if violations:
            system += (
                "\n\nPREVIOUS ATTEMPT FAILED THESE RULES - do not repeat them:\n"
                + "\n".join(f"- {v}" for v in violations)
            )

        edges = [g["signal_name"] for g in evidence.get("growth_edges", [])]
        user_prompt = (
            "Below is the structured evidence for one child. "
            "Write the letter now using ONLY this data.\n\n"
            "Every one of these growth edges must be covered somewhere in "
            '"still_growing", named in that item\'s "signals": '
            f"{', '.join(edges) if edges else 'none'}.\n"
            "Group the ones that are really the same finding into a single "
            f"item. Aim for three items and never write more than "
            f"{_ABSOLUTE_MAX_GROWING}.\n\n"
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
            # The same child should get the same letter. 0.4 gave a good
            # letter on one run and a vague one on the next from identical
            # evidence, which is the whole problem with letting the model
            # choose how specific to be.
            temperature=0.15,
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

        # LS9: every growth edge the engine found must reach the parent -
        # but not necessarily in an item of its own. Four read-aloud sounds
        # are one thing for a parent to work on, so the check is that every
        # edge is COVERED, not that the item count matches. A letter with
        # seven near-identical sections is one a parent stops reading.
        expected = {g["signal_name"] for g in evidence.get("growth_edges", [])}
        covered = {
            name
            for item in growing
            for name in (item.get("signals") or [])
        }
        uncovered = expected - covered
        if uncovered:
            violations.append(
                "still_growing leaves out growth edges the engine found; "
                "cover each one in an item, grouping the ones that are the "
                f"same finding: {', '.join(sorted(uncovered))}"
            )
        if expected and len(growing) > _ABSOLUTE_MAX_GROWING:
            violations.append(
                f"{_STYLE_PREFIX}still_growing has {len(growing)} items, which "
                "is more than a parent will read; group the ones that are the "
                f"same finding into at most {_ABSOLUTE_MAX_GROWING}"
            )
        if not expected and growing:
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

        violations.extend(missing_required_facts(letter, evidence))
        violations.extend(style_violations(letter))

        # A quoted misspelling must never read as a correction.
        for pattern, label in _CORRECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                violations.append(
                    f"reads as a correction, not an explanation ({label}): "
                    f"{match.group(0)!r}"
                )

        violations.extend(self._check_pronouns(letter, evidence))
        violations.extend(self._check_opening(letter, evidence))

        return violations

    # ------------------------------------------------------------------
    @staticmethod
    def _check_opening(
        letter: Dict[str, Any], evidence: Dict[str, Any]
    ) -> List[str]:
        """The opening describes how this child works, and nothing else.

        It is the hardest paragraph in the letter and the one a parent reads
        first, so it is checked rather than hoped for. Naming an activity or
        labelling the child is mechanical and fatal - the writer can always
        fix it. Whether the opening reaches across two activities and names a
        growth edge is a judgement, so those are voice: worth asking again
        for, never worth withholding the letter over.
        """
        opening = letter.get("opening") or {}
        headline = str(opening.get("headline") or "")
        paragraph = str(opening.get("paragraph") or "")
        text = f"{headline} {paragraph}".strip()
        if not text:
            return ["the opening is empty"]

        violations: List[str] = []

        # The activity names are ours, not the parent's.
        for activity in evidence.get("activities_completed") or []:
            if activity and re.search(rf"\b{re.escape(activity)}\b", text, re.I):
                violations.append(
                    f"the opening names an activity ({activity!r}): say what "
                    "happened, not which module it happened in"
                )
                break

        match = _LABELLING.search(text)
        if match:
            violations.append(
                f"the opening says what the child IS, not what they did: "
                f"{match.group(0)!r}"
            )

        # A count anywhere is already fatal; in the opening it is the whole
        # complaint, so it is named here in the opening's own terms.
        for pattern, label in _FORBIDDEN_PATTERNS:
            found = pattern.search(text)
            if found and label in ("count of right or wrong", "percentage",
                                   "score ratio"):
                violations.append(
                    f"the opening counts what the child got right or wrong: "
                    f"{found.group(0)!r}"
                )
                break

        if not _NAMES_A_GROWTH_EDGE.search(text):
            violations.append(
                f"{_STYLE_PREFIX}the opening names nowhere this child is "
                "still working; say it plainly in one clause, before any "
                "praise, so the parent knows the letter is straight with them"
            )

        if len(_activities_behind(text, evidence)) < 2:
            violations.append(
                f"{_STYLE_PREFIX}the opening rests on one activity; a way of "
                "working that shows up in only one activity is an activity "
                "result in disguise, so prove it from a second one"
            )

        return violations

    # ------------------------------------------------------------------
    @staticmethod
    def _check_pronouns(
        letter: Dict[str, Any], evidence: Dict[str, Any]
    ) -> List[str]:
        """One voice for the child, and it is never a guess.

        Known pronouns are a matter of voice rather than of harm: a letter
        that slips into "they" once still belongs to this child, and the
        generic fallback belongs to no one. Unknown pronouns are different -
        a guess misgenders a real child, so that one is fatal and repaired
        before it ever reaches here.
        """
        text = json.dumps(letter, ensure_ascii=False)
        pronouns = evidence.get("pronouns") or {}
        child = evidence.get("child_name") or "the child"

        if not pronouns.get("known"):
            match = _GENDERED_PRONOUNS.search(text)
            if match:
                return [
                    f"gendered pronoun {match.group(0)!r}: no pronoun is known "
                    f"for this child, so use {child} or they/them throughout"
                ]
            return []

        match = _PLURAL_PRONOUNS.search(text)
        if not match:
            return []
        return [
            f"{_STYLE_PREFIX}plural pronoun {match.group(0)!r} in a letter "
            f"about one child: {child} takes {pronouns['subject']}/"
            f"{pronouns['object']}/{pronouns['possessive']}, and every verb "
            "has to agree with it"
        ]

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
        specificity: int = 0,
    ) -> Dict[str, Any]:
        name = evidence.get("child_name", "your child")
        pronouns = evidence.get("pronouns") or {}
        closing = letter.get("closing") or _GENERIC_LETTER["closing"]
        if "{name}" in closing:
            closing = closing.replace("{name}", name)
        letter["closing"] = closing

        # The frame of the letter. It is the same shape every time, so it is
        # written here rather than asked for: a model that has to produce
        # "Dear Parent," on every run will eventually produce something else.
        letter["salutation"] = "Dear Parent,"
        letter["signature"] = "Eko"
        letter["caveat"] = _caveat(evidence)

        # LS5 / LS3: these sections are gone. Strip them if a model produced
        # them anyway, so nothing invented reaches the parent.
        for key in _REMOVED_KEYS:
            letter.pop(key, None)

        letter["branding"] = "The Dear Parent Project"
        letter["disclaimer"] = (
            f"This is a starting point for a conversation about how {name} "
            "learns. It is not a diagnosis or a formal assessment, and it "
            f"compares {pronouns.get('object', 'them')} to no one."
        )
        letter["meta"] = {
            "llm_generated": llm_generated,
            "tests_completed": evidence.get("tests_completed", []),
            # Every promise the product makes to a parent held. Voice slips
            # are reported separately: they are a matter of how it reads.
            "guardrails_passed": llm_generated,
            "voice_slips": list(style_slips or []),
            # How many of this child's own words, sentences, stories and
            # puzzles the letter used. A low number is a thin letter.
            "specificity": specificity,
            # LS9: what the engine found, beside what the letter carried, so
            # a dropped growth edge is visible rather than silent.
            "growth_edges_found": len(evidence.get("growth_edges", [])),
            "growth_edges_written": len(letter.get("still_growing") or []),
            # Which pronouns the letter was written in, and whether they came
            # from the profile or were the they/them fallback.
            "pronouns": pronouns.get("key", "they"),
            "pronouns_known": bool(pronouns.get("known")),
        }
        return letter


def _activities_behind(text: str, evidence: Dict[str, Any]) -> set:
    """Which activities' evidence a passage actually draws on."""
    lowered = text.lower()
    found = set()
    could = evidence.get("could_mention") or {}
    for key, activity in _ACTIVITY_BUCKETS.items():
        facts = could.get(key) or []
        if isinstance(facts, str):
            facts = [facts]
        for fact in facts:
            fact = str(fact).strip().lower()
            probe = fact if len(fact) <= 40 else fact[:40]
            if len(probe) >= 4 and probe in lowered:
                found.add(activity)
                break
    return found


def _caveat(evidence: Dict[str, Any]) -> str:
    """The line that hands the letter back to the parent.

    A snapshot is one sitting. The parent has years of them, and the letter
    says so in the parent's own terms - the real length of the sitting, and
    the child's own name.
    """
    name = evidence.get("child_name") or "your child"
    span = (evidence.get("session") or {}).get("span_phrase") or "a short sitting"
    opener = span[0].upper() + span[1:]
    return (
        f"{opener} is a short time, and children have days. Take this as one "
        "afternoon's worth of noticing rather than the whole picture. If "
        f"something here does not sound like the {name} you know, trust "
        "yourself first."
    )


def get_snapshot_writer() -> SnapshotWriter:
    return SnapshotWriter()
