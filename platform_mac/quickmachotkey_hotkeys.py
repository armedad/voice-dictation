"""
Quickmachotkey-backed global hotkeys for macOS.

Mirrors the approach in @coding/hotkey/:
- quickHotKey registration
- NSApplication + AppHelper.runEventLoop()
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from AppKit import NSApplication  # type: ignore[import]
from PyObjCTools import AppHelper  # type: ignore[import]
from quickmachotkey import mask, quickHotKey  # type: ignore[import]
from quickmachotkey.constants import cmdKey, controlKey, optionKey, shiftKey  # type: ignore[import]

from core.hotkey_chord import parse_chord_or_raise
from core.debug_flags_logging import log_debug
from platform_mac.chord_vk import chord_to_carbon_vk_and_modifiers

def _debug_emit(location: str, message: str, data: dict[str, Any]) -> None:
    log_debug(
        username=None,
        flag="DICTATION",
        level="INFO",
        message=message,
        data={"location": location, **data},
    )


class QuickMachHotkeyController:
    """Register hotkeys via quickmachotkey and run AppHelper event loop."""

    def __init__(self) -> None:
        # Registerable objects from quickHotKey(...)(handler); each has unregister()/register().
        self._handlers: list[Any] = []
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
        # ``runEventLoop(installInterrupt=True)`` only calls ``installMachInterrupt()`` when
        # ``NSApp()`` is still None. ``initialize()`` already created ``NSApplication``, so
        # install explicitly—otherwise Ctrl+C never gets the Mach → CFRunLoop path.
        AppHelper.installMachInterrupt()
        # installInterrupt=True: keep PyObjC’s full path when NSApp is created inside runEventLoop.
        AppHelper.runEventLoop(installInterrupt=True)

    def set_hotkeys(
        self,
        *,
        toggle_chord: dict[str, Any] | None,
        cancel_chord: dict[str, Any] | None,
        on_toggle: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        if self._current_keys == (toggle_chord, cancel_chord):
            return

        for h in self._handlers:
            unreg = getattr(h, "unregister", None)
            if callable(unreg):
                try:
                    unreg()
                except Exception:
                    _debug_emit(
                        "platform_mac/quickmachotkey_hotkeys.py:set_hotkeys",
                        "unregister failed",
                        {"handler": repr(h)},
                    )
        self._handlers.clear()

        self._current_keys = (toggle_chord, cancel_chord)
        used: set[tuple[int, int]] = set()
        self._register_one(toggle_chord, on_toggle, "toggle", used)
        self._register_one(cancel_chord, on_cancel, "cancel", used)

    def _register_one(
        self,
        chord: dict[str, Any] | None,
        cb: Callable[[], None],
        label: str,
        used: set[tuple[int, int]],
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
        key = (int(vk), int(mod_mask))
        if key in used:
            _debug_emit(
                "platform_mac/quickmachotkey_hotkeys.py:_register_one",
                "duplicate vk+modifiers skipped",
                {"label": label, "vk": vk, "mods": mod_mask},
            )
            return
        used.add(key)

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
