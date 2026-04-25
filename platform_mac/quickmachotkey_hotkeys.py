"""
Quickmachotkey-backed global hotkeys for macOS.

Mirrors the approach in @coding/hotkey/:
- quickHotKey registration
- NSApplication + AppHelper.runEventLoop()
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

from AppKit import NSApplication  # type: ignore[import]
from PyObjCTools import AppHelper  # type: ignore[import]
from quickmachotkey import mask, quickHotKey  # type: ignore[import]
from quickmachotkey.constants import cmdKey, controlKey, optionKey, shiftKey  # type: ignore[import]

from core.hotkey_chord import parse_chord_or_raise
from platform_mac.carbon_hotkeys import chord_to_carbon_vk_and_modifiers

_DEBUG_LOG_PATH = "/Users/chee/zapier ai project/.cursor/debug-55f014.log"
_DEBUG_SESSION_ID = "55f014"


def _debug_emit(location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    payload = {
        "sessionId": _DEBUG_SESSION_ID,
        "runId": f"quickmachotkey-{int(time.time())}",
        "hypothesisId": "H6",
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


class QuickMachHotkeyController:
    """Register hotkeys via quickmachotkey and run AppHelper event loop."""

    def __init__(self) -> None:
        self._handlers: list[Callable[[], None]] = []
        self._current_keys: tuple[dict[str, Any] | None, dict[str, Any] | None] | None = None

    def initialize(self) -> None:
        NSApplication.sharedApplication()
        # region agent log
        _debug_emit(
            "platform_mac/quickmachotkey_hotkeys.py:initialize",
            "initialized",
            {
                "thread": threading.current_thread().name,
                "is_main_thread": threading.current_thread() is threading.main_thread(),
            },
        )
        # endregion

    def run_event_loop(self) -> None:
        AppHelper.runEventLoop()

    def set_hotkeys(
        self,
        *,
        toggle_chord: dict[str, Any] | None,
        cancel_chord: dict[str, Any] | None,
        on_toggle: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        if self._current_keys is not None:
            if self._current_keys == (toggle_chord, cancel_chord):
                return
            # quickmachotkey does not expose unregistration; avoid duplicating bindings.
            _debug_emit(
                "platform_mac/quickmachotkey_hotkeys.py:set_hotkeys",
                "rebind skipped (restart required)",
                {"reason": "no_unregister", "toggle_changed": True, "cancel_changed": True},
            )
            return
        self._current_keys = (toggle_chord, cancel_chord)
        self._register_one(toggle_chord, on_toggle, "toggle")
        self._register_one(cancel_chord, on_cancel, "cancel")

    def _register_one(
        self,
        chord: dict[str, Any] | None,
        cb: Callable[[], None],
        label: str,
    ) -> None:
        if chord is None:
            return
        parsed = parse_chord_or_raise(chord)
        if parsed is None:
            return
        vk, _mods = chord_to_carbon_vk_and_modifiers(chord)
        mods: list[int] = []
        for m in parsed["modifiers"]:
            if m == "cmd":
                mods.append(cmdKey)
            elif m == "shift":
                mods.append(shiftKey)
            elif m == "alt":
                mods.append(optionKey)
            elif m == "ctrl":
                mods.append(controlKey)
        mod_mask = mask(*mods) if mods else 0

        def _handler() -> None:
            _debug_emit(
                "platform_mac/quickmachotkey_hotkeys.py:_handler",
                "hotkey event received",
                {"label": label, "thread": threading.current_thread().name},
            )
            cb()

        decorated = quickHotKey(virtualKey=vk, modifierMask=mod_mask, immediately=True)(_handler)
        self._handlers.append(decorated)
        _debug_emit(
            "platform_mac/quickmachotkey_hotkeys.py:_register_one",
            "register ok",
            {"label": label, "vk": vk, "mods": mod_mask},
        )
