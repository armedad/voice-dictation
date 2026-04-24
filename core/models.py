from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AdapterEndpoint(BaseModel):
    """One configurable LLM/STT endpoint (transcription or cleanup)."""

    model_config = ConfigDict(populate_by_name=True)

    provider: str = Field(
        ...,
        description="Adapter id, e.g. faster_whisper, openai_compatible_audio, ollama_chat",
    )
    baseURL: str = Field(
        default="",
        description="Base URL for HTTP adapters; empty for faster_whisper",
    )
    # JSON key "model" — avoid Python attr `model` (reserved on BaseModel in Pydantic v2).
    model_name: str = Field(..., alias="model")
    apiKeyKeychainAccount: Optional[str] = None
    systemPromptRef: Optional[str] = Field(
        default=None, description="Optional cleanup system prompt ref"
    )


class VoiceDictationConfig(BaseModel):
    schemaVersion: Literal[1] = 1
    transcription: AdapterEndpoint
    cleanup: AdapterEndpoint


DEFAULT_CLEANUP_SYSTEM_PROMPT = (
    "You rewrite spoken dictation into clear written text. Capture the user's intent, "
    "not their literal words: tighten phrasing, remove filler and false starts, and "
    "keep the substance. Preserve important names, numbers, and technical terms when "
    "they matter. Output plain text only: no quotes, no markdown, no preamble or commentary."
)


MAX_VOCABULARY_LINES = 150


def parse_vocabulary_lines(raw: Optional[str]) -> list[str]:
    """Non-empty trimmed lines from a newline-separated vocabulary field."""
    if not raw or not str(raw).strip():
        return []
    out: list[str] = []
    for line in str(raw).splitlines():
        t = line.strip()
        if t:
            out.append(t)
        if len(out) >= MAX_VOCABULARY_LINES:
            break
    return out


def format_vocabulary_for_whisper_initial_prompt(raw: Optional[str]) -> Optional[str]:
    """
    Compact string for faster-whisper ``initial_prompt`` (weak STT bias, not guaranteed).

    Whisper-style models treat this as soft context; keep length bounded.
    """
    lines = parse_vocabulary_lines(raw)
    if not lines:
        return None
    joined = ", ".join(lines)
    max_chars = 1800
    if len(joined) > max_chars:
        joined = joined[:max_chars].rsplit(", ", 1)[0]
    return f"Terms that may appear: {joined}."


def build_dictation_cleanup_system_prompt(
    user_instructions: Optional[str],
    vocabulary: Optional[str] = None,
) -> str:
    """
    Merge default cleanup behavior with optional vocabulary list and user style constraints.

    Vocabulary is applied in the LLM pass (strong): prefer these spellings when they match
    what was said. For local faster-whisper, the same list can also be passed as
    ``initial_prompt`` (weak STT hint) from the caller.
    """
    base = DEFAULT_CLEANUP_SYSTEM_PROMPT.strip()
    parts: list[str] = [base]
    voc_lines = parse_vocabulary_lines(vocabulary)
    if voc_lines:
        bullets = "\n".join(f"- {line}" for line in voc_lines)
        parts.append(
            "Preferred vocabulary (when the transcript clearly refers to these, use this "
            "spelling or form exactly; do not add names or terms that are not supported by "
            "what was said):\n"
            + bullets
        )
    extra = (user_instructions or "").strip()
    if extra:
        parts.append(f"User preferences (follow these when rewriting):\n{extra}")
    return "\n\n".join(parts)
