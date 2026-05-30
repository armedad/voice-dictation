"""Tests for core.models — vocabulary, cleanup prompts, pydantic config."""

from __future__ import annotations

import pytest

from core.models import (
    MAX_VOCABULARY_LINES,
    VoiceDictationConfig,
    format_dictation_cleanup_user_message,
    format_dictation_cleanup_user_message_with_template,
    format_vocabulary_for_whisper_initial_prompt,
    parse_vocabulary_lines,
    render_dictation_cleanup_system_prompt,
)


class TestParseVocabularyLines:
    def test_empty_and_whitespace(self) -> None:
        assert parse_vocabulary_lines(None) == []
        assert parse_vocabulary_lines("  \n  ") == []

    def test_trims_and_skips_blank_lines(self) -> None:
        raw = " Zapier \n\n  Ollama  \n"
        assert parse_vocabulary_lines(raw) == ["Zapier", "Ollama"]

    def test_caps_at_max_lines(self) -> None:
        raw = "\n".join(f"term{i}" for i in range(MAX_VOCABULARY_LINES + 10))
        lines = parse_vocabulary_lines(raw)
        assert len(lines) == MAX_VOCABULARY_LINES
        assert lines[0] == "term0"
        assert lines[-1] == f"term{MAX_VOCABULARY_LINES - 1}"


class TestFormatVocabularyForWhisper:
    def test_none_when_empty(self) -> None:
        assert format_vocabulary_for_whisper_initial_prompt(None) is None
        assert format_vocabulary_for_whisper_initial_prompt("") is None

    def test_prefix_and_join(self) -> None:
        out = format_vocabulary_for_whisper_initial_prompt("Foo\nBar")
        assert out == "Terms that may appear: Foo, Bar."

    def test_truncates_long_join(self) -> None:
        terms = ", ".join(f"word{i}" for i in range(400))
        out = format_vocabulary_for_whisper_initial_prompt(terms)
        assert out is not None
        assert len(out) <= 1800 + len("Terms that may appear: .")


class TestRenderDictationCleanupSystemPrompt:
    def test_defaults_vocabulary_and_prefs_to_none(self) -> None:
        out = render_dictation_cleanup_system_prompt(
            "",
            vocabulary=None,
            user_instructions=None,
        )
        assert "none" in out.lower()
        assert "{{ vocabulary }}" not in out
        assert "{{ user preferences }}" not in out

    def test_substitutes_vocabulary_bullets(self) -> None:
        tmpl = "VOCAB:\n{{ vocabulary }}\nPREFS:\n{{ user preferences }}"
        out = render_dictation_cleanup_system_prompt(
            tmpl,
            vocabulary="Acme Corp",
            user_instructions="Use Oxford comma.",
        )
        assert "- Acme Corp" in out
        assert "Use Oxford comma." in out

    def test_braces_in_template_not_format_interpolation(self) -> None:
        tmpl = "Keep {literal braces} and {{ vocabulary }}."
        out = render_dictation_cleanup_system_prompt(tmpl, vocabulary=None, user_instructions=None)
        assert "{literal braces}" in out


class TestFormatDictationCleanupUserMessage:
    def test_default_template_wraps_raw(self) -> None:
        msg = format_dictation_cleanup_user_message("  hello world  ")
        assert "hello world" in msg
        assert "Transcript for you to transcribe" in msg
        assert "minimal edits" in msg

    def test_custom_template_appends_raw_placeholder(self) -> None:
        msg = format_dictation_cleanup_user_message_with_template(
            "test", "Rewrite only:"
        )
        assert msg.endswith("test")
        assert "Rewrite only:" in msg

    def test_custom_template_with_raw_placeholder(self) -> None:
        msg = format_dictation_cleanup_user_message_with_template(
            "payload", "Body: {raw}"
        )
        assert msg == "Body: payload"


class TestVoiceDictationConfig:
    def test_validates_example_json(self, example_voice_config: dict) -> None:
        cfg = VoiceDictationConfig.model_validate(example_voice_config)
        assert cfg.transcription.provider == "faster_whisper"
        assert cfg.transcription.model_name == "base"
        assert cfg.cleanup.provider == "ollama_chat"
