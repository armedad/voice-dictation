"""Global hotkeys on Windows via pynput ``GlobalHotKeys`` (same chord JSON as macOS)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from pynput import keyboard

_LOG = logging.getLogger("hotkey_agent.pynput")


def chord_to_pynput_combo(chord: dict[str, Any]) -> str:
    """
    Map normalized chord ``{"modifiers": [...], "key": "..."}`` to pynput hotkey string.

    See pynput ``GlobalHotKeys`` / ``HotKey`` docs for combo syntax (e.g. ``<ctrl>+r``).
    """
    mods = list(chord.get("modifiers") or [])
    key = (chord.get("key") or "").strip().lower()
    if not key:
        raise ValueError("chord.key is empty")

    order = {"ctrl": 0, "alt": 1, "shift": 2, "cmd": 3}
    mods_sorted = sorted(mods, key=lambda m: order.get(m, 99))

    parts: list[str] = []
    for m in mods_sorted:
        parts.append(f"<{m}>")

    if len(key) == 1 and key.isalnum():
        parts.append(key)
        return "+".join(parts)

    named = {
        "escape": "<esc>",
        "space": "<space>",
        "tab": "<tab>",
        "enter": "<enter>",
        "return": "<enter>",
        "backspace": "<backspace>",
        "delete": "<delete>",
        "insert": "<insert>",
        "home": "<home>",
        "end": "<end>",
        "page_up": "<page_up>",
        "page_down": "<page_down>",
        "up": "<up>",
        "down": "<down>",
        "left": "<left>",
        "right": "<right>",
        "comma": ",",
        "period": ".",
        "slash": "/",
        "minus": "-",
        "equals": "=",
        "grave": "`",
        "semicolon": ";",
        "quote": "'",
        "backslash": "\\",
        "left_bracket": "[",
        "right_bracket": "]",
    }
    if key in named:
        parts.append(named[key])
        return "+".join(parts)

    if key.startswith("f") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 24:
            parts.append(f"<f{n}>")
            return "+".join(parts)

    parts.append(f"<{key}>")
    return "+".join(parts)


class PynputHotkeyController:
    """Register global hotkeys; call ``pump_events`` from main loop for reload checks."""

    def __init__(self) -> None:
        self._listener: keyboard.GlobalHotKeys | None = None
        self._lock = threading.Lock()

    def initialize(self) -> None:
        return None

    def set_hotkeys(
        self,
        *,
        toggle_chord: dict[str, Any] | None,
        cancel_chord: dict[str, Any] | None,
        on_toggle: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        with self._lock:
            if self._listener is not None:
                try:
                    self._listener.stop()
                except Exception:
                    _LOG.exception("stopping previous GlobalHotKeys listener")
                try:
                    self._listener.join(timeout=3.0)
                except Exception:
                    pass
                self._listener = None

            combos: dict[str, Callable[[], None]] = {}
            if toggle_chord is not None:
                try:
                    s = chord_to_pynput_combo(toggle_chord)
                    combos[s] = on_toggle
                    _LOG.info("Pynput register toggle combo %r", s)
                except Exception as e:
                    _LOG.warning("Invalid toggle chord %s: %s", toggle_chord, e)
            if cancel_chord is not None:
                try:
                    s = chord_to_pynput_combo(cancel_chord)
                    if s in combos:
                        _LOG.warning("Cancel chord duplicates toggle; skipping cancel")
                    else:
                        combos[s] = on_cancel
                        _LOG.info("Pynput register cancel combo %r", s)
                except Exception as e:
                    _LOG.warning("Invalid cancel chord %s: %s", cancel_chord, e)

            if not combos:
                _LOG.info("Pynput: no global hotkeys registered (cleared)")
                return

            try:
                self._listener = keyboard.GlobalHotKeys(combos)
                self._listener.start()
            except Exception:
                _LOG.exception("GlobalHotKeys start failed")
                self._listener = None
                raise

    def pump_events(self, timeout_sec: float) -> None:
        time.sleep(max(0.0, float(timeout_sec)))

    def run_event_loop(self) -> None:
        """Block until listener exits (normally never)."""
        if self._listener is not None:
            self._listener.join()
