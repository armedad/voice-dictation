from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_USERS_DIR = _ROOT / "twim" / "users"
_LOGS_DIR = _ROOT / "twim" / "logs"

_DEFAULT_FLAGS: dict[str, bool] = {
    "AUTH": True,
    "API": False,
    "CHAT": True,
    "SETTINGS": False,
    "MODELS": False,
    "NOTIFICATIONS": True,
    "APP": False,
    "DICTATION": False,
    "CONTEXT": False,
    "PROFILE": False,
    "SPEECH": False,
}


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _write_to_daily_log(level: str, message: str, data: dict[str, Any] | None = None) -> None:
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.now().strftime("%Y%m%d")
        log_file = _LOGS_DIR / f"twim_{day}.log"
        suffix = f" | {data}" if data else ""
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{_now_ts()}] [{level}] {message}{suffix}\n")
    except OSError:
        pass


def _normalize_flags(raw: Any) -> dict[str, bool]:
    out = dict(_DEFAULT_FLAGS)
    if not isinstance(raw, dict):
        return out
    for key in _DEFAULT_FLAGS:
        if key in raw:
            out[key] = bool(raw[key])
    return out


def _load_user_debug_flags(username: str) -> dict[str, bool]:
    u = (username or "").strip()
    if not u:
        return dict(_DEFAULT_FLAGS)
    settings_file = _USERS_DIR / u / "settings.json"
    if not settings_file.exists():
        return dict(_DEFAULT_FLAGS)
    try:
        raw = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_FLAGS)
    return _normalize_flags(raw.get("debug_flags"))


def is_flag_enabled_for_user(username: str, flag: str) -> bool:
    f = (flag or "").strip().upper()
    if not f:
        return False
    flags = _load_user_debug_flags(username)
    return bool(flags.get(f, False))


def log_debug(
    *,
    username: str | None,
    flag: str,
    level: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    u = (username or "").strip()
    f = (flag or "").strip().upper()
    if not f:
        return
    if not is_flag_enabled_for_user(u, f):
        return
    payload: dict[str, Any] = {"flag": f, "user": u or None}
    if data:
        payload.update(data)
    _write_to_daily_log(f"DEBUG_{(level or 'INFO').upper()}", f"[{f}] {message}", payload)


def log_system(*, level: str, message: str, data: dict[str, Any] | None = None) -> None:
    _write_to_daily_log(f"SYSTEM_{(level or 'INFO').upper()}", message, data)
