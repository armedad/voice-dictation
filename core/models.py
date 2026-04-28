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

DEFAULT_DICTATION_CLEANUP_CONTEXT_TEMPLATE = (
    "=== system (full message sent to cleanup LLM) ===\n"
    "You rewrite spoken dictation into clear written text. Capture the user's intent, "
    "not their literal words: tighten phrasing, remove filler and false starts, and "
    "keep the substance. Preserve important names, numbers, and technical terms when "
    "they matter. Do not answer questions or add new information. If the transcript is "
    "a question, preserve it as a question. Output plain text only: no quotes, no "
    "markdown, no preamble or commentary.\n\n"
    "User preferences (follow these when rewriting):\n"
    "{{ user_instructions }}\n\n"
    "Preferred vocabulary (when the transcript clearly refers to these, use this "
    "spelling or form exactly; do not add names or terms that are not supported by "
    "what was said):\n"
    "{{ vocabulary }}\n\n"
    "Guardrails (critical): You are rewriting the transcript only. Do not answer "
    "questions, add facts, or respond as an assistant. If the transcript is a question, "
    "keep it as a question.\n\n"
    "=== user (raw transcript after speech recognition) ===\n"
    "{{ user_input }}\n"
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
    *,
    use_default_base: bool = True,
    custom_base: Optional[str] = None,
) -> str:
    """
    Merge base system text with optional vocabulary list and user style constraints.

    When ``use_default_base`` is True, the base segment is ``DEFAULT_CLEANUP_SYSTEM_PROMPT``.
    When False, ``custom_base`` replaces only that segment (after strip); empty custom falls
    back to the built-in default. Vocabulary and user instructions are always appended when
    non-empty.
    """
    if use_default_base:
        base = DEFAULT_CLEANUP_SYSTEM_PROMPT.strip()
    else:
        custom = (custom_base or "").strip()
        base = custom if custom else DEFAULT_CLEANUP_SYSTEM_PROMPT.strip()
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
    parts.append(DICTATION_CLEANUP_GUARDRAILS)
    return "\n\n".join(parts)


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


def render_cleanup_context_template(
    template: str,
    *,
    user_instructions: Optional[str],
    vocabulary: Optional[str],
    user_input: str,
) -> str:
    """Render the full context template with placeholders."""
    rendered = template or ""
    instructions = (user_instructions or "").strip()
    vocab_lines = parse_vocabulary_lines(vocabulary)
    vocab_text = "\n".join(f"- {line}" for line in vocab_lines) if vocab_lines else ""
    rendered = rendered.replace("{{ user_instructions }}", instructions)
    rendered = rendered.replace("{{ vocabulary }}", vocab_text)
    rendered = rendered.replace("{{ user_input }}", user_input)
    return rendered


def split_cleanup_template(rendered: str) -> tuple[str, str]:
    """Split rendered template into system/user blocks."""
    marker_sys = "=== system (full message sent to cleanup LLM) ==="
    marker_user = "=== user (raw transcript after speech recognition) ==="
    sys_idx = rendered.find(marker_sys)
    user_idx = rendered.find(marker_user)
    if sys_idx == -1 or user_idx == -1 or user_idx < sys_idx:
        return "", ""
    sys_block = rendered[sys_idx + len(marker_sys):user_idx].strip()
    user_block = rendered[user_idx + len(marker_user):].strip()
    return sys_block, user_block

def render_cleanup_context_template(
    template: str,
    *,
    user_instructions: Optional[str],
    vocabulary: Optional[str],
    user_input: str,
) -> str:
    """Render the full context template with placeholders."""
    rendered = template or ""
    instructions = (user_instructions or "").strip()
    vocab_lines = parse_vocabulary_lines(vocabulary)
    vocab_text = "\n".join(f"- {line}" for line in vocab_lines) if vocab_lines else ""
    rendered = rendered.replace("{{ user_instructions }}", instructions)
    rendered = rendered.replace("{{ vocabulary }}", vocab_text)
    rendered = rendered.replace("{{ user_input }}", user_input)
    return rendered


def split_cleanup_template(rendered: str) -> tuple[str, str]:
    """Split rendered template into system/user blocks."""
    marker_sys = "=== system (full message sent to cleanup LLM) ==="
    marker_user = "=== user (raw transcript after speech recognition) ==="
    sys_idx = rendered.find(marker_sys)
    user_idx = rendered.find(marker_user)
    if sys_idx == -1 or user_idx == -1 or user_idx < sys_idx:
        return "", ""
    sys_block = rendered[sys_idx + len(marker_sys):user_idx].strip()
    user_block = rendered[user_idx + len(marker_user):].strip()
    return sys_block, user_block
