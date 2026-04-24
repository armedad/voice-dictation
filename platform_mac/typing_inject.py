from __future__ import annotations

from pynput.keyboard import Controller


class TypingInjectionError(RuntimeError):
    """Strict path: no paste fallback (see MVP scope)."""


def type_text_strict(text: str) -> None:
    """
    Synthetic typing at the current focus. Requires Accessibility (and often
    Input Monitoring) for the Python process.

    Note: complex Unicode/IME may be imperfect with pynput alone; scope allows
    tightening with pyobjc later.
    """
    if not text:
        return
    try:
        kb = Controller()
        kb.type(text)
    except Exception as e:
        raise TypingInjectionError(
            "Synthetic typing failed (strict mode — no paste fallback). "
            "Try another app or field; grant Accessibility to this app."
        ) from e
