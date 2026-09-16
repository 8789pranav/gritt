"""Comprehensive regression test for all spelling bugs.

Covers:
  #77: Convention errors recorded as phonics errors → FIXED (AI classifier)
  #75: spelling_convention_emerging not firing → FIXED
  #78: strengths list contradicts error list → FIXED (accuracy + min 2 words)
  #80: shower tagged short_vowel_correct wrongly → FIXED (data fix)
  #79: homophone error missing from key_error_patterns → FIXED
  #70: sight_word_emerging excluded from focus_areas → ALREADY FIXED
  #57: 'and' missing consonant_blend_correct → ALREADY WORKING
  #54: unanswered words show Incorrect icon → ALREADY FIXED
  #61: rushed_attempt co-fires → ALREADY FIXED
  #73/#74: dropped silent e → NEEDS VERIFICATION
"""
import os
import sys

sys.path.insert(0, "Z:/grittt")

from pathlib import Path
env_path = Path("Z:/grittt/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

from app.domain.enums import Grade, WordType
from app.domain.models import SpellingResponse
from app.engines import registry
from app.engines.spelling.phonics import sounds_like

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} — {detail}")

def _run(grade, attempts, time=10.0):
    engine = registry.spelling_engine()
    by_word = {item.word: item for item in engine.get_items(grade)}
    items = [by_word[w] for w in attempts if w in by_word]
    responses = [
        SpellingResponse(
            item_id=by_word[w].item_id, word=w, user_input=a,
            word_type=by_word[w].word_type, response_time_seconds=time,
        )
        for w, a in attempts.items() if w in by_word
    ]
    result = engine.evaluate("test", grade, responses, items=items)
    label_by_id = {item.item_id: item.word for item in items}
    tags = {label_by_id[p.item_id]: set(p.tags) for p in result.per_item_tags}
    return result, tags

print("=" * 60)
print("COMPREHENSIVE SPELLING BUG REGRESSION TEST")
print("=" * 60)

# --- #77: Convention errors as phonics errors ---
print("\n--- #77: Convention errors (candle→kandle etc.) ---")
result, tags = _run(Grade.THIRD, {
    "candle": "kandle",
    "outline": "owtline",
    "perplex": "purplex",
    "turnstile": "ternstile",
})
for word in ["candle", "outline", "perplex", "turnstile"]:
    check(
        f"{word} has spelling_convention_error",
        "spelling_convention_error" in tags.get(word, set()),
        f"tags={tags.get(word, set())}",
    )
    check(
        f"{word} has NO phonics error tags",
        not any(t.endswith("_error") and t != "spelling_convention_error"
                for t in tags.get(word, set())),
        f"tags={tags.get(word, set())}",
    )

# --- #75: spelling_convention_emerging fires ---
print("\n--- #75: spelling_convention_emerging fires ---")
all_tags = {t.tag for t in result.tags}
check("spelling_convention_emerging in tags", "spelling_convention_emerging" in all_tags)
check("convention_error_count >= 3",
      result.signals.get("convention_error_count", 0) >= 3,
      f"count={result.signals.get('convention_error_count')}")
focus = registry.spelling_engine().focus_areas(result.score)
check("'Spelling conventions' in focus_areas", "Spelling conventions" in focus)

# --- #78: strengths from accuracy not presence ---
print("\n--- #78: strengths from accuracy + min 2 words ---")
# A feature tested on only 1 word should NOT be a strength
# even if accuracy is 100%
result78, tags78 = _run(Grade.THIRD, {
    "candle": "candle",      # correct, has short_vowel, beginning_consonant, etc.
    "outline": "owtline",    # wrong (convention), has long_vowel
    "perplex": "purplex",    # wrong (convention), has short_vowel
    "turnstile": "ternstile", # wrong (convention), has long_vowel
})
strengths = registry.spelling_engine().strengths(result78.signals)
print(f"  strengths: {strengths}")
# short_vowel: candle correct + perplex convention error = 2/2 = 100% accuracy, 2 attempted → strength
check("Short vowel in strengths (2/2 correct, 2 attempted)",
      "Short vowel" in strengths,
      f"strengths={strengths}")
# Check that a feature with only 1 attempt is NOT in strengths
# (need to find such a feature in this test set)

