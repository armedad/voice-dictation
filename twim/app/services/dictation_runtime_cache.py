"""Pre-built dictation pipeline context (endpoints, prompts, device) per user."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.services.storage import Settings, UserDataStore, USERS_DIR
from core.debug_flags_logging import log_system


@dataclass(frozen=True)
class DictationRuntimePrep:
    """Snapshot used by ``_execute_dictation`` so hotkey start avoids cold setup."""

    settings: Settings
    sd_device: int | None
    llm_cleanup: bool
    gate_code: str
    clean_ep: Any | None
    openai_key: str | None
    trans_ep: Any
    cleanup_system_prompt: str | None
    stt_vocab_hint: str
    prep_error: str | None = None


_cache: dict[str, DictationRuntimePrep] = {}
_cache_mtime: dict[str, float] = {}
_cache_lock = asyncio.Lock()
_refresh_tasks: dict[str, asyncio.Task[None]] = {}


def _settings_mtime(store: UserDataStore) -> float:
    try:
        return store.settings_file.stat().st_mtime
    except OSError:
        return 0.0


def invalidate_dictation_runtime_cache(username: str | None = None) -> None:
    """Drop cached prep for ``username`` or all users when ``username`` is None."""
    if username is None:
        _cache.clear()
        _cache_mtime.clear()
        return
    u = username.strip()
    _cache.pop(u, None)
    _cache_mtime.pop(u, None)


def _build_prep_sync(store: UserDataStore) -> DictationRuntimePrep:
    from app.routers.dictation import (
        _dictation_cleanup_gate,
        _resolve_sounddevice_input_index,
    )
    from app.services.dictation_cleanup import (
        build_cleanup_endpoint,
        resolve_transcription_endpoint,
    )
    from app.services.dictation_cleanup_prompts import build_dictation_cleanup_prompts
    from core.config import load_config
    from core.models import format_vocabulary_for_whisper_initial_prompt

    settings = store.get_settings()
    sd_device = _resolve_sounddevice_input_index(settings)
    llm_cleanup, gate_code = _dictation_cleanup_gate(
        settings, user_for_log=store.username or ""
    )

    clean_ep = None
    openai_key = None
    prep_error: str | None = None
    if llm_cleanup:
        try:
            clean_ep, openai_key = build_cleanup_endpoint(settings, store.data_dir)
        except ValueError as e:
            prep_error = str(e)

    cfg = load_config()
    trans_ep = resolve_transcription_endpoint(settings.speech_model, cfg)

    cleanup_system_prompt = None
    if llm_cleanup and prep_error is None:
        cleanup_system_prompt = build_dictation_cleanup_prompts(
            settings, ""
        ).system_prompt

    stt_vocab_hint = format_vocabulary_for_whisper_initial_prompt(
        settings.dictation_vocabulary
    )

    return DictationRuntimePrep(
        settings=settings,
        sd_device=sd_device,
        llm_cleanup=llm_cleanup,
        gate_code=gate_code,
        clean_ep=clean_ep,
        openai_key=openai_key,
        trans_ep=trans_ep,
        cleanup_system_prompt=cleanup_system_prompt,
        stt_vocab_hint=stt_vocab_hint,
        prep_error=prep_error,
    )


async def refresh_dictation_runtime_cache(store: UserDataStore) -> DictationRuntimePrep:
    """Rebuild cache entry for ``store.username`` (runs sync build in a worker thread)."""
    u = (store.username or "").strip()
    if not u:
        raise ValueError("username required for dictation runtime cache")

    t0 = time.perf_counter()
    prep = await asyncio.to_thread(_build_prep_sync, store)
    mtime = _settings_mtime(store)

    async with _cache_lock:
        _cache[u] = prep
        _cache_mtime[u] = mtime

    log_system(
        level="INFO",
        message="dictation runtime cache refreshed",
        data={
            "user": u,
            "prep_ms": int((time.perf_counter() - t0) * 1000),
            "prep_error": prep.prep_error,
        },
    )
    return prep


async def get_dictation_runtime_prep(store: UserDataStore) -> DictationRuntimePrep:
    """Return cached prep, refreshing synchronously on miss or stale settings mtime."""
    u = (store.username or "").strip()
    if not u:
        prep = await asyncio.to_thread(_build_prep_sync, store)
        return prep

    mtime = _settings_mtime(store)
    async with _cache_lock:
        cached = _cache.get(u)
        if cached is not None and _cache_mtime.get(u) == mtime:
            return cached

    return await refresh_dictation_runtime_cache(store)


def schedule_dictation_runtime_cache_refresh(username: str) -> None:
    """Fire-and-forget cache rebuild after settings change."""
    u = (username or "").strip()
    if not u:
        return
    invalidate_dictation_runtime_cache(u)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    existing = _refresh_tasks.get(u)
    if existing is not None and not existing.done():
        return

    data_dir = USERS_DIR / u
    store = UserDataStore(data_dir, u)

    async def _run() -> None:
        try:
            await refresh_dictation_runtime_cache(store)
        finally:
            _refresh_tasks.pop(u, None)

    _refresh_tasks[u] = loop.create_task(_run())


async def warm_all_dictation_runtime_caches() -> None:
    """Warm cache for each user directory (startup / background)."""
    if not USERS_DIR.is_dir():
        return
    for path in sorted(USERS_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        store = UserDataStore(path, path.name)
        try:
            await refresh_dictation_runtime_cache(store)
        except Exception as e:
            log_system(
                level="INFO",
                message="dictation runtime cache warm skipped",
                data={"user": path.name, "error": str(e)[:200]},
            )
