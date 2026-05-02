"""Local dictation: record from mic, transcribe + cleanup, inject at OS focus (macOS / Windows)."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import time
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.routers.models import get_user_store
from app.services import users
from app.services.dictation_cleanup import (
    build_cleanup_endpoint,
    resolve_transcription_endpoint,
)
from app.services.storage import Settings, UserDataStore, USERS_DIR
from app.services.dictation_events import publish_event
from core.debug_flags_logging import log_debug, log_system


def _debug_emit(location: str, message: str, data: dict[str, Any]) -> None:
    username = data.get("user") if isinstance(data.get("user"), str) else None
    log_debug(
        username=username,
        flag="DICTATION",
        level="INFO",
        message=message,
        data={"location": location, **data},
    )

router = APIRouter(tags=["dictation"])

RECORD_SECONDS = 10.0
_DICTATION_CONSOLE_INTERVAL_SEC = 3.0

# Repo root (parent of ai-frame/): same layout as app.main.VOICE_DICTATION_ROOT
_VOICE_DICTATION_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HOTKEY_AGENT_HEARTBEAT = _VOICE_DICTATION_ROOT / "logs" / "hotkey_agent_heartbeat.json"
# Fallback when loopback ping to the sidecar fails (older agent or bind error).
_HEARTBEAT_MAX_AGE_SEC = 120.0
_DEFAULT_HOTKEY_PING_PORT = 18447


def _hotkey_agent_ping_port() -> int:
    raw = os.environ.get(
        "VOICE_DICTATION_HOTKEY_PING_PORT", str(_DEFAULT_HOTKEY_PING_PORT)
    ).strip()
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_HOTKEY_PING_PORT


def _probe_hotkey_agent_via_ping(session_user: str) -> tuple[str, dict[str, Any]]:
    """
    GET http://127.0.0.1:<ping_port>/health from the sidecar.

    Returns (status, details) where status is ``alive`` | ``wrong_user`` | ``unreachable``.
    """
    port = _hotkey_agent_ping_port()
    url = f"http://127.0.0.1:{port}/health"
    try:
        r = httpx.get(url, timeout=0.35)
        if r.status_code != 200:
            return "unreachable", {"ping_url": url, "http_status": r.status_code}
        data = r.json()
    except Exception as e:
        return "unreachable", {"ping_url": url, "error": str(e)[:200]}

    if not isinstance(data, dict) or not data.get("ok"):
        return "unreachable", {"ping_url": url, "detail": "bad_json"}
    u = data.get("username")
    if not isinstance(u, str) or not u.strip():
        return "unreachable", {"ping_url": url, "detail": "no_username"}
    u = u.strip()
    if u != session_user:
        return "wrong_user", {"ping_url": url, "ping_username": u}
    return "alive", {"ping_url": url, "ping_username": u}

_dictation_cancel = threading.Event()
_dictation_stop = threading.Event()
_dictation_session_lock = asyncio.Lock()
_dictation_active = False


def _set_dictation_cancel() -> None:
    _dictation_cancel.set()


def _set_dictation_stop() -> None:
    _dictation_stop.set()


async def _dictation_console_heartbeat(stop: asyncio.Event) -> None:
    """Emit ``dictating`` heartbeat every interval until ``stop`` is set."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_DICTATION_CONSOLE_INTERVAL_SEC)
            return
        except asyncio.TimeoutError:
            log_system(level="INFO", message="dictating")


def _emit_overlap(store: UserDataStore, source: str) -> None:
    _dictation_server_log(
        "dictation overlap detected",
        {"source": source, "user": store.username},
    )
    publish_event(store.username, "dictation_overlap", {"source": source})
    _debug_emit(
        "app/routers/dictation.py:overlap",
        "dictation overlap detected",
        {"source": source, "user": store.username},
    )


def _require_loopback(request: Request) -> None:
    client = request.client
    host = (client.host if client else "") or ""
    if host not in ("127.0.0.1", "::1"):
        raise HTTPException(
            status_code=403,
            detail="Hotkey endpoints accept connections from loopback only.",
        )


def _dictation_server_log(message: str, data: dict[str, Any] | None = None) -> None:
    """Append to unified daily ai-frame log."""
    log_system(level="INFO", message=message, data=data)


