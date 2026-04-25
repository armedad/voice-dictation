"""
macOS global hotkeys via Carbon ``RegisterEventHotKey`` + one ``InstallEventHandler``.

Only the configured chords are registered with the system; there is no listener that
receives arbitrary key events (unlike ``pynput`` global hooks / CGEvent taps).

Carbon must run on the **same thread** that pumps the process CFRunLoop (the hotkey
agent main thread). Uses ``ctypes`` for Carbon and PyObjC ``CoreFoundation`` for
``CFRunLoopRunInMode`` to process hotkey events between settings polls.

"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
from ctypes import POINTER, Structure, byref, c_uint32, c_ulong, c_void_p
from typing import Any, Callable

from core.hotkey_chord import parse_chord_or_raise

_LOG = logging.getLogger("hotkey_agent.carbon")

# --- Carbon four-char codes (OSType / EventParamName / EventParamType) ---


def _fourcc(code: str) -> int:
    if len(code) != 4:
        raise ValueError("fourcc must be exactly 4 characters")
    return int.from_bytes(code.encode("latin-1"), "big")


kEventClassKeyboard = _fourcc("keyb")
kEventHotKeyPressed = 5
kEventParamDirectObject = _fourcc("----")
typeEventHotKeyID = _fourcc("hkid")

noErr = 0
eventHotKeyExistsErr = -9878

# EventHotKeyID.signature — arbitrary stable tag for our registrations
_HOTKEY_SIG = _fourcc("VDHT")
_TOGGLE_HOTID = 1
_CANCEL_HOTID = 2

# Carbon modifier masks (Events.h)
cmdKey = 1 << 8
shiftKey = 1 << 9
optionKey = 1 << 11
controlKey = 1 << 12

# Virtual key codes (HIToolbox Events.h — physical ANSI layout; letters are NOT A..Z contiguous)
_LETTER_VK: dict[str, int] = {
    "a": 0x00,
    "b": 0x0B,
    "c": 0x08,
    "d": 0x02,
    "e": 0x0E,
    "f": 0x03,
    "g": 0x05,
    "h": 0x04,
    "i": 0x22,
    "j": 0x26,
    "k": 0x28,
    "l": 0x25,
    "m": 0x2E,
    "n": 0x2D,
    "o": 0x1F,
    "p": 0x23,
    "q": 0x0C,
    "r": 0x0F,
    "s": 0x01,
    "t": 0x11,
    "u": 0x20,
    "v": 0x09,
    "w": 0x0D,
    "x": 0x07,
    "y": 0x10,
    "z": 0x06,
}
_VK_ANSI_Equal = 0x18
_VK_ANSI_Minus = 0x1B
_VK_ANSI_LeftBracket = 0x21
_VK_ANSI_RightBracket = 0x1E
_VK_ANSI_Quote = 0x27
_VK_ANSI_Semicolon = 0x29
_VK_ANSI_Backslash = 0x2A
_VK_ANSI_Comma = 0x2B
_VK_ANSI_Slash = 0x2C
_VK_ANSI_Period = 0x2F
_VK_ANSI_Grave = 0x32
_VK_Return = 0x24
_VK_Tab = 0x30
_VK_Space = 0x31
_VK_Delete = 0x33
_VK_Escape = 0x35
_VK_ForwardDelete = 0x75
_VK_LeftArrow = 0x7B
_VK_RightArrow = 0x7C
_VK_DownArrow = 0x7D
_VK_UpArrow = 0x7E
_VK_HOME = 0x73
_VK_PAGEUP = 0x74
_VK_END = 0x77
_VK_PAGEDOWN = 0x79

_NAMED_VK: dict[str, int] = {
    "comma": _VK_ANSI_Comma,
    "period": _VK_ANSI_Period,
    "minus": _VK_ANSI_Minus,
    "equal": _VK_ANSI_Equal,
    "semicolon": _VK_ANSI_Semicolon,
    "quote": _VK_ANSI_Quote,
    "slash": _VK_ANSI_Slash,
    "backslash": _VK_ANSI_Backslash,
    "bracket_left": _VK_ANSI_LeftBracket,
    "bracket_right": _VK_ANSI_RightBracket,
    "backquote": _VK_ANSI_Grave,
    "intl_backslash": _VK_ANSI_Grave,
    "escape": _VK_Escape,
    "space": _VK_Space,
    "tab": _VK_Tab,
    "enter": _VK_Return,
    "return": _VK_Return,
    "backspace": _VK_Delete,
    "delete": _VK_ForwardDelete,
    "up": _VK_UpArrow,
    "down": _VK_DownArrow,
    "left": _VK_LeftArrow,
    "right": _VK_RightArrow,
    "home": _VK_HOME,
    "end": _VK_END,
    "page_up": _VK_PAGEUP,
    "page_down": _VK_PAGEDOWN,
}


def _f_key_vk(name: str) -> int:
    if not name.startswith("f") or not name[1:].isdigit():
        raise ValueError(f"Invalid F-key {name!r}")
    n = int(name[1:])
    if n < 1 or n > 15:
        raise ValueError(f"F-key F{n} not supported for Carbon hotkeys in this build")
    # Physical F-keys are non-contiguous in Events.h
    _explicit = {
        1: 0x7A,
        2: 0x78,
        3: 0x63,
        4: 0x76,
        5: 0x60,
        6: 0x61,
        7: 0x62,
        8: 0x64,
        9: 0x65,
        10: 0x6D,
        11: 0x67,
        12: 0x6F,
        13: 0x69,
        14: 0x6B,
        15: 0x71,
    }
    return _explicit[n]


# ANSI keyboard digit row virtual key codes (not in numeric order on macOS)
_DIGIT_VK: dict[str, int] = {
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "5": 0x17,
    "6": 0x16,
    "7": 0x1A,
    "8": 0x1C,
    "9": 0x19,
    "0": 0x1D,
}


def chord_to_carbon_vk_and_modifiers(chord: dict[str, Any]) -> tuple[int, int]:
    """Return (virtual_key_code, carbon_modifier_flags) for ``RegisterEventHotKey``."""
    c = parse_chord_or_raise(chord)
    if c is None:
        raise ValueError("chord is null")
    mods = 0
    for m in c["modifiers"]:
        if m == "cmd":
            mods |= cmdKey
        elif m == "shift":
            mods |= shiftKey
        elif m == "alt":
            mods |= optionKey
        elif m == "ctrl":
            mods |= controlKey
        else:
            raise ValueError(f"Unknown modifier {m!r}")
    k = c["key"]
    if k == "space":
        vk = _VK_Space
    elif (nv := _NAMED_VK.get(k)) is not None:
        vk = nv
    elif len(k) == 1 and k.isalpha():
        try:
            vk = _LETTER_VK[k.lower()]
        except KeyError as e:
            raise ValueError(f"Letter key {k!r} not supported") from e
    elif len(k) == 1 and k.isdigit():
        try:
            vk = _DIGIT_VK[k]
        except KeyError as e:
            raise ValueError(f"Digit key {k!r} not supported") from e
    elif k.startswith("f") and k[1:].isdigit():
        vk = _f_key_vk(k)
    else:
        raise ValueError(f"Key {k!r} is not supported for Carbon global hotkeys yet")
    return vk, mods


class EventHotKeyID(Structure):
    _fields_ = [("signature", c_uint32), ("id", c_uint32)]


class EventTypeSpec(Structure):
    _fields_ = [("eventClass", c_uint32), ("eventKind", c_uint32)]


_EventHandlerProc = ctypes.CFUNCTYPE(
    ctypes.c_int32,
    c_void_p,
    c_void_p,
    c_void_p,
)


class CarbonHotkeyController:
    """0–2 ``RegisterEventHotKey`` registrations on the thread that calls ``initialize`` / ``pump_events``."""

    def __init__(self) -> None:
        self._carbon = ctypes.CDLL(ctypes.util.find_library("Carbon"))
        self._initialized = False
        self._hotkey_refs: list[c_void_p] = []
        self._handler_ref: c_void_p | None = None
        self._handler_upp: _EventHandlerProc | None = None
        self._callbacks: dict[int, Callable[[], None]] = {}

        self._bind_carbon_prototypes()

    def _bind_carbon_prototypes(self) -> None:
        c = self._carbon
        c.GetApplicationEventTarget.restype = c_void_p
        c.GetApplicationEventTarget.argtypes = []
        c.GetEventDispatcherTarget.restype = c_void_p
        c.GetEventDispatcherTarget.argtypes = []

        c.InstallEventHandler.restype = ctypes.c_int32
        c.InstallEventHandler.argtypes = [
            c_void_p,
            c_void_p,
            c_uint32,
            POINTER(EventTypeSpec),
            c_void_p,
            ctypes.POINTER(c_void_p),
        ]

        c.RemoveEventHandler.restype = ctypes.c_int32
        c.RemoveEventHandler.argtypes = [c_void_p]

        c.RegisterEventHotKey.restype = ctypes.c_int32
        c.RegisterEventHotKey.argtypes = [
            c_uint32,
            c_uint32,
            EventHotKeyID,
            c_void_p,
            c_uint32,
            ctypes.POINTER(c_void_p),
        ]

        c.UnregisterEventHotKey.restype = ctypes.c_int32
        c.UnregisterEventHotKey.argtypes = [c_void_p]

        c.GetEventParameter.restype = ctypes.c_int32
        c.GetEventParameter.argtypes = [
            c_void_p,
            c_uint32,
            c_uint32,
            c_void_p,
            c_ulong,
            ctypes.POINTER(c_ulong),
            c_void_p,
        ]

        c.CallNextEventHandler.restype = ctypes.c_int32
        c.CallNextEventHandler.argtypes = [c_void_p, c_void_p]

    def initialize(self) -> None:
        """Install the Carbon event handler on the **current** thread (call once before ``pump_events``)."""
        if self._initialized:
            return
        self._install_handler_once()
        self._initialized = True
        _LOG.info("Carbon hotkey handler ready on this thread (pump CFRunLoop via pump_events)")

    def start(self) -> None:
        """Backward-compatible alias for ``initialize``."""
        self.initialize()

    def pump_events(self, timeout_sec: float) -> None:
        """Dispatch pending Carbon/Cocoa events (call regularly from the same thread as ``initialize``)."""
        from CoreFoundation import CFRunLoopGetCurrent, CFRunLoopRunInMode, kCFRunLoopDefaultMode

        if timeout_sec <= 0:
            return
        # ReturnAfterSourceHandled=True so hotkey events run without waiting full timeout.
        # PyObjC usually exposes 3 args; some environments still accept the 4-arg C shape.
        try:
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, float(timeout_sec), True)
        except TypeError:
            CFRunLoopRunInMode(CFRunLoopGetCurrent(), kCFRunLoopDefaultMode, float(timeout_sec), True)

    def set_hotkeys(
        self,
        *,
        toggle_chord: dict[str, Any] | None,
        cancel_chord: dict[str, Any] | None,
        on_toggle: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Replace hotkey registrations. Must run on the same thread as ``initialize`` / ``pump_events``."""
        if not self._initialized:
            _LOG.warning("set_hotkeys called before initialize(); hotkeys not applied")
            return
        self._rebind_hotkeys(
            toggle_chord=toggle_chord,
            cancel_chord=cancel_chord,
            on_toggle=on_toggle,
            on_cancel=on_cancel,
        )

    def _install_handler_once(self) -> None:
        if self._handler_ref is not None:
            return

        def _handler(
            next_handler: c_void_p,
            evt: c_void_p,
            _user_data: c_void_p,
        ) -> int:
            hk = EventHotKeyID()
            actual = c_ulong(0)
            err = self._carbon.GetEventParameter(
                evt,
                kEventParamDirectObject,
                typeEventHotKeyID,
                None,
                ctypes.sizeof(hk),
                byref(actual),
                byref(hk),
            )
            if err != noErr:
                return self._carbon.CallNextEventHandler(next_handler, evt)
            if hk.signature != _HOTKEY_SIG:
                return self._carbon.CallNextEventHandler(next_handler, evt)
            cb = self._callbacks.get(int(hk.id))
            if cb:
                _LOG.info("Carbon global hotkey fired id=%s", int(hk.id))
                try:
                    cb()
                except Exception:
                    _LOG.exception("Carbon hotkey callback failed")
                return noErr
            return self._carbon.CallNextEventHandler(next_handler, evt)

        self._handler_upp = _EventHandlerProc(_handler)
        spec = EventTypeSpec(kEventClassKeyboard, kEventHotKeyPressed)
        target = self._carbon.GetEventDispatcherTarget()
        href = c_void_p()
        upp = ctypes.cast(self._handler_upp, c_void_p)
        err = self._carbon.InstallEventHandler(
            target,
            upp,
            1,
            byref(spec),
            None,
            byref(href),
        )
        if err != noErr:
            _LOG.error("InstallEventHandler failed: OSStatus %s", err)
            raise OSError(f"InstallEventHandler failed: {err}")
        self._handler_ref = href
        _LOG.info("Carbon InstallEventHandler installed for kEventHotKeyPressed")

    def _unregister_all_hotkeys(self) -> None:
        for ref in self._hotkey_refs:
            if ref:
                try:
                    self._carbon.UnregisterEventHotKey(ref)
                except Exception:
                    _LOG.debug("UnregisterEventHotKey failed for ref", exc_info=True)
        self._hotkey_refs.clear()

    def _rebind_hotkeys(
        self,
        *,
        toggle_chord: dict[str, Any] | None,
        cancel_chord: dict[str, Any] | None,
        on_toggle: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self._unregister_all_hotkeys()
        self._callbacks.clear()

        target = self._carbon.GetEventDispatcherTarget()
        used: set[tuple[int, int]] = set()

        def _register_one(
            chord: dict[str, Any] | None,
            hid: int,
            cb: Callable[[], None],
            label: str,
        ) -> None:
            if chord is None:
                return
            try:
                vk, mods = chord_to_carbon_vk_and_modifiers(chord)
            except ValueError as e:
                _LOG.warning("%s chord invalid: %s", label, e)
                return
            key = (vk, mods)
            if key in used:
                _LOG.error("%s duplicates another binding %r — skipped.", label, key)
                return
            used.add(key)
            eid = EventHotKeyID(_HOTKEY_SIG, hid)
            href = c_void_p()
            err = self._carbon.RegisterEventHotKey(
                vk,
                mods,
                eid,
                target,
                0,
                byref(href),
            )
            if err == eventHotKeyExistsErr:
                _LOG.warning(
                    "%s RegisterEventHotKey conflict (eventHotKeyExistsErr); "
                    "another app may own this shortcut exclusively.",
                    label,
                )
                return
            if err != noErr:
                _LOG.error("%s RegisterEventHotKey failed OSStatus=%s vk=%#x mods=%#x", label, err, vk, mods)
                return
            self._hotkey_refs.append(href)
            self._callbacks[hid] = cb
            _LOG.info(
                "Carbon RegisterEventHotKey OK %s id=%s vk=%#x mods=%#x",
                label,
                hid,
                vk,
                mods,
            )

        _register_one(toggle_chord, _TOGGLE_HOTID, on_toggle, "toggle")
        _register_one(cancel_chord, _CANCEL_HOTID, on_cancel, "cancel")
