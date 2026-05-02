"""Dictation helpers: cleanup from Settings; STT endpoint from speech_model + file config."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from app.services.providers_config import load_providers
from app.services.storage import Settings

from core.models import AdapterEndpoint, VoiceDictationConfig


def build_cleanup_endpoint(
    settings: Settings, data_dir: Path
) -> Tuple[AdapterEndpoint, Optional[str]]:
    """
    Map Settings.default_provider + default_model + URLs to a cleanup AdapterEndpoint.

    Returns (endpoint, openai_api_key): key is None for Ollama; '' for LM Studio (no auth);
    str for cloud OpenAI-compatible providers.
    """
    model = (settings.default_model or "").strip()
    if not model:
        raise ValueError(
            "Choose a default model in Settings → Models (used for dictation cleanup)."
        )

    prov = (settings.default_provider or "ollama").strip().lower()

    if prov == "ollama":
        ep = AdapterEndpoint(
            provider="ollama_chat",
            baseURL=settings.ollama_url.rstrip("/"),
            model=model,
        )
        return ep, None

    if prov == "local":
        base = settings.lm_studio_url.rstrip("/") + "/v1"
        ep = AdapterEndpoint(
            provider="openai_compatible_chat",
            baseURL=base,
            model=model,
        )
        return ep, ""

    cfg = load_providers(data_dir)
    pc = cfg.providers.get(prov)
    if not pc:
        raise ValueError(f"Unknown provider {prov!r} for dictation cleanup.")
    if pc.api_format != "openai":
        raise ValueError(
            f"Dictation cleanup needs an OpenAI-compatible chat API; "
            f"{prov} uses format {pc.api_format!r}."
        )
    if not (pc.api_key or "").strip():
        raise ValueError(f"Add an API key for {pc.name} in Settings → API Providers.")

    ep = AdapterEndpoint(
        provider="openai_compatible_chat",
        baseURL=pc.base_url.rstrip("/"),
        model=model,
    )
    return ep, (pc.api_key or "").strip()


def resolve_transcription_endpoint(
    speech_model_setting: Optional[str], cfg: VoiceDictationConfig
) -> AdapterEndpoint:
    """
    Build STT endpoint from Settings.speech_model.

    Stored value is ``provider:model`` (e.g. ``faster_whisper:small``). A legacy bare id
    (e.g. ``base``) is treated as ``faster_whisper:<id>``.

    OpenAI-compatible STT reuses ``cfg.transcription.baseURL`` from disk config.
    """
    raw = (speech_model_setting or "").strip()
    if not raw:
        return cfg.transcription
    if ":" not in raw:
        raw = f"faster_whisper:{raw}"
    prov, _, model = raw.partition(":")
    prov = (prov or "").strip().lower()
    model = (model or "").strip()
    if not model:
        return cfg.transcription

    base = (cfg.transcription.baseURL or "").strip()
    return AdapterEndpoint(
        provider=prov or cfg.transcription.provider,
        baseURL=base,
        model=model,
    )
