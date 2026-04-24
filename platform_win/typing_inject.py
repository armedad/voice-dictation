from __future__ import annotations


class TypingInjectionError(RuntimeError):
    pass


def type_text_strict(text: str) -> None:
    raise NotImplementedError("Windows SendInput typing not implemented yet.")
