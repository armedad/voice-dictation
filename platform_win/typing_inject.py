from __future__ import annotations

from pynput.keyboard import Controller


class TypingInjectionError(RuntimeError):
    """Strict path: no paste fallback (see MVP scope)."""


def type_text_strict(text: str) -> None:
    """
    Synthetic typing at the current focus (pynput).

    Complex Unicode / IME may be imperfect; scope allows tightening later.
    """
    if not text:
        return
    try:
        kb = Controller()
        kb.type(text)
    except Exception as e:
        raise TypingInjectionError(
            "Synthetic typing failed (strict mode — no paste fallback). "
            "Try another app or field; ensure this process is allowed to send input."
        ) from e
