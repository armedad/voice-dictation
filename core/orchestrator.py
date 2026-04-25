from __future__ import annotations

from typing import Any, Optional

from .adapters.cleanup_ollama import cleanup_ollama_chat
from .adapters.cleanup_openai import cleanup_openai_chat
from .adapters.transcription_faster_whisper import transcribe_faster_whisper
from .adapters.transcription_openai import transcribe_openai_whisper
from .config import api_key_for_cleanup, api_key_for_transcription, load_config
from .models import AdapterEndpoint, VoiceDictationConfig


async def run_pipeline(
    wav_bytes: bytes,
    wav_filename: str = "dictation.wav",
    *,
    transcription_endpoint: Optional[AdapterEndpoint] = None,
    cleanup_endpoint: Optional[AdapterEndpoint] = None,
    cleanup_openai_api_key: Optional[str] = None,
    cleanup_system_prompt: Optional[str] = None,
    skip_llm_cleanup: bool = False,
    transcription_initial_prompt: Optional[str] = None,
    capture_audit: Optional[dict[str, Any]] = None,
) -> str:
    """
    Transcribe WAV bytes, then optionally run LLM cleanup.

    ``transcription_endpoint`` overrides STT for this run (e.g. from Settings speech model).

    When ``cleanup_endpoint`` is set (from ai-frame Settings), it drives cleanup URL/model.
    ``cleanup_openai_api_key``: ``None`` lets OpenAI-compatible cleanup use env keys when
    using file-based cleanup; ``\"\"`` for no Authorization header (e.g. LM Studio); else
    the API key string.

    ``cleanup_system_prompt``: full system message for the cleanup LLM (when not skipping).

    ``skip_llm_cleanup``: if True, return the raw transcript after STT only.

    ``transcription_initial_prompt``: optional faster-whisper ``initial_prompt`` (soft bias);
    ignored for OpenAI-compatible audio STT.

    ``capture_audit``: if provided, set ``raw_transcript`` after STT (even when skipping LLM).

    When ``cleanup_endpoint`` is omitted, ``~/.voice-dictation/config.json`` cleanup is used.
    """
    cfg: VoiceDictationConfig = load_config()
    trans = transcription_endpoint if transcription_endpoint is not None else cfg.transcription

    tp = (trans.provider or "").strip().lower()

    if tp in ("openai_compatible_audio", "openai", "openai_whisper"):
        t_key = api_key_for_transcription()
        raw = await transcribe_openai_whisper(wav_bytes, wav_filename, trans, t_key)
    elif tp in ("faster_whisper", "local_faster_whisper", "faster-whisper"):
        raw = await transcribe_faster_whisper(
            wav_bytes,
            trans,
            initial_prompt=transcription_initial_prompt,
        )
    else:
        raise ValueError(
            f"Unknown transcription.provider: {trans.provider!r}. "
            "Use faster_whisper (local) or openai_compatible_audio."
        )

    if capture_audit is not None:
        capture_audit["raw_transcript"] = raw

    if not (raw or "").strip():
        return ""

    if skip_llm_cleanup:
        return raw

    clean = cleanup_endpoint if cleanup_endpoint is not None else cfg.cleanup
    cp = (clean.provider or "").strip().lower()
    sys_prompt = cleanup_system_prompt

    if cp in ("ollama_chat", "ollama"):
        cleaned = await cleanup_ollama_chat(raw, clean, system_prompt=sys_prompt)
    elif cp in ("openai_compatible_chat", "openai_chat"):
        if cleanup_openai_api_key is not None:
            c_key = cleanup_openai_api_key
        else:
            c_key = api_key_for_cleanup()
        cleaned = await cleanup_openai_chat(raw, clean, c_key, system_prompt=sys_prompt)
    else:
        raise ValueError(
            f"Unknown cleanup.provider: {clean.provider!r}. "
            "Use ollama_chat (local) or openai_compatible_chat."
        )

    return cleaned