def _maybe_dictation_ui_sound(kind: str) -> None:
    """
    Optional short OS chime when dictation recording starts (``start``) or when the
    microphone capture phase ends (``end`` — before STT, cleanup, or typing).

    Disable with ``VOICE_DICTATION_UI_SOUNDS=0``.
    """
    raw = os.environ.get("VOICE_DICTATION_UI_SOUNDS", "1").strip().lower()
    if raw in ("0", "false", "no"):
        return
    if kind not in ("start", "end"):
        return

    def _worker() -> None:
        try:
            if sys.platform == "darwin":
                path = (
                    "/System/Library/Sounds/Tink.aiff"
                    if kind == "start"
                    else "/System/Library/Sounds/Pop.aiff"
                )
                if not Path(path).is_file():
                    return
                subprocess.run(
                    ["afplay", path],
                    check=False,
                    timeout=3.0,
                    capture_output=True,
                )
            elif sys.platform == "win32":
                import winsound

                winsound.PlaySound(
                    "SystemAsterisk" if kind == "start" else "SystemDefault",
                    winsound.SND_ALIAS | winsound.SND_ASYNC,
                )
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def _dictation_cleanup_gate(settings: Settings, *, user_for_log: str) -> tuple[bool, str]:
    """
    Decide whether this dictation run should call the cleanup LLM.

    Returns ``(effective, gate_code)`` where ``gate_code`` is always set:
    ``effective_on`` | ``dictation_llm_cleanup_enabled_false`` |
    ``default_model_blank_after_strip``.
    """
    if not settings.dictation_llm_cleanup_enabled:
        return False, "dictation_llm_cleanup_enabled_false"
    if not (settings.default_model or "").strip():
        if user_for_log.strip():
            _dictation_server_log(
                "Dictation LLM cleanup is enabled but no default model is set; "
                "running transcription only (pick a model in Settings → Models or disable cleanup).",
                {"user": user_for_log.strip()},
            )
        return False, "default_model_blank_after_strip"
    return True, "effective_on"


def _raw_settings_json_subset(path: Path, keys: tuple[str, ...]) -> dict[str, Any]:
    """Read JSON object keys as stored on disk (no merge). For trace logs only."""
    out: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        out["read_error"] = repr(e)[:400]
        return out
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        out["json_error"] = repr(e)[:400]
        return out
    if not isinstance(raw, dict):
        out["json_top_type"] = type(raw).__name__
        return out
    out["subset"] = {k: raw[k] if k in raw else "__key_absent__" for k in keys}
    return out


def _dictation_cleanup_gate_trace(
    store: UserDataStore,
    source: str,
    settings: Settings,
    llm_cleanup: bool,
    gate_code: str,
) -> None:
    """
    One log line with merged Settings, on-disk user/template JSON, and absolute paths.

    Use this to see why the server skipped cleanup (no guessing vs browser UI).
    """
    keys = ("dictation_llm_cleanup_enabled", "default_model", "default_provider")
    user_disk = _raw_settings_json_subset(store.settings_file, keys)
    tmpl_path = USERS_DIR / "_default" / "settings.json"
    tmpl_disk = _raw_settings_json_subset(tmpl_path, keys)
    dm = settings.default_model
    payload: dict[str, Any] = {
        "user": store.username,
        "source": source,
        "merged_llm_cleanup_effective": llm_cleanup,
        "merged_gate_code": gate_code,
        "merged_dictation_llm_cleanup_enabled": settings.dictation_llm_cleanup_enabled,
        "merged_dictation_llm_cleanup_enabled_python_type": type(
            settings.dictation_llm_cleanup_enabled
        ).__name__,
        "merged_default_model_repr": repr(dm)[:800],
        "merged_default_model_outer_len": len(dm or ""),
        "merged_default_model_strip_len": len((dm or "").strip()),
        "merged_default_provider": settings.default_provider,
        "user_settings_json": user_disk,
        "default_template_settings_json": tmpl_disk,
    }
    _dictation_server_log("dictation cleanup gate trace", payload)


def _dictation_cleanup_debug_logger(
    store: UserDataStore, source: str
) -> Callable[[dict[str, Any]], None]:
    """Writes one structured line per dictation run to the daily ai-frame log (see client_log)."""

    def _emit(payload: dict[str, Any]) -> None:
        _dictation_server_log(
            "dictation cleanup LLM debug",
            {"user": store.username, "source": source, **payload},
        )

    return _emit


