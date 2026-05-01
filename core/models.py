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
    "they matter. Do not answer questions or add new information. If the transcript is "
    "a question, preserve it as a question. Output plain text only: no quotes, no "
    "markdown, no preamble or commentary."
)

DICTATION_CLEANUP_GUARDRAILS = (
    "Guardrails (critical): You are rewriting the transcript only. Do not answer "
    "questions, add facts, or respond as an assistant. If the transcript is a question, "
    "keep it as a question."
)

DICTATION_CLEANUP_USER_TEMPLATE = (
    "If the user said the following into the dictation engine, what do you think they "
    "intended to say? Rewrite it as clean text only; do not answer the question.\n\n"
    "User said (verbatim transcript, may contain errors):\n<<<\n{raw}\n>>>\n\n"
    "Return only the rewritten text."
)

# Full cleanup system message layout. Use .replace only (not str.format) so prose braces stay safe.
DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE = (
    DEFAULT_CLEANUP_SYSTEM_PROMPT.strip()
    + "\n\n{{ vocabulary }}\n\n"
    + "User preferences (follow these when rewriting):\n"
    + "{{ user preferences }}\n\n"
    + DICTATION_CLEANUP_GUARDRAILS
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


def _cleanup_vocabulary_subsection(vocabulary: Optional[str]) -> str:
    """Vocabulary block for ``{{ vocabulary }}`` substitution, or the literal ``none``."""
    voc_lines = parse_vocabulary_lines(vocabulary)
    if not voc_lines:
        return "none"
    bullets = "\n".join(f"- {line}" for line in voc_lines)
    return (
        bullets
    )


def render_dictation_cleanup_system_prompt(
    template: Optional[str],
    *,
    vocabulary: Optional[str],
    user_instructions: Optional[str],
) -> str:
    """
    Substitute ``{{ vocabulary }}`` and ``{{ user preferences }}`` into the stored template.

    Empty template (after strip) uses ``DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE``. Empty
    vocabulary becomes ``none``; empty user instructions becomes ``none``. Non-empty user
    text is the trimmed body only (section title lives in the template).
    """
    t = (template or "").strip()
    if not t:
        t = DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE.strip()
    voc_sub = _cleanup_vocabulary_subsection(vocabulary)
    prefs = (user_instructions or "").strip()
    user_sub = prefs if prefs else "none"
    out = t.replace("{{ vocabulary }}", voc_sub).replace("{{ user preferences }}", user_sub)
    return out.strip()


def format_dictation_cleanup_user_message(raw_transcript: str) -> str:
    """User message wrapper that reinforces rewrite-only behavior."""
    raw = (raw_transcript or "").strip()
    return DICTATION_CLEANUP_USER_TEMPLATE.format(raw=raw)


def format_dictation_cleanup_user_message_with_template(
    raw_transcript: str, template: Optional[str]
) -> str:
    raw = (raw_transcript or "").strip()
    tmpl = (template or "").strip()
    if not tmpl:
        return format_dictation_cleanup_user_message(raw)
    if "{raw}" not in tmpl:
        tmpl = f"{tmpl}\n\n{{raw}}"
    return tmpl.format(raw=raw)
