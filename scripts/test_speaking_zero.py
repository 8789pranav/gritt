"""Local test: verify speaking score is 0 when no speech / garbage audio."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.engines.speaking.scorer import SpeakingScorer, MAX_SENTENCE_SCORE
from app.engines.speaking.analyzer import SpeechAnalysis, DimensionScore
from app.engines.speaking.loader import SpeakingSentenceLoader
from app.domain.enums import Grade, Difficulty
from app.domain.models import SpeakingSentence, SpeakingResponse

grade = Grade.KINDERGARTEN
loader = SpeakingSentenceLoader()
sentences = loader.shuffled(grade, seed=42)[:3]

print("=" * 60)
print("  Speaking Zero-Score Guard Test")
print("=" * 60)

# --- Case 1: No transcription (empty audio / silence) ---
print("\nCase 1: Empty transcription (silence / no speech)")
analysis1 = SpeechAnalysis(
    pronunciation=DimensionScore(score=50),
    fluency=DimensionScore(score=60),
    prosody=DimensionScore(score=50),
    grammar=DimensionScore(score=100),
    speaking_rate=DimensionScore(score=80),
    overall_score=50.0,
    level="Developing",
    recommendation="",
)
responses1 = [
    SpeakingResponse(
        item_id=s.sentence_id,
        sentence_id=s.sentence_id,
        original_sentence=s.sentence,
        transcribed_text="",
        audio_base64=None,
    )
    for s in sentences
]
analyses1 = {s.sentence_id: analysis1 for s in sentences}

scorer = SpeakingScorer()
scorer.with_analyses(analyses1)
score1 = scorer.score(sentences, responses1, grade)

all_zero_1 = all(si.points == 0.0 for si in score1.scored_items)
print(f"  All points=0: {all_zero_1}")
print(f"  Total points: {score1.points}")
print(f"  Percentage: {score1.percentage}%")
for si in score1.scored_items:
    print(f"    {si.label[:30]}: points={si.points}, is_correct={si.is_correct}")

# --- Case 2: Garbage transcription (no word overlap) ---
print("\nCase 2: Garbage transcription (background noise)")
analysis2 = SpeechAnalysis(
    pronunciation=DimensionScore(score=40),
    fluency=DimensionScore(score=50),
    prosody=DimensionScore(score=30),
    grammar=DimensionScore(score=50),
    speaking_rate=DimensionScore(score=60),
    overall_score=40.0,
    level="Needs Improvement",
    recommendation="",
)
responses2 = [
    SpeakingResponse(
        item_id=s.sentence_id,
        sentence_id=s.sentence_id,
        original_sentence=s.sentence,
        transcribed_text="blah blah xyz random noise",
        audio_base64=None,
    )
    for s in sentences
]
analyses2 = {s.sentence_id: analysis2 for s in sentences}

scorer2 = SpeakingScorer()
scorer2.with_analyses(analyses2)
score2 = scorer2.score(sentences, responses2, grade)

all_zero_2 = all(si.points == 0.0 for si in score2.scored_items)
print(f"  All points=0: {all_zero_2}")
print(f"  Total points: {score2.points}")
print(f"  Percentage: {score2.percentage}%")
for si in score2.scored_items:
    print(f"    {si.label[:30]}: points={si.points}, is_correct={si.is_correct}")

# --- Case 3: Correct speech (should get non-zero) ---
print("\nCase 3: Correct transcription (should score > 0)")
analysis3 = SpeechAnalysis(
    pronunciation=DimensionScore(score=90),
    fluency=DimensionScore(score=85),
    prosody=DimensionScore(score=80),
    grammar=DimensionScore(score=95),
    speaking_rate=DimensionScore(score=90),
    overall_score=88.0,
    level="Good Speaker",
    recommendation="",
)
responses3 = [
    SpeakingResponse(
        item_id=s.sentence_id,
        sentence_id=s.sentence_id,
        original_sentence=s.sentence,
        transcribed_text=s.sentence,
        audio_base64=None,
    )
    for s in sentences
]
analyses3 = {s.sentence_id: analysis3 for s in sentences}

scorer3 = SpeakingScorer()
scorer3.with_analyses(analyses3)
score3 = scorer3.score(sentences, responses3, grade)

has_score = any(si.points > 0 for si in score3.scored_items)
print(f"  Has non-zero scores: {has_score}")
print(f"  Total points: {score3.points}")
print(f"  Percentage: {score3.percentage}%")
for si in score3.scored_items:
    print(f"    {si.label[:30]}: points={si.points}, is_correct={si.is_correct}")

# --- Summary ---
print("\n" + "=" * 60)
passed = 0
failed = 0

if all_zero_1 and score1.points == 0.0:
    print("  PASS: Empty transcription → 0 score")
    passed += 1
else:
    print("  FAIL: Empty transcription should be 0")
    failed += 1

if all_zero_2 and score2.points == 0.0:
    print("  PASS: Garbage transcription → 0 score")
    passed += 1
else:
    print("  FAIL: Garbage transcription should be 0")
    failed += 1

if has_score and score3.points > 0:
    print("  PASS: Correct speech → non-zero score")
    passed += 1
else:
    print("  FAIL: Correct speech should score > 0")
    failed += 1

print(f"\n  TOTAL: {passed} passed, {failed} failed")
if failed == 0:
    print("  ALL TESTS PASSED!")