def _store_for_username(username: str) -> UserDataStore:
    u = (username or "").strip()
    if not u or users.get_user(u) is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserDataStore(users.get_user_data_dir(u), u)


class HotkeyUserBody(BaseModel):
    username: str = Field(..., min_length=1)


class DictationTextBody(BaseModel):
    text: str = Field(..., min_length=1)


async def _execute_dictation_from_text(
    store: UserDataStore,
    *,
    raw_text: str,
    source: str,
) -> dict[str, Any]:
    """Run cleanup-only pipeline from a provided transcript (no mic)."""
    from core.config import load_config
    from core.models import (
        format_dictation_cleanup_user_message_with_template,
        format_vocabulary_for_whisper_initial_prompt,
        render_dictation_cleanup_system_prompt,
    )
    from core.orchestrator import run_pipeline

    settings = store.get_settings()
    llm_cleanup, gate_code = _dictation_cleanup_gate(
        settings, user_for_log=store.username or ""
    )
    _dictation_cleanup_gate_trace(store, source, settings, llm_cleanup, gate_code)

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
        cleanup_system_prompt = render_dictation_cleanup_system_prompt(
            settings.dictation_cleanup_system_prompt_template,
            vocabulary=settings.dictation_vocabulary,
            user_instructions=settings.dictation_instructions,
        )

    stt_vocab_hint = format_vocabulary_for_whisper_initial_prompt(
        settings.dictation_vocabulary
    )
    raw_transcript = (raw_text or "").strip()
    if not raw_transcript:
        empty_snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_prompt_full": cleanup_system_prompt or "",
            "user_message": "",
            "response_text_full": "(No text provided)",
            "cleanup_user_prompt": "",
            "llm_cleanup_enabled": llm_cleanup,
            "cleanup_provider": getattr(clean_ep, "provider", None) if clean_ep else None,
            "cleanup_model": getattr(clean_ep, "model_name", None) if clean_ep else None,
            "cleanup_base_url": (clean_ep.baseURL if clean_ep else "") or "",
            "status": "empty_transcript",
            "source": source,
        }
        store.save_dictation_last_llm_snapshot(empty_snapshot)
        publish_event(
            store.username,
            "dictation_context_updated",
            {"source": source, "status": "empty_transcript"},
        )
        publish_event(store.username, "dictation_empty", {"source": source})
        return {"ok": True, "cancelled": False, "text": "", "skipped_empty": True}

    cleanup_user_prompt = (
        format_dictation_cleanup_user_message_with_template(
            raw_transcript, settings.dictation_cleanup_user_prompt_template
        )
        if llm_cleanup
        else ""
    )

    try:
        text = await run_pipeline(
            b"",
            "dictation.txt",
            transcription_endpoint=trans_ep,
            cleanup_endpoint=clean_ep,
            cleanup_openai_api_key=openai_key,
            cleanup_system_prompt=cleanup_system_prompt,
            cleanup_user_prompt=cleanup_user_prompt,
            skip_llm_cleanup=not llm_cleanup,
            transcription_initial_prompt=stt_vocab_hint,
            capture_audit=None,
            raw_transcript_override=raw_transcript,
            cleanup_debug_log=_dictation_cleanup_debug_logger(store, source),
            cleanup_skip_gate_code=(gate_code if not llm_cleanup else None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Transcription or cleanup failed: {e!s}",
        ) from e

    text_out = (text or "").strip()
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_prompt_full": cleanup_system_prompt or "",
        "user_message": raw_transcript,
        "response_text_full": text_out,
        "cleanup_user_prompt": cleanup_user_prompt,
        "llm_cleanup_enabled": llm_cleanup,
        "cleanup_provider": getattr(clean_ep, "provider", None) if clean_ep else None,
        "cleanup_model": getattr(clean_ep, "model_name", None) if clean_ep else None,
        "cleanup_base_url": (clean_ep.baseURL if clean_ep else "") or "",
        "source": source,
    }
    store.save_dictation_last_llm_snapshot(snapshot)
    publish_event(
        store.username,
        "dictation_context_updated",
        {"source": source, "status": "ok"},
    )
    publish_event(store.username, "dictation_done", {"source": source})
    return {"ok": True, "cancelled": False, "text": text_out}


