"""
macOS global dictation hotkeys: Carbon ``RegisterEventHotKey`` + httpx to local FastAPI.

Uses system hotkey registration (narrow scope) instead of a global key tap, so macOS
typically does **not** require Input Monitoring for this sidecar.

Env:
  VOICE_DICTATION_PORT — default 8000 (ai-frame URL for toggle/cancel POST)
  VOICE_DICTATION_AI_FRAME_USER — username under ai-frame/users/
  VOICE_DICTATION_HOTKEY_PING_PORT — loopback HTTP ``/health`` for liveness (default 18447)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

_DEFAULT_HOTKEY_PING_PORT = 18447
_HOTKEY_SETTINGS_POLL_FALLBACK_SEC = 30.0
_DEBUG_LOG_PATH = "/Users/chee/zapier ai project/.cursor/debug-55f014.log"
_DEBUG_SESSION_ID = "55f014"

# Repo root (parent of platform_mac/)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.hotkey_chord import normalize_chord

_LOG = logging.getLogger("hotkey_agent")


def _debug_emit(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
) -> None:
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
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


def _users_dir() -> Path:
    return ROOT / "ai-frame" / "users"


def _resolve_username() -> str:
    """Prefer env, then marker file written when hotkeys are saved in the UI."""
    env_u = (os.environ.get("VOICE_DICTATION_AI_FRAME_USER") or "").strip()
    if env_u:
        return env_u
    marker = _users_dir() / ".hotkey_agent_target_username"
    if marker.exists():
        try:
            t = marker.read_text(encoding="utf-8").strip()
        except OSError:
            t = ""
        if t and (_users_dir() / t).is_dir():
            return t
    return ""


def _load_user_chords_and_secret(
    username: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, float]:
    """Return (toggle_chord, cancel_chord, secret, settings_mtime)."""
    base = _users_dir() / username
    settings_path = base / "settings.json"
    secret_path = base / "hotkey_local_secret.txt"
    mtime = settings_path.stat().st_mtime if settings_path.exists() else 0.0
    toggle = cancel = None
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            _LOG.warning("Could not read settings.json: %s", e)
            data = {}
        if data.get("dictation_hotkey_toggle") is not None:
            try:
                toggle = normalize_chord(data["dictation_hotkey_toggle"])
            except ValueError as e:
                _LOG.warning("Invalid dictation_hotkey_toggle: %s", e)
        if data.get("dictation_hotkey_cancel") is not None:
            try:
                cancel = normalize_chord(data["dictation_hotkey_cancel"])
            except ValueError as e:
                _LOG.warning("Invalid dictation_hotkey_cancel: %s", e)
    secret = None
    if secret_path.exists():
        try:
            secret = secret_path.read_text(encoding="utf-8").strip() or None
        except OSError:
            secret = None
    return toggle, cancel, secret, mtime


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        log_path = ROOT / "logs" / "hotkey-agent.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        abs_log = str(log_path.resolve())
        have_file = any(
            isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == abs_log
            for h in _LOG.handlers
        )
        if not have_file:
            fh = logging.FileHandler(abs_log, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            _LOG.addHandler(fh)
        _LOG.setLevel(logging.INFO)
    except OSError:
        _LOG.exception("Could not attach file logger for hotkey agent")
    if sys.platform != "darwin":
        _LOG.error("hotkey_agent is only supported on macOS in this build.")
        sys.exit(1)
    run_id = f"hotkey-agent-{os.getpid()}-{int(time.time())}"
    prev_sig_handlers: dict[int, Any] = {}

    def _signal_debug(signum: int, _frame: Any) -> None:
        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H1",
            location="platform_mac/hotkey_agent.py:signal",
            message="signal received",
            data={"signum": signum},
        )
        # endregion
        prev = prev_sig_handlers.get(signum)
        if callable(prev):
            prev(signum, _frame)

    for sig in (signal.SIGINT, signal.SIGTERM):
        prev_sig_handlers[sig] = signal.getsignal(sig)
        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H1",
            location="platform_mac/hotkey_agent.py:signal",
            message="install signal handler",
            data={"signum": sig, "prev": str(prev_sig_handlers[sig])},
        )
        # endregion
        signal.signal(sig, _signal_debug)
    # region agent log
    _debug_emit(
        run_id=run_id,
        hypothesis_id="H1",
        location="platform_mac/hotkey_agent.py:main:entry",
        message="hotkey agent starting",
        data={
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
            "is_main_thread": threading.current_thread() is threading.main_thread(),
        },
    )
    # endregion

    quick_flag = os.environ.get("VOICE_DICTATION_USE_QUICKMACHOTKEY", "").strip().lower()
    use_quick = quick_flag not in {"0", "false", "no"}
    if use_quick:
        from platform_mac.quickmachotkey_hotkeys import QuickMachHotkeyController
    else:
        from platform_mac.carbon_hotkeys import CarbonHotkeyController

    port = int(os.environ.get("VOICE_DICTATION_PORT", "8000"))
    username = _resolve_username()
    if not username:
        _LOG.error(
            "No hotkey agent user: set VOICE_DICTATION_AI_FRAME_USER, or save a dictation "
            "hotkey in Preferences while logged in (writes ai-frame/users/.hotkey_agent_target_username), "
            "or use a single local account."
        )
        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H1",
            location="platform_mac/hotkey_agent.py:main:no-user",
            message="aborted before event loop",
            data={"pid": os.getpid(), "reason": "no_username"},
        )
        # endregion
        sys.exit(1)
    # region agent log
    _debug_emit(
        run_id=run_id,
        hypothesis_id="H1",
        location="platform_mac/hotkey_agent.py:main:username",
        message="resolved username",
        data={"username": username},
    )
    # endregion

    base_url = f"http://127.0.0.1:{port}"
    toggle_url = f"{base_url}/api/dictation/hotkey/toggle"
    cancel_url = f"{base_url}/api/dictation/hotkey/cancel"

    last_applied_mtime: float | None = None
    reload_requested = threading.Event()

    def _start_ping_server() -> None:
        """Loopback health + control endpoints for hotkey sidecar."""
        try:
            ping_port = int(
                os.environ.get(
                    "VOICE_DICTATION_HOTKEY_PING_PORT", str(_DEFAULT_HOTKEY_PING_PORT)
                )
            )
        except ValueError:
            ping_port = _DEFAULT_HOTKEY_PING_PORT
        bind_host = "127.0.0.1"
        user_ref = username

        class _HealthHandler(BaseHTTPRequestHandler):
            def log_message(self, _fmt: str, *_args: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                path = (self.path or "").split("?", 1)[0].rstrip("/") or "/"
                if path not in ("/", "/health"):
                    self.send_error(404)
                    return
                body = json.dumps({"ok": True, "username": user_ref}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802
                path = (self.path or "").split("?", 1)[0].rstrip("/") or "/"
                if path != "/hotkeys/reload":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                payload = {}
                if length > 0:
                    try:
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    except Exception:
                        payload = {}
                req_user = (
                    payload.get("username", "").strip()
                    if isinstance(payload, dict)
                    else ""
                )
                if req_user and req_user != user_ref:
                    body = json.dumps(
                        {"ok": False, "reloaded": False, "reason": "wrong_user", "username": user_ref}
                    ).encode("utf-8")
                    self.send_response(409)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                reload_requested.set()
                _LOG.info("Hotkey sidecar reload requested via HTTP (username=%r)", req_user or None)
                body = json.dumps({"ok": True, "reloaded": True, "username": user_ref}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            httpd = ThreadingHTTPServer((bind_host, ping_port), _HealthHandler)
        except OSError as e:
            _LOG.warning("Hotkey sidecar HTTP server could not bind %s:%s (%s).", bind_host, ping_port, e)
            return

        threading.Thread(
            target=httpd.serve_forever,
            name="hotkey-ping-http",
            daemon=True,
        ).start()
        _LOG.info(
            "Hotkey sidecar HTTP: GET http://%s:%s/health, POST /hotkeys/reload",
            bind_host,
            ping_port,
        )

    def _post_toggle() -> None:
        _LOG.info("Hotkey toggle: HTTP thread started for user=%r", username)
        _, _, sec, _ = _load_user_chords_and_secret(username)
        if not sec:
            _LOG.warning("toggle: missing hotkey_local_secret.txt")
            return
        try:
            with httpx.Client(timeout=120.0) as client:
                _LOG.info("Hotkey toggle: POST %s", toggle_url)
                r = client.post(
                    toggle_url,
                    headers={"X-Voice-Dictation-Secret": sec},
                    json={"username": username},
                )
            # region agent log
            _debug_emit(
                run_id=run_id,
                hypothesis_id="H3",
                location="platform_mac/hotkey_agent.py:_post_toggle",
                message="toggle HTTP response",
                data={"status": r.status_code},
            )
            # endregion
            if r.status_code >= 400:
                msg = r.text[:500] if r.text else ""
                if r.status_code == 403:
                    _LOG.warning(
                        "toggle HTTP 403 (wrong secret or hotkey user mismatch). "
                        "Agent user=%r must match the account that saved hotkeys / hotkey_local_secret.txt. %s",
                        username,
                        msg,
                    )
                else:
                    _LOG.warning("toggle HTTP %s: %s", r.status_code, msg)
            else:
                _LOG.info("toggle finished: HTTP %s", r.status_code)
        except Exception:
            _LOG.exception("toggle request failed")

    def _post_cancel() -> None:
        _LOG.info("Hotkey cancel: HTTP thread started")
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.post(cancel_url)
            if r.status_code >= 400:
                _LOG.warning("cancel HTTP %s: %s", r.status_code, r.text[:200])
        except Exception:
            _LOG.exception("cancel request failed")

    def _fire_toggle() -> None:
        _LOG.info("Global hotkey matched: toggle chord (starting request thread)")
        print("[HOTKEY] toggle detected", flush=True)
        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H2",
            location="platform_mac/hotkey_agent.py:_fire_toggle",
            message="hotkey callback reached toggle bridge",
            data={"thread": threading.current_thread().name},
        )
        # endregion
        threading.Thread(target=_post_toggle, daemon=True).start()

    def _fire_cancel() -> None:
        _LOG.info("Global hotkey matched: cancel chord (starting request thread)")
        print("[HOTKEY] cancel detected", flush=True)
        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H2",
            location="platform_mac/hotkey_agent.py:_fire_cancel",
            message="hotkey callback reached cancel bridge",
            data={"thread": threading.current_thread().name},
        )
        # endregion
        threading.Thread(target=_post_cancel, daemon=True).start()

    settings_path = _users_dir() / username / "settings.json"
    secret_path = _users_dir() / username / "hotkey_local_secret.txt"
    _LOG.info(
        "Voice dictation hotkey agent (user=%r, port=%s, base=%s, backend=Carbon)",
        username,
        port,
        base_url,
    )
    # region agent log
    _debug_emit(
        run_id=run_id,
        hypothesis_id="H1",
        location="platform_mac/hotkey_agent.py:main:startup",
        message="resolved endpoints",
        data={"port": port, "toggle_url": toggle_url, "cancel_url": cancel_url},
    )
    # endregion
    _LOG.info("Using settings: %s", settings_path)
    _LOG.info("Secret file: %s (exists=%s)", secret_path, secret_path.exists())

    if use_quick:
        carbon = QuickMachHotkeyController()
    else:
        carbon = CarbonHotkeyController()
    try:
        carbon.initialize()
    except Exception:
        _LOG.exception("Carbon hotkey controller failed to initialize")
        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H1",
            location="platform_mac/hotkey_agent.py:main:init-failed",
            message="carbon initialize failed",
            data={"pid": os.getpid()},
        )
        # endregion
        sys.exit(1)

    _start_ping_server()

    def _noop() -> None:
        return None

    last_fallback_poll_at = 0.0
    loop_counter = 0

    def _apply_hotkeys_once() -> None:
        toggle_c, cancel_c, secret, mtime = _load_user_chords_and_secret(username)
        can_bind = bool(secret) and (bool(toggle_c) or bool(cancel_c))
        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H4",
            location="platform_mac/hotkey_agent.py:main:rebind",
            message="rebind decision",
            data={
                "can_bind": can_bind,
                "has_toggle": bool(toggle_c),
                "has_cancel": bool(cancel_c),
                "has_secret": bool(secret),
                "mtime": mtime,
            },
        )
        # endregion
        if can_bind:
            _LOG.info(
                "Applying %s global hotkeys (toggle=%s cancel=%s)",
                "QuickMachHotkey" if use_quick else "Carbon",
                toggle_c is not None,
                cancel_c is not None,
            )
            carbon.set_hotkeys(
                toggle_chord=toggle_c,
                cancel_chord=cancel_c,
                on_toggle=_fire_toggle,
                on_cancel=_fire_cancel,
            )
        else:
            _LOG.info("Clearing %s hotkeys (missing secret or no chords configured)", "QuickMachHotkey" if use_quick else "Carbon")
            carbon.set_hotkeys(
                toggle_chord=None,
                cancel_chord=None,
                on_toggle=_noop,
                on_cancel=_noop,
            )
        return mtime

    if use_quick:
        from PyObjCTools import AppHelper as _AppHelper

        _quick_poll_sec = 0.05
        last_applied_mtime = _apply_hotkeys_once()
        _LOG.info(
            "QuickMachHotkey mode: live reload (POST /hotkeys/reload + periodic settings check)."
        )
        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H1",
            location="platform_mac/hotkey_agent.py:main:quickmachotkey",
            message="quickmachotkey enabled",
            data={"env_value": quick_flag},
        )
        # endregion

        def _quick_poll_tick() -> None:
            nonlocal last_applied_mtime, last_fallback_poll_at
            now = time.time()
            fallback_due = (now - last_fallback_poll_at) >= _HOTKEY_SETTINGS_POLL_FALLBACK_SEC
            if fallback_due:
                last_fallback_poll_at = now
            need_refresh = (
                reload_requested.is_set()
                or fallback_due
                or last_applied_mtime is None
            )
            if reload_requested.is_set():
                reload_requested.clear()
            if need_refresh:
                last_applied_mtime = _apply_hotkeys_once()
            _AppHelper.callLater(_quick_poll_sec, _quick_poll_tick)

        # region agent log
        _debug_emit(
            run_id=run_id,
            hypothesis_id="H1",
            location="platform_mac/hotkey_agent.py:main:quickmachotkey",
            message="entering AppHelper.runEventLoop",
            data={},
        )
        # endregion
        _AppHelper.callAfter(_quick_poll_tick)
        carbon.run_event_loop()
        return

    while True:
        # Pump Carbon events on this thread (embedded runtime runs in its own thread).
        carbon.pump_events(0.05)
        loop_counter += 1
        if loop_counter % 40 == 0:
            # region agent log
            _debug_emit(
                run_id=run_id,
                hypothesis_id="H1",
                location="platform_mac/hotkey_agent.py:main:loop",
                message="loop heartbeat",
                data={
                    "loop_counter": loop_counter,
                    "thread": threading.current_thread().name,
                    "reload_requested": reload_requested.is_set(),
                    "last_applied_mtime": last_applied_mtime,
                },
            )
            # endregion
        now = time.time()
        fallback_due = (now - last_fallback_poll_at) >= _HOTKEY_SETTINGS_POLL_FALLBACK_SEC
        need_refresh = reload_requested.is_set() or fallback_due or last_applied_mtime is None
        if fallback_due:
            last_fallback_poll_at = now
        if reload_requested.is_set():
            reload_requested.clear()
        if need_refresh:
            mtime = _apply_hotkeys_once()
            last_applied_mtime = mtime


if __name__ == "__main__":
    main()
