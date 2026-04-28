from __future__ import annotations

from typing import Any, Callable, Optional

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
    cleanup_user_prompt: Optional[str] = None,
    cleanup_user_prompt_builder: Optional[Callable[[str], str]] = None,
    cleanup_prompt_builder: Optional[Callable[[str], tuple[str, str]]] = None,
    skip_llm_cleanup: bool = False,
    transcription_initial_prompt: Optional[str] = None,
    capture_audit: Optional[dict[str, Any]] = None,
    raw_transcript_override: Optional[str] = None,
) -> str:
    """
    Transcribe WAV bytes, then optionally run LLM cleanup.

    ``transcription_endpoint`` overrides STT for this run (e.g. from Settings speech model).

    When ``cleanup_endpoint`` is set (from ai-frame Settings), it drives cleanup URL/model.
    ``cleanup_openai_api_key``: ``None`` lets OpenAI-compatible cleanup use env keys when
    using file-based cleanup; ``\"\"`` for no Authorization header (e.g. LM Studio); else
    the API key string.

    ``cleanup_system_prompt``: full system message for the cleanup LLM (when not skipping).
    ``cleanup_user_prompt``: optional wrapper for the user transcript (if not provided,
    the raw transcript is sent).
    ``cleanup_user_prompt_builder``: callable that receives the raw transcript and
    returns a user prompt. When provided, it overrides ``cleanup_user_prompt``.
    ``cleanup_prompt_builder``: callable that receives the raw transcript and returns
    (system_prompt, user_prompt). When provided, it overrides both system + user prompts.

    ``skip_llm_cleanup``: if True, return the raw transcript after STT only.

    ``transcription_initial_prompt``: optional faster-whisper ``initial_prompt`` (soft bias);
    ignored for OpenAI-compatible audio STT.

    ``capture_audit``: if provided, set ``raw_transcript`` after STT (even when skipping LLM).
    ``raw_transcript_override``: optional raw transcript to use instead of STT output.

    When ``cleanup_endpoint`` is omitted, ``~/.voice-dictation/config.json`` cleanup is used.
    """
    cfg: VoiceDictationConfig = load_config()
    trans = transcription_endpoint if transcription_endpoint is not None else cfg.transcription

    if raw_transcript_override is not None:
        raw = raw_transcript_override
    else:
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
    user_prompt = None
    if cleanup_prompt_builder is not None:
        built_sys, built_user = cleanup_prompt_builder(raw)
        if built_sys or built_user:
            sys_prompt = built_sys
            user_prompt = built_user

    if user_prompt is None:
        if cleanup_user_prompt_builder is not None:
            user_prompt = cleanup_user_prompt_builder(raw)
        else:
            user_prompt = cleanup_user_prompt or raw

    if cp in ("ollama_chat", "ollama"):
        cleaned = await cleanup_ollama_chat(user_prompt, clean, system_prompt=sys_prompt)
    elif cp in ("openai_compatible_chat", "openai_chat"):
        if cleanup_openai_api_key is not None:
            c_key = cleanup_openai_api_key
        else:
            c_key = api_key_for_cleanup()
        cleaned = await cleanup_openai_chat(user_prompt, clean, c_key, system_prompt=sys_prompt)
    else:
        raise ValueError(
            f"Unknown cleanup.provider: {clean.provider!r}. "
            "Use ollama_chat (local) or openai_compatible_chat."
        )

    return cleaned
