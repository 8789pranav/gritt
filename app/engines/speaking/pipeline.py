"""The Voice Challenge signal chain.

Six stages per sentence, in order, each one able to stop the chain:

  0  capture        client: record, validate, time the press-to-speak gap
  1  waveform gate  deterministic; silence never reaches a paid call
  2  Azure          scripted pronunciation assessment - the scoring spine
  3  verbatim       blind transcription for fillers, and as a cross-check
  4  derive         WCPM, pauses, phonics - counted, not estimated
  5  tag            existing declarative tag engine

Sentences run concurrently. AWS App Runner enforces a fixed 120-second request
timeout that cannot be configured, and eight sentences analysed one after
another do not fit inside it. Run concurrently, wall time is roughly one
sentence rather than eight.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.engines.speaking.metrics import (
    build_sentence_metrics,
    empty_sentence_metrics,
)
from app.infrastructure.audio_gate import inspect, message_for
from app.infrastructure.azure_pronunciation import (
    AzureNotConfigured,
    AzurePronunciationClient,
)

logger = logging.getLogger(__name__)

#: How many sentences to have in flight at once. Azure's short-audio endpoint
#: is per-request, so this is bounded by politeness and by App Runner's memory,
#: not by the service.
MAX_CONCURRENCY = 8

#: Below this word-overlap, the verbatim channel and Azure disagree about what
#: was said, and neither number is trustworthy.
AGREEMENT_THRESHOLD = 0.5


@dataclass
class SentenceSubmission:
    sentence_id: str
    reference_text: str
    audio_base64: str
    audio_format: str = "wav"
    time_to_speak_ms: Optional[float] = None
    attempt: int = 1


def _agreement(left: str, right: str) -> float:
    """Word-level similarity between the two transcription channels."""
    from difflib import SequenceMatcher

    left_words = (left or "").lower().split()
    right_words = (right or "").lower().split()
    if not left_words or not right_words:
        return 0.0
    return round(SequenceMatcher(None, left_words, right_words).ratio(), 3)


class SpeakingPipeline:
    """Runs the chain for a whole submission."""

    def __init__(
        self,
        azure: Optional[AzurePronunciationClient] = None,
        transcriber: Optional[Any] = None,
    ) -> None:
        self.azure = azure or AzurePronunciationClient()
        # The verbatim channel. Injected so the pipeline can be tested, and so
        # the transcriber can be swapped without touching the chain.
        self._transcriber = transcriber

    # -- stage 3 ------------------------------------------------------------
    async def _verbatim(self, audio_base64: str, audio_format: str) -> str:
        """Blind transcription. No reference text, no prompt hint, ever."""
        if self._transcriber is None:
            from app.infrastructure.hybrid_speech import HybridSpeechProvider

            self._transcriber = HybridSpeechProvider()
        try:
            import base64

            return await asyncio.to_thread(
                self._transcriber._transcribe_blind,
                base64.b64decode(audio_base64),
                audio_format,
            )
        except Exception as exc:  # pragma: no cover - network failure path
            logger.warning("Verbatim channel failed: %s", exc)
            return ""

    # -- one sentence -------------------------------------------------------
    async def analyse_sentence(
        self,
        submission: SentenceSubmission,
        grade: str,
    ) -> Dict[str, Any]:
        reference = submission.reference_text

        # Stage 1 - the gate. Deterministic, free, and unbypassable.
        check = inspect(submission.audio_base64, submission.audio_format)
        if not check.has_speech:
            logger.info(
                "%s rejected by gate: %s (rms=%s voiced=%s)",
                submission.sentence_id, check.reason, check.rms, check.voiced_fraction,
            )
            payload = empty_sentence_metrics(
                reference, check.reason, message_for(check.reason)
            )
            payload["sentence_id"] = submission.sentence_id
            payload["audio_check"] = {
                "reason": check.reason,
                "duration_seconds": check.duration_seconds,
                "rms": check.rms,
                "voiced_fraction": check.voiced_fraction,
            }
            return payload

        # Stages 2 and 3 run against the same audio, so run them together.
        azure_task = asyncio.create_task(
            self.azure.assess(submission.audio_base64, reference)
        )
        verbatim_task = asyncio.create_task(
            self._verbatim(submission.audio_base64, submission.audio_format)
        )
        results = await asyncio.gather(
            azure_task, verbatim_task, return_exceptions=True
        )
        azure_result, verbatim_text = results

        if isinstance(azure_result, AzureNotConfigured):
            raise azure_result
        if isinstance(azure_result, Exception):
            logger.warning(
                "%s: Azure assessment failed: %s", submission.sentence_id, azure_result
            )
            payload = empty_sentence_metrics(
                reference, "assessment_failed",
                "The recording could not be assessed. Please try again.",
            )
            payload["sentence_id"] = submission.sentence_id
            payload["status"] = "needs_review"
            return payload

        if isinstance(verbatim_text, Exception):
            verbatim_text = ""

        # Stage 4 - derive.
        payload = build_sentence_metrics(
            azure_result,
            reference_text=reference,
            grade=grade,
            verbatim_text=verbatim_text,
            time_to_speak_ms=submission.time_to_speak_ms,
        )
        payload["sentence_id"] = submission.sentence_id
        payload["attempt"] = submission.attempt

        # The cross-check. Two channels heard the same audio; if they describe
        # different utterances, we publish no score for this sentence.
        agreement = _agreement(verbatim_text, azure_result.recognized_text)
        payload["channel_agreement"] = agreement
        if verbatim_text and agreement < AGREEMENT_THRESHOLD:
            logger.warning(
                "%s: channels disagree (%.2f) verbatim=%r azure=%r",
                submission.sentence_id, agreement,
                verbatim_text[:60], azure_result.recognized_text[:60],
            )
            payload["status"] = "needs_review"
            payload["message"] = (
                "The two transcriptions of this recording disagree, so it has "
                "not been scored."
            )
            # Withhold the numbers, do not merely label them. Azure aligns its
            # recognition to the reference sentence, so a child who read
            # something else entirely can come back with a plausible-looking
            # score and a transcript containing the reference words. Measured:
            # a reading of "Elephants migrate across the savannah" scored 32.5
            # and transcribed as "The cat the sat cat the on."
            payload["withheld"] = {
                "reason": "channel_disagreement",
                "scores": dict(payload["scores"]),
                "azure_recognized": azure_result.recognized_text,
            }
            payload["scores"] = {
                "accuracy": 0.0, "fluency": 0.0, "completeness": 0.0,
                "prosody": 0.0, "pron_score": 0.0,
            }
            payload["recognized"] = ""
            payload["reading"] = empty_sentence_metrics(
                reference, "channel_disagreement", payload["message"]
            )["reading"]
            payload["phonics"] = {k: None for k in payload.get("phonics", {})}
        else:
            payload["status"] = "answered"

        return payload

    # -- whole submission ---------------------------------------------------
    async def analyse(
        self,
        submissions: Sequence[SentenceSubmission],
        grade: str,
    ) -> List[Dict[str, Any]]:
        """Analyse every sentence concurrently, in submission order."""
        limit = asyncio.Semaphore(MAX_CONCURRENCY)

        async def run(submission: SentenceSubmission) -> Dict[str, Any]:
            async with limit:
                return await self.analyse_sentence(submission, grade)

        return list(await asyncio.gather(*(run(s) for s in submissions)))


# ---------------------------------------------------------------------------
# test-level aggregation
# ---------------------------------------------------------------------------
def aggregate(results: Sequence[Dict[str, Any]], grade: str) -> Dict[str, Any]:
    """Roll per-sentence measurements up into the signals the tags read.

    Only sentences with status "answered" contribute to the averages. A
    sentence that was never attempted, or whose channels disagreed, is
    reported and counted but does not move the mean - the same decision Word
    Wizard makes, for the same reason.
    """
    answered = [r for r in results if r.get("status") == "answered"]
    attempted = len(answered)
    total = len(results)

    def mean(path: Sequence[str], source: Sequence[Dict[str, Any]] = None) -> float:
        rows = source if source is not None else answered
        values = []
        for row in rows:
            node: Any = row
            for key in path:
                node = (node or {}).get(key) if isinstance(node, dict) else None
            if isinstance(node, (int, float)):
                values.append(float(node))
        return round(sum(values) / len(values), 1) if values else 0.0

    def total_of(path: Sequence[str]) -> int:
        count = 0
        for row in answered:
            node: Any = row
            for key in path:
                node = (node or {}).get(key) if isinstance(node, dict) else None
            if isinstance(node, (int, float)):
                count += int(node)
        return count

    from app.engines.speaking.metrics import PHONICS_FEATURES

    phonics: Dict[str, Optional[float]] = {}
    for feature in PHONICS_FEATURES:
        values = [
            r["phonics"][feature] for r in answered
            if isinstance(r.get("phonics", {}).get(feature), (int, float))
        ]
        phonics[feature] = round(sum(values) / len(values), 1) if values else None

    words_read = total_of(("reading", "total_words"))
    fillers = total_of(("disfluency", "filler_count"))

    # WCPM is a whole-test measure, not a per-sentence one. Published grade
    # norms assume roughly a minute of connected reading; a nine-word sentence
    # read in 2.4 seconds computes to 224 wcpm, which is arithmetically true
    # and educationally meaningless. Summing correct words over total speaking
    # time across the sitting gives a figure that can be read against a norm.
    correct_words = total_of(("reading", "correct_words"))
    speaking_ms = sum(
        float(r.get("timing", {}).get("speaking_span_ms") or 0.0) for r in answered
    )
    speaking_minutes = speaking_ms / 60_000.0
    test_wcpm = round(correct_words / speaking_minutes, 1) if speaking_minutes else 0.0

    from app.engines.speaking.metrics import DEFAULT_WCPM_BAND, GRADE_WCPM_BANDS

    low, high = GRADE_WCPM_BANDS.get(grade, DEFAULT_WCPM_BAND)
    if test_wcpm <= 0:
        rate_band = "no_reading"
    elif test_wcpm < low:
        rate_band = "below_band"
    elif test_wcpm > high:
        rate_band = "above_band"
    else:
        rate_band = "in_band"

    return {
        "sentences_total": total,
        "sentences_answered": attempted,
        "sentences_needs_review": sum(
            1 for r in results if r.get("status") == "needs_review"
        ),
        "attempted_ratio": round(attempted / total, 3) if total else 0.0,

        "avg_accuracy": mean(("scores", "accuracy")),
        "avg_fluency": mean(("scores", "fluency")),
        "avg_completeness": mean(("scores", "completeness")),
        "avg_prosody": mean(("scores", "prosody")),
        "avg_pron_score": mean(("scores", "pron_score")),

        # The figure to report. avg_wcpm is kept for continuity but is the
        # mean of per-sentence rates, which is not comparable to a grade norm.
        "wcpm": test_wcpm,
        "wcpm_band": rate_band,
        "correct_words": correct_words,
        "speaking_seconds": round(speaking_ms / 1000.0, 2),
        "avg_wcpm": mean(("reading", "wcpm")),
        "avg_accuracy_pct": mean(("reading", "accuracy_pct")),
        "words_read": words_read,

        "avg_time_to_speak_ms": mean(("timing", "time_to_speak_ms")),
        "avg_time_to_first_word_ms": mean(("timing", "time_to_first_word_ms")),
        "total_pause_count": total_of(("timing", "pause_count")),
        "total_long_pause_count": total_of(("timing", "long_pause_count")),

        "filler_count": fillers,
        "filler_rate_per_100w": (
            round(fillers / words_read * 100, 1) if words_read else 0.0
        ),
        "repetition_count": total_of(("disfluency", "repetitions")),

        "omission_count": total_of(("errors", "omission")),
        "insertion_count": total_of(("errors", "insertion")),
        "mispronunciation_count": total_of(("errors", "mispronunciation")),
        "monotone_count": total_of(("errors", "monotone")),
        # Our own banding. Azure flags Mispronunciation below 60 only, which
        # misses words a teacher would mark.
        "clear_error_count": total_of(("errors", "clear_error")),
        "needs_attention_count": total_of(("errors", "needs_attention")),
        "prolonged_count": total_of(("errors", "prolonged")),
        "words_flagged": total_of(("errors", "words_flagged")),
        "unexpected_break_count": total_of(("errors", "unexpected_break")),

        "phonics": phonics,
        **{f"phonics_{name}": value for name, value in phonics.items()},
    }
