"""Local dictation: record from mic, transcribe + cleanup, inject at OS focus (macOS)."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.routers.models import get_user_store
from app.services import users
from app.services.dictation_cleanup import (
    build_cleanup_endpoint,
    resolve_transcription_endpoint,
)
from app.services.storage import UserDataStore
from app.services.dictation_events import publish_event

_DEBUG_LOG_PATH = "/Users/chee/zapier ai project/.cursor/debug-55f014.log"
_DEBUG_SESSION_ID = "55f014"


def _debug_emit(location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": "dictation-sse",
        "hypothesisId": "H_DELAY",
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except OSError:
        pass
    # endregion

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
    """Print ``dictating`` every ``_DICTATION_CONSOLE_INTERVAL_SEC`` until ``stop`` is set."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_DICTATION_CONSOLE_INTERVAL_SEC)
            return
        except asyncio.TimeoutError:
            print("dictating", flush=True)


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
    """Append to daily ai-frame log (same sink as client debug logs)."""
    try:
        from app.routers.client_log import write_to_log_file

        write_to_log_file("INFO", message, data)
    except Exception:
        pass


def _store_for_username(username: str) -> UserDataStore:
    u = (username or "").strip()
    if not u or users.get_user(u) is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserDataStore(users.get_user_data_dir(u), u)


class HotkeyUserBody(BaseModel):
    username: str = Field(..., min_length=1)


def _format_verbatim_llm_request(system_prompt_full: str, user_message: str) -> str:
    """Single readonly bundle: system + user roles as sent to the cleanup LLM."""
    blocks = [
        "=== system (full message sent to cleanup LLM) ===\n" + (system_prompt_full or ""),
        "=== user (raw transcript after speech recognition) ===\n" + (user_message or ""),
    ]
    return "\n\n".join(blocks)


@router.get("/dictation/prompt-defaults")
async def dictation_prompt_defaults(request: Request) -> dict[str, str]:
    """Built-in dictation cleanup base prompt (for Context tab when using default)."""
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")
    from core.models import DEFAULT_CLEANUP_SYSTEM_PROMPT

    return {"default_cleanup_base_prompt": DEFAULT_CLEANUP_SYSTEM_PROMPT.strip()}


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
            "verbatim_request": "",
            "response_text_full": "",
            "history_index": None,
            "history_total": 0,
            "last_dictation_timestamp": None,
            "current_timestamp": None,
        }

    resolved = total - 1 if index is None else index
    resolved = max(0, min(resolved, total - 1))
    snap = entries[resolved]
    sys_full = snap.get("system_prompt_full") or ""
    user_msg = snap.get("user_message") or ""
    response = snap.get("response_text_full") or ""
    cur_ts = snap.get("timestamp") or None
    return {
        "snapshot": snap,
        "verbatim_request": _format_verbatim_llm_request(sys_full, user_msg),
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
    from platform_mac.audio import record_wav_bytes_interruptible
    from platform_mac.typing_inject import TypingInjectionError, type_text_strict

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
            use_default_base=settings.dictation_use_default_system_prompt,
            custom_base=settings.dictation_custom_system_prompt_base,
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
    cancel_event.clear()
    _dictation_stop.clear()
    print("start dictating", flush=True)
    console_stop = asyncio.Event()
    hb_task = asyncio.create_task(_dictation_console_heartbeat(console_stop))
    try:
        try:
            wav, cancelled, stopped = await asyncio.to_thread(
                record_wav_bytes_interruptible,
                None,
                cancel_event,
                stop_event=_dictation_stop,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Microphone capture failed: {e!s}. Check mic permission and PortAudio.",
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

        capture_audit: dict[str, Any] = {}
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
                capture_audit=capture_audit,
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
            empty_snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_prompt_full": cleanup_system_prompt or "",
                "user_message": raw_tr,
                "response_text_full": "(No speech detected)",
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
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_prompt_full": cleanup_system_prompt or "",
            "user_message": raw_tr,
            "response_text_full": text_out,
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
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Synthetic typing failed: {e!s}",
            ) from e

        publish_event(store.username, "dictation_done", {"source": source})
        return {"ok": True, "cancelled": False, "text": text_out}
    finally:
        console_stop.set()
        await hb_task
        print("stop dictating", flush=True)


@router.post("/dictation/record-and-type")
async def record_and_type(request: Request) -> dict[str, Any]:
    """
    Requires login cookie. Records fixed duration from default mic, runs voice pipeline,
    then types the result at the current keyboard focus (any app). macOS only.
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
        out = await _execute_dictation(
            store, cancel_event=_dictation_cancel, source="record_and_type"
        )
        _dictation_active = False
    if out.get("cancelled"):
        return {"ok": False, "cancelled": True, "text": ""}
    if out.get("skipped_empty"):
        return {"ok": True, "text": "", "skipped_empty": True}
    return {"ok": True, "text": out.get("text", "")}


@router.get("/dictation/hotkey/status")
async def dictation_hotkey_agent_status(request: Request) -> dict[str, Any]:
    """
    Whether the macOS hotkey sidecar appears alive for this login.

    Prefer a **loopback HTTP GET** to the sidecar ``/health`` (responds only while the
    process runs). Falls back to ``logs/hotkey_agent_heartbeat.json`` for older agents.
    """
    if not request.cookies.get("aiframe_session"):
        raise HTTPException(status_code=401, detail="Not logged in")

    store = get_user_store(request)
    session_user = store.username

    if sys.platform != "darwin":
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
    _dictation_server_log(
        "dictation cancel requested",
        {"client": request.client.host if request.client else None},
    )
    _set_dictation_cancel()
    _set_dictation_stop()
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
        return {"ok": True, "stopped": True}
    lock_start = time.time()
    async with _dictation_session_lock:
        _debug_emit(
            "app/routers/dictation.py:hotkey_toggle",
            "hotkey toggle lock acquired",
            {"wait_ms": int((time.time() - lock_start) * 1000), "user": body.username},
        )
        _dictation_active = True
        out = await _execute_dictation(
            store, cancel_event=_dictation_cancel, source="hotkey_toggle"
        )
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
