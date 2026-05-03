"""Cross-platform dictation hotkey chord: JSON shape, validation, display labels.

OS-specific bindings (quickmachotkey, pynput, etc.) live under platform_*; this module stays framework-free.
"""
from __future__ import annotations

import re
from typing import Any, Final

ALLOWED_MODIFIERS: Final[frozenset[str]] = frozenset({"cmd", "ctrl", "alt", "shift"})

# Logical non-modifier keys: one ASCII letter/digit or a short name (browser / agent agreed).
_KEY_SINGLE_RE = re.compile(r"^[a-z0-9]$")
_KEY_NAMED_RE = re.compile(r"^[a-z][a-z0-9_-]{0,24}$")


def normalize_chord(data: Any) -> dict[str, Any] | None:
    """Return a normalized chord dict or None if ``data`` is None (cleared)."""
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("Hotkey chord must be a JSON object or null")
    raw_mods = data.get("modifiers")
    if not isinstance(raw_mods, list):
        raise ValueError("Hotkey chord.modifiers must be a list")
    mods: list[str] = []
    for m in raw_mods:
        if not isinstance(m, str):
            raise ValueError("Each modifier must be a string")
        ml = m.strip().lower()
        if ml not in ALLOWED_MODIFIERS:
            raise ValueError(f"Unknown modifier: {m!r} (use cmd, ctrl, alt, shift)")
        if ml not in mods:
            mods.append(ml)
    if not mods:
        raise ValueError("Hotkey chord requires at least one modifier")
    key = data.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("Hotkey chord.key must be a non-empty string")
    key_norm = key.strip().lower()
    if not (_KEY_SINGLE_RE.match(key_norm) or _KEY_NAMED_RE.match(key_norm)):
        raise ValueError(
            "Hotkey chord.key must be a single letter/digit or a lowercase name "
            "(e.g. escape, space, comma)"
        )
    _order = {"alt": 0, "cmd": 1, "ctrl": 2, "shift": 3}
    mods.sort(key=lambda x: _order[x])
    return {"modifiers": mods, "key": key_norm}


def parse_chord_or_raise(data: Any) -> dict[str, Any] | None:
    """Validate chord JSON; raises ValueError on bad input."""
    return normalize_chord(data)


def format_chord_display(chord: dict[str, Any] | None) -> str:
    """Human-readable label for Preferences (macOS Option maps to alt in storage)."""
    if not chord:
        return ""
    try:
        c = normalize_chord(chord)
    except ValueError:
        return "(invalid hotkey)"
    if c is None:
        return ""
    labels = {"cmd": "Cmd", "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift"}
    parts = [labels[m] for m in c["modifiers"]]
    k = c["key"]
    if len(k) == 1:
        parts.append(k.upper() if k.isalpha() else k)
    else:
        parts.append(k.replace("_", " ").title())
    return "+".join(parts)
