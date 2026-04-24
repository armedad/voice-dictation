"""Local dictation: record from mic, transcribe + cleanup, inject at OS focus (macOS)."""
from __future__ import annotations

import asyncio
import sys
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.routers.models import get_user_store
from app.services.dictation_cleanup import (
    build_cleanup_endpoint,
    resolve_transcription_endpoint,
)

router = APIRouter(tags=["dictation"])

RECORD_SECONDS = 10.0


@router.post("/dictation/record-and-type")
async def record_and_type(request: Request) -> dict[str, Any]:
    """
    Requires login cookie. Records fixed duration from default mic, runs voice pipeline,
    then types the result at the current keyboard focus (any app). macOS only.

    LLM rewrite (optional): Settings → Dictation. Uses Default model from Models tab when
    enabled. STT model from Settings → Speech recognition (or ~/.voice-dictation when unset).
    """
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")

    if sys.platform != "darwin":
        raise HTTPException(
            status_code=501,
            detail="Dictation + synthetic typing is only wired for macOS in this build.",
        )

    from core.config import load_config
    from core.models import (
        build_dictation_cleanup_system_prompt,
        format_vocabulary_for_whisper_initial_prompt,
    )
    from core.orchestrator import run_pipeline
    from platform_mac.audio import record_wav_bytes
    from platform_mac.typing_inject import TypingInjectionError, type_text_strict

    store = get_user_store(request)
    settings = store.get_settings()
    llm_cleanup = settings.dictation_llm_cleanup_enabled

    clean_ep = None
    openai_key = None
    if llm_cleanup:
        try:
            clean_ep, openai_key = build_cleanup_endpoint(settings, store.data_dir)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    cfg = load_config()
    trans_ep = resolve_transcription_endpoint(settings.speech_model, cfg)

    cleanup_system_prompt = None
    if llm_cleanup:
        cleanup_system_prompt = build_dictation_cleanup_system_prompt(
            settings.dictation_instructions,
            vocabulary=settings.dictation_vocabulary,
        )

    stt_vocab_hint = format_vocabulary_for_whisper_initial_prompt(
        settings.dictation_vocabulary
    )

    try:
        wav = await asyncio.to_thread(record_wav_bytes, RECORD_SECONDS)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Microphone capture failed: {e!s}. Check mic permission and PortAudio.",
        ) from e

    try:
        text = await run_pipeline(
            wav,
            "dictation.wav",
            transcription_endpoint=trans_ep,
            cleanup_endpoint=clean_ep,
            cleanup_openai_api_key=openai_key,
            cleanup_system_prompt=cleanup_system_prompt,
            skip_llm_cleanup=not llm_cleanup,
            transcription_initial_prompt=stt_vocab_hint,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Transcription or cleanup failed: {e!s}",
        ) from e

    try:
        await asyncio.to_thread(type_text_strict, text)
    except TypingInjectionError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Synthetic typing failed: {e!s}",
        ) from e

    return {"ok": True, "text": text}