@router.get("/dictation/prompt-defaults")
async def dictation_prompt_defaults(request: Request) -> dict[str, str]:
    """Built-in dictation cleanup prompts (Context tab restore / defaults)."""
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")
    from core.models import (
        DEFAULT_CLEANUP_SYSTEM_PROMPT,
        DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE,
    )

    return {
        "default_cleanup_base_prompt": DEFAULT_CLEANUP_SYSTEM_PROMPT.strip(),
        "default_cleanup_system_prompt_template": (
            DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE.strip()
        ),
    }


def _resolve_sounddevice_input_index(settings: Settings) -> int | None:
    """
    ``None`` → use PortAudio / OS default for this process (omit ``device`` in ``sounddevice``).

    If the saved index no longer exists (device unplugged), return ``None``.
    """
    from core.portaudio_devices import list_input_devices

    raw = settings.dictation_input_device_index
    if raw is None:
        return None
    if not isinstance(raw, int) or raw < 0:
        return None
    devices, _, err = list_input_devices()
    if err:
        return None
    valid = {int(d["index"]) for d in devices}
    if raw not in valid:
        return None
    return raw


@router.get("/dictation/audio-input")
async def dictation_audio_input(request: Request) -> dict[str, Any]:
    """Enumerate input microphones + current system default (Preferences Voice input)."""
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")

    from core.portaudio_devices import list_input_devices

    devices, system_default, err = await asyncio.to_thread(list_input_devices)
    if err:
        return {
            "ok": False,
            "error": err,
            "devices": [],
            "system_default": system_default,
        }
    return {
        "ok": True,
        "error": None,
        "devices": devices,
        "system_default": system_default,
    }


def _context_tab_llm_display(snap: dict[str, Any]) -> tuple[str, str, str]:
    """
    Build (system_text, user_text, response_text) for the Context tab.

    Snapshots omit ``system_prompt_full`` / ``cleanup_user_prompt`` when no cleanup LLM
    ran (rewrite off in Profile, or on but no default model so only transcription ran).
    ``user_message`` in snapshots is the raw STT transcript, not the cleanup user prompt.
    """
    response = snap.get("response_text_full") or ""
    if not isinstance(snap, dict):
        return "", "", response

    sys_raw = snap.get("system_prompt_full")
    system = sys_raw if isinstance(sys_raw, str) else ""
    cup = snap.get("cleanup_user_prompt")
    user_prompt = cup if isinstance(cup, str) else ("" if cup is None else str(cup))

    raw_msg = snap.get("user_message")
    raw = raw_msg if isinstance(raw_msg, str) else ""

    llm_off = snap.get("llm_cleanup_enabled") is False

    if llm_off:
        sys_out = (
            system.strip()
            and system
            or (
                "(No system message was sent to a cleanup LLM — either “Run dictation through LLM "
                "before typing” was off in Profile, or it was on but no default chat model was set "
                "so only transcription ran.)"
            )
        )
        if user_prompt.strip():
            user_out = user_prompt
        elif raw.strip():
            user_out = (
                "(No user message was sent to a cleanup LLM; raw speech-to-text was typed as-is.)\n\n"
                + raw.strip()
            )
        else:
            user_out = "(No user message was sent to a cleanup LLM.)"
        return sys_out, user_out, response

    # Cleanup LLM was used for this saved run.
    sys_out = system if system.strip() else "(No system prompt text was stored for this history entry.)"
    if user_prompt.strip():
        user_out = user_prompt
    elif raw.strip():
        user_out = (
            "(Exact user message to the cleanup LLM was not stored in this history entry. "
            "Raw transcript from that run:)\n\n"
            + raw.strip()
        )
    else:
        user_out = "(No user message text was stored for this history entry.)"
    return sys_out, user_out, response


@router.get("/dictation/last-context")
async def dictation_last_context(
    request: Request,
    index: int | None = Query(
        default=None,
        description="0-based index into saved dictations (oldest=0). Omit for newest.",
    ),
) -> dict[str, Any]:
    """Dictation LLM snapshot(s) for the Context tab; optional index browses history."""
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")
    store = get_user_store(request)
    entries = store.load_dictation_history_entries()
    total = len(entries)
    last_ts: str | None = None
    if total:
        last_ts = (entries[-1].get("timestamp") or None) if isinstance(entries[-1], dict) else None

    if total == 0:
        return {
            "snapshot": {},
            "cleanup_system_sent": "",
            "cleanup_user_sent": "",
            "response_text_full": "",
            "history_index": None,
            "history_total": 0,
            "last_dictation_timestamp": None,
            "current_timestamp": None,
        }

    resolved = total - 1 if index is None else index
    resolved = max(0, min(resolved, total - 1))
    snap = entries[resolved]
    cur_ts = snap.get("timestamp") or None
    sys_disp, user_disp, response = _context_tab_llm_display(snap)
    return {
        "snapshot": snap,
        "cleanup_system_sent": sys_disp,
        "cleanup_user_sent": user_disp,
        "response_text_full": response,
        "history_index": resolved,
        "history_total": total,
        "last_dictation_timestamp": last_ts,
        "current_timestamp": cur_ts,
    }


