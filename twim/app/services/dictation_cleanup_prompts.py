"""Build dictation cleanup LLM prompts from Settings (shared by TWIM routes and evals)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.storage import Settings
from core.models import (
    format_dictation_cleanup_user_message_with_template,
    render_dictation_cleanup_system_prompt,
)


@dataclass(frozen=True)
class DictationCleanupPrompts:
    """Rendered system + user messages for one cleanup LLM call."""

    system_prompt: str
    user_prompt_for_transcript: str


def build_dictation_cleanup_prompts(
    settings: Settings,
    raw_transcript: str,
    *,
    vocabulary_override: Optional[str] = None,
    user_instructions_override: Optional[str] = None,
    system_template_override: Optional[str] = None,
    user_template_override: Optional[str] = None,
) -> DictationCleanupPrompts:
    """
    Match TWIM dictation cleanup prompt assembly (Context + Profile templates).

    Overrides apply per eval case or test without changing stored Settings.
    """
    vocabulary = (
        vocabulary_override
        if vocabulary_override is not None
        else settings.dictation_vocabulary
    )
    user_instructions = (
        user_instructions_override
        if user_instructions_override is not None
        else settings.dictation_instructions
    )
    system_template = (
        system_template_override
        if system_template_override is not None
        else settings.dictation_cleanup_system_prompt_template
    )
    user_template = (
        user_template_override
        if user_template_override is not None
        else settings.dictation_cleanup_user_prompt_template
    )
    system_prompt = render_dictation_cleanup_system_prompt(
        system_template,
        vocabulary=vocabulary,
        user_instructions=user_instructions,
    )
    user_prompt = format_dictation_cleanup_user_message_with_template(
        raw_transcript,
        user_template,
    )
    return DictationCleanupPrompts(
        system_prompt=system_prompt,
        user_prompt_for_transcript=user_prompt,
    )
