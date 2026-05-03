"""
Map JSON hotkey chords to macOS HIToolbox virtual key codes and Carbon-style modifier flags.

Used by quickmachotkey registration (virtual key + separate modifier mask from quickmachotkey).
Modifier bit layout matches Carbon ``Events.h`` (cmd/shift/alt/control).
"""
from __future__ import annotations

from typing import Any

from core.hotkey_chord import parse_chord_or_raise

# Carbon-style modifier masks (Events.h) — same values quickmachotkey expects per modifier token
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
        raise ValueError(f"F-key F{n} not supported in this build")
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
    """Return ``(virtual_key_code, carbon_modifier_flags)`` for macOS hotkey registration."""
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
        raise ValueError(f"Key {k!r} is not supported for global hotkeys yet")
    return vk, mods