async def _execute_dictation(
    store: UserDataStore,
    *,
    cancel_event: threading.Event,
    source: str = "dictation",
) -> dict[str, Any]:
    """Shared dictation pipeline: record → STT/cleanup → type. Respects ``cancel_event``."""
    if sys.platform == "darwin":
        from platform_mac.audio import record_wav_bytes_interruptible
        from platform_mac.typing_inject import TypingInjectionError, type_text_strict
    elif sys.platform == "win32":
        from platform_win.audio import record_wav_bytes_interruptible
        from platform_win.typing_inject import TypingInjectionError, type_text_strict
    else:
        raise HTTPException(
            status_code=501,
            detail="Dictation + synthetic typing is only wired for macOS and Windows in this build.",
        )

    from core.config import load_config
    from core.models import (
        format_dictation_cleanup_user_message_with_template,
        format_vocabulary_for_whisper_initial_prompt,
        render_dictation_cleanup_system_prompt,
    )
    from core.orchestrator import run_pipeline

    settings = store.get_settings()
    sd_device = _resolve_sounddevice_input_index(settings)
    llm_cleanup, gate_code = _dictation_cleanup_gate(
        settings, user_for_log=store.username or ""
    )
    _dictation_cleanup_gate_trace(store, source, settings, llm_cleanup, gate_code)

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
        cleanup_system_prompt = render_dictation_cleanup_system_prompt(
            settings.dictation_cleanup_system_prompt_template,
            vocabulary=settings.dictation_vocabulary,
            user_instructions=settings.dictation_instructions,
        )

    stt_vocab_hint = format_vocabulary_for_whisper_initial_prompt(
        settings.dictation_vocabulary
    )

    _debug_emit(
        "app/routers/dictation.py:_execute_dictation",
        "record start enter",
        {"source": source, "user": store.username},
    )
    _dictation_server_log(
        "dictation record start",
        {"source": source, "user": store.username, "seconds": RECORD_SECONDS},
    )
    publish_event(store.username, "dictation_start", {"source": source})
    _maybe_dictation_ui_sound("start")
    cancel_event.clear()
    _dictation_stop.clear()
    log_system(level="INFO", message="start dictating", data={"source": source, "user": store.username})
    console_stop = asyncio.Event()
    hb_task = asyncio.create_task(_dictation_console_heartbeat(console_stop))
    try:
        try:
            wav, cancelled, stopped = await asyncio.to_thread(
                record_wav_bytes_interruptible,
                None,
                cancel_event,
                stop_event=_dictation_stop,
                device=sd_device,
            )
        except Exception as e:
            hint = (
                "Check mic permission and PortAudio."
                if sys.platform == "darwin"
                else "Check microphone privacy settings and that the input device is available."
            )
            raise HTTPException(
                status_code=500,
                detail=f"Microphone capture failed: {e!s}. {hint}",
            ) from e

        if cancelled or not wav:
            _debug_emit(
                "app/routers/dictation.py:_execute_dictation",
                "record cancelled or empty",
                {"source": source, "user": store.username, "cancelled": cancelled},
            )
            _dictation_server_log(
                "dictation record cancelled or empty",
                {"source": source, "user": store.username, "cancelled": cancelled},
            )
            publish_event(store.username, "dictation_cancelled", {"source": source})
            _maybe_dictation_ui_sound("end")
            return {"ok": False, "cancelled": True, "text": ""}

        if stopped:
            _debug_emit(
                "app/routers/dictation.py:_execute_dictation",
                "record stop event",
                {"source": source, "user": store.username},
            )
            _dictation_server_log(
                "dictation record stopped",
                {"source": source, "user": store.username, "seconds": "toggle_stop"},
            )
            publish_event(store.username, "dictation_stop", {"source": source})

        # Mic / PortAudio capture is finished (``InputStream`` closed); chime before STT & typing.
        _maybe_dictation_ui_sound("end")

        capture_audit: dict[str, Any] = {}
        try:
            text = await run_pipeline(
                wav,
                "dictation.wav",
                transcription_endpoint=trans_ep,
                cleanup_endpoint=clean_ep,
                cleanup_openai_api_key=openai_key,
                cleanup_system_prompt=cleanup_system_prompt,
                cleanup_user_prompt=None,
                cleanup_user_prompt_builder=(
                    (lambda raw: format_dictation_cleanup_user_message_with_template(
                        raw, settings.dictation_cleanup_user_prompt_template
                    ))
                    if llm_cleanup
                    else None
                ),
                skip_llm_cleanup=not llm_cleanup,
                transcription_initial_prompt=stt_vocab_hint,
                capture_audit=capture_audit,
                cleanup_debug_log=_dictation_cleanup_debug_logger(store, source),
                cleanup_skip_gate_code=(gate_code if not llm_cleanup else None),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Transcription or cleanup failed: {e!s}",
            ) from e

        text_out = (text or "").strip()
        if not text_out:
            raw_tr = (capture_audit.get("raw_transcript") or "").strip()
            cup_empty = ""
            if llm_cleanup and raw_tr:
                cup_empty = format_dictation_cleanup_user_message_with_template(
                    raw_tr, settings.dictation_cleanup_user_prompt_template
                )
            empty_snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_prompt_full": cleanup_system_prompt or "",
                "user_message": raw_tr,
                "response_text_full": "(No speech detected)",
                "cleanup_user_prompt": cup_empty,
                "llm_cleanup_enabled": llm_cleanup,
                "cleanup_provider": getattr(clean_ep, "provider", None) if clean_ep else None,
                "cleanup_model": getattr(clean_ep, "model_name", None) if clean_ep else None,
                "cleanup_base_url": (clean_ep.baseURL if clean_ep else "") or "",
                "status": "empty_transcript",
                "source": source,
            }
            store.save_dictation_last_llm_snapshot(empty_snapshot)
            publish_event(
                store.username,
                "dictation_context_updated",
                {"source": source, "status": "empty_transcript"},
            )
            _dictation_server_log(
                "dictation skipped empty transcript",
                {"source": source, "user": store.username, "raw_len": len(raw_tr)},
            )
            publish_event(store.username, "dictation_empty", {"source": source})
            return {"ok": True, "cancelled": False, "text": "", "skipped_empty": True}

        raw_tr = capture_audit.get("raw_transcript", "")
        cleanup_user_prompt = (
            format_dictation_cleanup_user_message_with_template(
                raw_tr, settings.dictation_cleanup_user_prompt_template
            )
            if llm_cleanup
            else ""
        )
        text_out = (text or "").strip()
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_prompt_full": cleanup_system_prompt or "",
            "user_message": raw_tr,
            "response_text_full": text_out,
            "cleanup_user_prompt": cleanup_user_prompt,
            "llm_cleanup_enabled": llm_cleanup,
            "cleanup_provider": getattr(clean_ep, "provider", None) if clean_ep else None,
            "cleanup_model": getattr(clean_ep, "model_name", None) if clean_ep else None,
            "cleanup_base_url": (clean_ep.baseURL if clean_ep else "") or "",
        }
        store.save_dictation_last_llm_snapshot(snapshot)
        publish_event(
            store.username,
            "dictation_context_updated",
            {"source": source, "status": "ok"},
        )

        _dictation_server_log(
            "dictation pipeline ok before type",
            {"source": source, "user": store.username, "text_len": len(text_out)},
        )
        try:
            await asyncio.to_thread(type_text_strict, text_out)
        except TypingInjectionError as e:
            _dictation_server_log(
                "dictation typing failed",
                {"source": source, "user": store.username, "error": str(e)},
            )
            publish_event(
                store.username,
                "dictation_typing_failed",
                {"source": source, "error": str(e)},
            )
        except Exception as e:
            _dictation_server_log(
                "dictation typing failed",
                {"source": source, "user": store.username, "error": str(e)},
            )
            publish_event(
                store.username,
                "dictation_typing_failed",
                {"source": source, "error": str(e)},
            )

        publish_event(store.username, "dictation_done", {"source": source})
        return {"ok": True, "cancelled": False, "text": text_out}
    finally:
        console_stop.set()
        await hb_task
        log_system(level="INFO", message="stop dictating", data={"source": source, "user": store.username})