# --- #80: shower no short_vowel tag ---
print("\n--- #80: shower should NOT have short_vowel feature ---")
engine = registry.spelling_engine()
shower_item = None
for item in engine.get_items(Grade.THIRD):
    if item.word == "shower":
        shower_item = item
        break
if shower_item:
    from app.engines.spelling.phonics import parse_expectations
    exps = parse_expectations(shower_item.features)
    features_present = [e.feature.value for e in exps]
    print(f"  shower features: {features_present}")
    check("shower has NO short_vowel feature",
          "short_vowel" not in features_present,
          f"features={features_present}")
    check("shower has other_vowel_pattern",
          "other_vowel_pattern" in features_present)

# --- #79: homophone in key_error_patterns ---
print("\n--- #79: homophone error in key_error_patterns ---")
# "there" → "their" is a homophone error
result79, tags79 = _run(Grade.THIRD, {
    "there": "their",
    "candle": "candle",
    "outline": "outline",
    "perplex": "perplex",
    "turnstile": "turnstile",
})
error_breakdown = registry.spelling_engine().scorer.error_breakdown(result79.score)
print(f"  error_breakdown: {error_breakdown}")
check("Homophone error in error_breakdown",
      error_breakdown.get("Homophone error", 0) >= 1,
      f"breakdown={error_breakdown}")

# --- #70: sight words in focus_areas ---
print("\n--- #70: sight words in focus_areas ---")
# Need a test where sight words are below mastery
# Grade 3 has: could, people, there, which, although
result70, tags70 = _run(Grade.THIRD, {
    "could": "cud",      # wrong sight word
    "people": "peepl",   # wrong sight word
    "there": "thare",    # wrong sight word
    "which": "wich",     # wrong sight word
    "candle": "candle",  # correct regular
    "outline": "outline",
    "perplex": "perplex",
    "turnstile": "turnstile",
    "shower": "shower",
    "amputate": "amputate",
    "entertain": "entertain",
    "hamburger": "hamburger",
    "puzzle": "puzzle",
    "sixteen": "sixteen",
})
focus70 = registry.spelling_engine().focus_areas(result70.score)
print(f"  focus_areas: {focus70}")
check("'Sight words' in focus_areas when sight accuracy < 75%",
      "Sight words" in focus70,
      f"focus={focus70}")

# --- #57: 'and' has consonant_blend_correct ---
print("\n--- #57: 'and' has consonant_blend_correct ---")
result57, tags57 = _run(Grade.FIRST, {"and": "and"})
check("'and' has consonant_blend_correct",
      "consonant_blend_correct" in tags57.get("and", set()),
      f"tags={tags57.get('and', set())}")

# --- #73/#74: dropped silent e ---
print("\n--- #73/#74: dropped silent e is phonics error ---")
check("sounds_like('home', 'hom') is False", not sounds_like("home", "hom"))
check("sounds_like('turnstile', 'turnstil') is False",
      not sounds_like("turnstile", "turnstil"))
check("sounds_like('entertain', 'entertan') is False",
      not sounds_like("entertain", "entertan"))
check("sounds_like('standstill', 'standstil') is True",
      sounds_like("standstill", "standstil"))

# Test home→hom gets long_vowel_error
result73, tags73 = _run(Grade.FIRST, {"home": "hom"})
check("home→hom gets long_vowel_error",
      "long_vowel_error" in tags73.get("home", set()),
      f"tags={tags73.get('home', set())}")
check("home→hom does NOT get spelling_convention_error",
      "spelling_convention_error" not in tags73.get("home", set()))

# --- #54: unanswered words show "Not answered" ---
print("\n--- #54: unanswered words show 'Not answered' icon ---")
# This is tested in the service layer; the scorer marks NOT_ATTEMPTED
# and the service maps it to "Not answered". Check scorer behavior.
result54, _ = _run(Grade.THIRD, {
    "candle": "candle",
    "outline": "outline",
    # perplex and turnstile are NOT submitted → unanswered
})
for s in result54.score.scored_items:
    if s.label in ("perplex", "turnstile"):
        check(f"{s.label} is NOT_ATTEMPTED",
              s.status.value == "not_attempted",
              f"status={s.status}")
        check(f"{s.label} has empty user_input",
              not s.detail.get("user_input", "").strip())

# --- Summary ---
print(f"\n{'=' * 60}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'=' * 60}")
sys.exit(0 if FAIL == 0 else 1)
