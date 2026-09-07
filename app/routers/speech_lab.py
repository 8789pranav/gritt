"""A diagnostic harness for the Voice Challenge signal chain.

One endpoint per stage, so each part of the chain can be exercised on its own
and its raw output inspected. This is a development tool, not a product
surface: it takes no auth, and stages 2 and 3 spend money per call.

It is therefore OFF unless SPEECH_LAB_ENABLED is set to a true value. Leave it
off in production. If you do enable it in a deployed environment, put it behind
an ingress rule first - an open endpoint that calls a paid API is an open
invoice.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/lab", tags=["speech-lab"])

_UI = Path(__file__).resolve().parents[2] / "static" / "speech_lab.html"


def _enabled() -> bool:
    return os.getenv("SPEECH_LAB_ENABLED", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=404,
            detail=(
                "The speech lab is disabled. Set SPEECH_LAB_ENABLED=true to "
                "turn it on, and only in a development environment."
            ),
        )


class AudioIn(BaseModel):
    audio_base64: str
    audio_format: str = "wav"
    reference_text: str = ""
    grade: str = "First"
    time_to_speak_ms: Optional[float] = None


class BatchIn(BaseModel):
    grade: str = "First"
    sentences: List[Dict[str, Any]]


@router.get("/", include_in_schema=False)
async def lab_ui():
    _require_enabled()
    if not _UI.exists():
        raise HTTPException(status_code=404, detail="speech_lab.html not found")
    return FileResponse(_UI)


@router.get("/config")
async def lab_config():
    """What is wired up, without revealing any secret."""
    _require_enabled()
    from app.infrastructure.azure_pronunciation import AzurePronunciationClient

    azure = AzurePronunciationClient()
    return {
        "azure": {
            "configured": azure.is_configured,
            "region": azure.region or None,
            "key_present": bool(azure.key),
            "endpoint": azure.endpoint if azure.region else None,
            "locale": azure.locale,
        },
        "openai": {"key_present": bool(os.getenv("OPENAI_API_KEY"))},
        "gate": _gate_settings(),
    }


def _gate_settings() -> Dict[str, Any]:
    from app.infrastructure import audio_gate

    return {
        "min_duration_seconds": audio_gate.MIN_DURATION_SECONDS,
        "min_rms": audio_gate.MIN_RMS,
        "min_voiced_fraction": audio_gate.MIN_VOICED_FRACTION,
    }


@router.post("/gate")
async def lab_gate(body: AudioIn):
    """Stage 1 only. Deterministic, free, no network."""
    _require_enabled()
    from app.infrastructure.audio_gate import inspect, message_for

    started = time.perf_counter()
    check = inspect(body.audio_base64, body.audio_format)
    return {
        "stage": "1-gate",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "has_speech": check.has_speech,
        "reason": check.reason,
        "message": None if check.has_speech else message_for(check.reason),
        "measured": {
            "duration_seconds": check.duration_seconds,
            "rms": check.rms,
            "voiced_fraction": check.voiced_fraction,
            "peak": check.peak,
        },
        "thresholds": _gate_settings(),
    }


@router.post("/azure")
async def lab_azure(body: AudioIn):
    """Stage 2 only. Raw Azure output, unmodified, plus our parse of it."""
    _require_enabled()
    if not body.reference_text.strip():
        raise HTTPException(status_code=400, detail="reference_text is required")

    from app.infrastructure.azure_pronunciation import (
        AzureNotConfigured,
        AzurePronunciationClient,
    )

    client = AzurePronunciationClient()
    started = time.perf_counter()
    try:
        result = await client.assess(body.audio_base64, body.reference_text)
    except AzureNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")

    return {
        "stage": "2-azure",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "recognized_text": result.recognized_text,
        "scores": {
            "accuracy": result.accuracy,
            "fluency": result.fluency,
            "completeness": result.completeness,
            "prosody": result.prosody,
            "pron_score": result.pron_score,
        },
        "words": [
            {
                "word": w.word,
                "accuracy": w.accuracy,
                "error_type": w.error_type,
                "offset_ms": w.offset_ms,
                "duration_ms": w.duration_ms,
                "phonemes": [
                    {"ipa": p.ipa, "accuracy": p.accuracy} for p in w.phonemes
                ],
            }
            for w in result.words
        ],
        "raw": result.raw,
    }


@router.post("/verbatim")
async def lab_verbatim(body: AudioIn):
    """Stage 3 only. Blind transcription - no reference text is sent."""
    _require_enabled()
    from app.engines.speaking.metrics import disfluency_metrics
    from app.infrastructure.hybrid_speech import HybridSpeechProvider

    started = time.perf_counter()
    text = HybridSpeechProvider()._transcribe_blind(
        base64.b64decode(body.audio_base64), body.audio_format
    )
    disfluency = disfluency_metrics(text, body.reference_text)
    return {
        "stage": "3-verbatim",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "verbatim_text": text,
        "note": "The reference sentence is never sent to this stage.",
        "disfluency": disfluency.as_dict(),
    }


@router.post("/sentence")
async def lab_sentence(body: AudioIn):
    """The whole chain for one sentence."""
    _require_enabled()
    if not body.reference_text.strip():
        raise HTTPException(status_code=400, detail="reference_text is required")

    from app.engines.speaking.pipeline import SentenceSubmission, SpeakingPipeline

    started = time.perf_counter()
    try:
        result = await SpeakingPipeline().analyse_sentence(
            SentenceSubmission(
                sentence_id="lab",
                reference_text=body.reference_text,
                audio_base64=body.audio_base64,
                audio_format=body.audio_format,
                time_to_speak_ms=body.time_to_speak_ms,
            ),
            body.grade,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")

    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


@router.post("/batch")
async def lab_batch(body: BatchIn):
    """Several sentences at once, to see the concurrency App Runner needs."""
    _require_enabled()
    from app.engines.speaking.pipeline import (
        SentenceSubmission,
        SpeakingPipeline,
        aggregate,
    )

    submissions = [
        SentenceSubmission(
            sentence_id=item.get("sentence_id", f"s{index}"),
            reference_text=item.get("reference_text", ""),
            audio_base64=item.get("audio_base64", ""),
            audio_format=item.get("audio_format", "wav"),
            time_to_speak_ms=item.get("time_to_speak_ms"),
        )
        for index, item in enumerate(body.sentences)
    ]

    started = time.perf_counter()
    results = await SpeakingPipeline().analyse(submissions, body.grade)
    elapsed = round((time.perf_counter() - started) * 1000, 1)

    return {
        "stage": "full-batch",
        "elapsed_ms": elapsed,
        "sentences": len(results),
        "ms_per_sentence_if_serial": (
            round(sum(r.get("elapsed_ms", 0) for r in results), 1) or None
        ),
        "app_runner_limit_ms": 120_000,
        "within_app_runner_limit": elapsed < 120_000,
        "signals": aggregate(results, body.grade),
        "results": results,
    }


@router.get("/sentences/{grade}")
async def lab_sentences(grade: str):
    """The real sentence bank, so the lab tests what children actually read."""
    _require_enabled()
    from app.domain.enums import Grade
    from app.engines.registry import speaking_engine

    try:
        grade_enum = Grade(grade)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown grade {grade!r}")

    return {
        "grade": grade,
        "sentences": [
            {
                "sentence_id": s.sentence_id,
                "sentence": s.sentence,
                "word_count": len(s.sentence.split()),
            }
            for s in speaking_engine().get_items(grade_enum)
        ],
    }