@router.post("/dictation/record-and-type")
async def record_and_type(request: Request) -> dict[str, Any]:
    """
    Requires login cookie. Records fixed duration from default mic, runs voice pipeline,
    then types the result at the current keyboard focus (any app). macOS / Windows.
    """
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")

    store = get_user_store(request)
    global _dictation_active
    lock_start = time.time()
    _debug_emit(
        "app/routers/dictation.py:record_and_type",
        "record_and_type entry",
        {"user": store.username, "active": _dictation_active},
    )
    if _dictation_active:
        _emit_overlap(store, "record_and_type")
    async with _dictation_session_lock:
        _debug_emit(
            "app/routers/dictation.py:record_and_type",
            "record_and_type lock acquired",
            {"wait_ms": int((time.time() - lock_start) * 1000), "user": store.username},
        )
        _dictation_active = True
        try:
            out = await _execute_dictation(
                store, cancel_event=_dictation_cancel, source="record_and_type"
            )
        finally:
            _dictation_active = False
    if out.get("cancelled"):
        return {"ok": False, "cancelled": True, "text": ""}
    if out.get("skipped_empty"):
        return {"ok": True, "text": "", "skipped_empty": True}
    return {"ok": True, "text": out.get("text", "")}


@router.post("/dictation/cleanup-text")
async def dictation_cleanup_text(request: Request, body: DictationTextBody) -> dict[str, Any]:
    """Run dictation cleanup using provided text instead of mic capture."""
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")
    store = get_user_store(request)
    if _dictation_active:
        _emit_overlap(store, "cleanup_text")
    out = await _execute_dictation_from_text(
        store, raw_text=body.text, source="cleanup_text"
    )
    if out.get("skipped_empty"):
        return {"ok": True, "text": "", "skipped_empty": True}
    return {"ok": True, "text": out.get("text", "")}


