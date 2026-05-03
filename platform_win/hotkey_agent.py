"""
Windows global dictation hotkeys: pynput ``GlobalHotKeys`` + httpx to local FastAPI.

Env:
  VOICE_DICTATION_PORT — default 8000 (twim URL for toggle/cancel POST)
  VOICE_DICTATION_TWIM_USER — username under twim/users/ (legacy: VOICE_DICTATION_AI_FRAME_USER)
  VOICE_DICTATION_HOTKEY_PING_PORT — loopback HTTP ``/health`` (default 18447)
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

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.hotkey_chord import normalize_chord
from hotkey_rebind_schedule import schedule_hotkey_rebind_from_http_thread

_LOG = logging.getLogger("hotkey_agent")


def _users_dir() -> Path:
    return ROOT / "twim" / "users"


def _resolve_username() -> str:
    env_u = (
        os.environ.get("VOICE_DICTATION_TWIM_USER")
        or os.environ.get("VOICE_DICTATION_AI_FRAME_USER")
        or ""
    ).strip()
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
    if sys.platform != "win32":
        _LOG.error("platform_win.hotkey_agent is only for Windows (got %s).", sys.platform)
        sys.exit(1)

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

    port = int(os.environ.get("VOICE_DICTATION_PORT", "8000"))
    username = _resolve_username()
    if not username:
        _LOG.error(
            "No hotkey agent user: set VOICE_DICTATION_TWIM_USER (or legacy VOICE_DICTATION_AI_FRAME_USER), "
            "or save a dictation hotkey in Preferences while logged in (writes twim/users/.hotkey_agent_target_username)."
        )
        sys.exit(1)

    base_url = f"http://127.0.0.1:{port}"
    toggle_url = f"{base_url}/api/dictation/hotkey/toggle"
    cancel_url = f"{base_url}/api/dictation/hotkey/cancel"

    def _start_ping_server() -> None:
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
                payload: dict[str, Any] = {}
                if length > 0:
                    try:
                        raw = json.loads(self.rfile.read(length).decode("utf-8"))
                        if isinstance(raw, dict):
                            payload = raw
                    except Exception:
                        payload = {}
                req_user = (payload.get("username") or "").strip() if isinstance(payload, dict) else ""
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
                schedule_hotkey_rebind_from_http_thread(_apply_hotkeys_once)
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
            t0 = time.time()
            with httpx.Client(timeout=120.0) as client:
                _LOG.info("Hotkey toggle: POST %s", toggle_url)
                r = client.post(
                    toggle_url,
                    headers={"X-Voice-Dictation-Secret": sec},
                    json={"username": username},
                )
            _LOG.info(
                "toggle finished: HTTP %s (elapsed_ms=%s)",
                r.status_code,
                int((time.time() - t0) * 1000),
            )
            if r.status_code >= 400:
                msg = r.text[:500] if r.text else ""
                _LOG.warning("toggle HTTP %s: %s", r.status_code, msg)
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
        threading.Thread(target=_post_toggle, daemon=True).start()

    def _fire_cancel() -> None:
        _LOG.info("Global hotkey matched: cancel chord (starting request thread)")
        print("[HOTKEY] cancel detected", flush=True)
        threading.Thread(target=_post_cancel, daemon=True).start()

    settings_path = _users_dir() / username / "settings.json"
    secret_path = _users_dir() / username / "hotkey_local_secret.txt"
    _LOG.info(
        "Voice dictation hotkey agent (user=%r, port=%s, base=%s, backend=Pynput)",
        username,
        port,
        base_url,
    )
    _LOG.info("Using settings: %s", settings_path)
    _LOG.info("Secret file: %s (exists=%s)", secret_path, secret_path.exists())

    from platform_win.pynput_hotkeys import PynputHotkeyController

    ctrl = PynputHotkeyController()
    try:
        ctrl.initialize()
    except Exception:
        _LOG.exception("Pynput hotkey controller failed to initialize")
        sys.exit(1)

    def _noop() -> None:
        return None

    def _apply_hotkeys_once() -> None:
        toggle_c, cancel_c, secret, _mtime = _load_user_chords_and_secret(username)
        can_bind = bool(secret) and (bool(toggle_c) or bool(cancel_c))
        if can_bind:
            _LOG.info(
                "Applying Pynput global hotkeys (toggle=%s cancel=%s)",
                toggle_c is not None,
                cancel_c is not None,
            )
            ctrl.set_hotkeys(
                toggle_chord=toggle_c,
                cancel_chord=cancel_c,
                on_toggle=_fire_toggle,
                on_cancel=_fire_cancel,
            )
        else:
            _LOG.info("Clearing Pynput hotkeys (missing secret or no chords configured)")
            ctrl.set_hotkeys(
                toggle_chord=None,
                cancel_chord=None,
                on_toggle=_noop,
                on_cancel=_noop,
            )

    _start_ping_server()

    _apply_hotkeys_once()
    _LOG.info("Pynput mode: loopback reload (POST /hotkeys/reload); main thread blocks on listener.")

    def _shutdown(_signum: int, _frame: Any) -> None:
        _LOG.info("Signal %s: exiting hotkey agent", _signum)
        sys.exit(0)

    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    ctrl.run_event_loop()


if __name__ == "__main__":
    main()