@router.get("/dictation/hotkey/status")
async def dictation_hotkey_agent_status(request: Request) -> dict[str, Any]:
    """
    Whether the embedded hotkey sidecar appears alive for this login (macOS / Windows).

    Prefer a **loopback HTTP GET** to the sidecar ``/health`` (responds only while the
    process runs). Falls back to ``logs/hotkey_agent_heartbeat.json`` for older agents.
    """
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")

    store = get_user_store(request)
    session_user = store.username

    if sys.platform not in ("darwin", "win32"):
        return {
            "macos_dictation_hotkeys_supported": False,
            "agent_running_for_you": None,
            "liveness_source": None,
            "heartbeat_username": None,
            "heartbeat_age_sec": None,
            "session_username": session_user,
        }

    ping_status, ping_detail = await asyncio.to_thread(
        _probe_hotkey_agent_via_ping, session_user
    )
    if ping_status == "alive":
        return {
            "macos_dictation_hotkeys_supported": True,
            "agent_running_for_you": True,
            "liveness_source": "ping",
            **ping_detail,
            "heartbeat_username": None,
            "heartbeat_age_sec": None,
            "session_username": session_user,
        }
    if ping_status == "wrong_user":
        return {
            "macos_dictation_hotkeys_supported": True,
            "agent_running_for_you": False,
            "liveness_source": "ping",
            **ping_detail,
            "heartbeat_username": None,
            "heartbeat_age_sec": None,
            "session_username": session_user,
        }

    hb_user: str | None = None
    age_sec: float | None = None
    if _HOTKEY_AGENT_HEARTBEAT.exists():
        try:
            raw = json.loads(_HOTKEY_AGENT_HEARTBEAT.read_text(encoding="utf-8"))
            hb_user = raw.get("username") if isinstance(raw.get("username"), str) else None
            ts = float(raw.get("ts", 0))
            if ts > 0:
                age_sec = max(0.0, time.time() - ts)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    alive = (
        age_sec is not None
        and age_sec <= _HEARTBEAT_MAX_AGE_SEC
        and hb_user is not None
        and session_user is not None
        and hb_user == session_user
    )

    return {
        "macos_dictation_hotkeys_supported": True,
        "agent_running_for_you": alive,
        "liveness_source": "heartbeat_file" if alive or hb_user is not None else "none",
        **({"ping_unreachable": True, **ping_detail} if ping_status == "unreachable" else {}),
        "heartbeat_username": hb_user,
        "heartbeat_age_sec": round(age_sec, 1) if age_sec is not None else None,
        "session_username": session_user,
    }


@router.post("/dictation/hotkey/cancel")
async def dictation_hotkey_cancel(request: Request) -> dict[str, Any]:
    """Signal in-process dictation recording to stop (loopback-only)."""
    _require_loopback(request)
    _debug_emit(
        "app/routers/dictation.py:hotkey_cancel",
        "hotkey cancel endpoint hit",
        {
            "client": request.client.host if request.client else None,
            "active": _dictation_active,
            "cancel_event_before": _dictation_cancel.is_set(),
            "stop_event_before": _dictation_stop.is_set(),
        },
    )
    _dictation_server_log(
        "dictation cancel requested",
        {"client": request.client.host if request.client else None},
    )
    _set_dictation_cancel()
    _set_dictation_stop()
    _debug_emit(
        "app/routers/dictation.py:hotkey_cancel",
        "hotkey cancel flags set",
        {
            "active": _dictation_active,
            "cancel_event_after": _dictation_cancel.is_set(),
            "stop_event_after": _dictation_stop.is_set(),
        },
    )
    session_user = request.cookies.get("aiframe_session") or ""
    if session_user:
        publish_event(session_user, "dictation_cancel_signal", {})
    return {"ok": True}


@router.post("/dictation/hotkey/toggle")
async def dictation_hotkey_toggle(
    request: Request,
    body: HotkeyUserBody,
) -> dict[str, Any]:
    """
    Start dictation for ``body.username`` using ``X-Voice-Dictation-Secret`` and per-user
    ``hotkey_local_secret.txt``. Loopback-only.
    """
    global _dictation_active
    _require_loopback(request)
    secret_hdr = request.headers.get("x-voice-dictation-secret")
    if not secret_hdr or not secret_hdr.strip():
        raise HTTPException(status_code=401, detail="Missing X-Voice-Dictation-Secret header")

    store = _store_for_username(body.username)
    expected = store.read_hotkey_secret()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="Hotkey secret not configured; save a dictation hotkey in Preferences first.",
        )
    if not secrets.compare_digest(secret_hdr.strip(), expected.strip()):
        raise HTTPException(status_code=403, detail="Invalid hotkey secret")

    settings = store.get_settings()
    if not settings.dictation_hotkey_toggle:
        raise HTTPException(status_code=400, detail="No dictation toggle hotkey configured")

    _debug_emit(
        "app/routers/dictation.py:hotkey_toggle",
        "hotkey toggle entry",
        {"user": body.username, "active": _dictation_active},
    )
    _dictation_server_log(
        "dictation hotkey toggle accepted",
        {"user": body.username, "client": request.client.host if request.client else None},
    )
    if _dictation_active:
        _dictation_server_log("dictation hotkey toggle -> stop active session", {"user": body.username})
        _set_dictation_stop()
        publish_event(store.username, "dictation_stop", {"source": "hotkey_toggle"})
        # End chime: played when the in-flight _execute_dictation hits dictation_done.
        return {"ok": True, "stopped": True}
    lock_start = time.time()
    async with _dictation_session_lock:
        _debug_emit(
            "app/routers/dictation.py:hotkey_toggle",
            "hotkey toggle lock acquired",
            {"wait_ms": int((time.time() - lock_start) * 1000), "user": body.username},
        )
        _dictation_active = True
        try:
            out = await _execute_dictation(
                store, cancel_event=_dictation_cancel, source="hotkey_toggle"
            )
        finally:
            _dictation_active = False
    if out.get("cancelled"):
        _dictation_server_log(
            "dictation hotkey toggle finished cancelled",
            {"user": body.username},
        )
        return {"ok": False, "cancelled": True, "text": ""}
    if out.get("skipped_empty"):
        _dictation_server_log(
            "dictation hotkey toggle finished empty transcript",
            {"user": body.username},
        )
        return {"ok": True, "text": "", "skipped_empty": True}
    _dictation_server_log(
        "dictation hotkey toggle finished ok",
        {"user": body.username},
    )
    return {"ok": True, "text": out.get("text", "")}
