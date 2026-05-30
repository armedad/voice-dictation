"""Dictation cleanup prompt builder (TWIM defaults + eval overrides)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.dictation_cleanup_prompts import build_dictation_cleanup_prompts
from app.services.storage import Settings, get_default_settings
from core.models import DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE


def test_build_prompts_from_default_settings_non_empty() -> None:
    defaults = get_default_settings()
    prompts = build_dictation_cleanup_prompts(defaults, "um hello there")
    assert prompts.system_prompt.strip()
    assert "hello there" in prompts.user_prompt_for_transcript
    assert "{{ vocabulary }}" not in prompts.system_prompt


def test_vocabulary_override_changes_system_prompt() -> None:
    defaults = get_default_settings()
    base = build_dictation_cleanup_prompts(defaults, "test")
    with_vocab = build_dictation_cleanup_prompts(
        defaults,
        "test",
        vocabulary_override="AcmeCorp\nQ3 report",
    )
    assert base.system_prompt != with_vocab.system_prompt
    assert "AcmeCorp" in with_vocab.system_prompt
    assert "Q3 report" in with_vocab.system_prompt


def test_custom_settings_templates_used_not_core_fallback() -> None:
    custom = Settings(
        dictation_cleanup_system_prompt_template=(
            "CUSTOM-SYS {{ vocabulary }} prefs: {{ user preferences }}"
        ),
        dictation_cleanup_user_prompt_template="CUSTOM-USER <<<{raw}>>>",
    )
    prompts = build_dictation_cleanup_prompts(
        custom,
        "raw line",
        vocabulary_override="Widget",
        user_instructions_override="Be formal.",
    )
    assert "CUSTOM-SYS" in prompts.system_prompt
    assert "Widget" in prompts.system_prompt
    assert "formal" in prompts.system_prompt.lower()
    assert "CUSTOM-USER" in prompts.user_prompt_for_transcript
    assert "raw line" in prompts.user_prompt_for_transcript


def test_shipped_default_system_template_differs_from_core_builtin() -> None:
    """When _default/settings.json exists, TWIM shipped text != core None fallback."""
    defaults = get_default_settings()
    from core.models import render_dictation_cleanup_system_prompt

    core_builtin = render_dictation_cleanup_system_prompt(
        None, vocabulary=None, user_instructions=None
    )
    twim_default = build_dictation_cleanup_prompts(defaults, "x").system_prompt
    if (defaults.dictation_cleanup_system_prompt_template or "").strip():
        assert twim_default != core_builtin or (
            defaults.dictation_cleanup_system_prompt_template.strip()
            == DEFAULT_CLEANUP_SYSTEM_PROMPT_TEMPLATE.strip()
        )


def test_resolve_cleanup_for_eval_matches_default_settings() -> None:
    from evals.helpers import resolve_cleanup_for_eval

    from app.services.storage import get_default_settings

    settings = get_default_settings()
    ep, openai_key = resolve_cleanup_for_eval()
    assert ep.model_name == settings.default_model
    assert ep.provider == "ollama_chat"
    assert openai_key is None


def test_format_cleanup_failure_context_includes_llm_prompts() -> None:
    from evals.helpers import format_cleanup_failure_context
    from app.services.dictation_cleanup_prompts import DictationCleanupPrompts

    prompts = DictationCleanupPrompts(
        system_prompt="SYS-PROMPT-LINE\nsecond line",
        user_prompt_for_transcript="USER-PROMPT with raw text",
    )
    ctx = format_cleanup_failure_context(
        {"id": "x", "raw_transcript": "raw in"},
        "model out",
        prompts=prompts,
    )
    assert "SYS-PROMPT-LINE" in ctx
    assert "second line" in ctx
    assert "USER-PROMPT with raw text" in ctx
    assert "cleanup LLM system_prompt (verbatim)" in ctx
    assert "cleanup LLM user_prompt (verbatim)" in ctx


@pytest.mark.asyncio
async def test_run_cleanup_only_uses_default_settings_templates(monkeypatch) -> None:
    from evals import helpers as eval_helpers

    captured: dict[str, str] = {}

    async def fake_pipeline(*_args, **kwargs):
        captured["system"] = kwargs.get("cleanup_system_prompt") or ""
        captured["user"] = kwargs.get("cleanup_user_prompt") or ""
        return "cleaned"

    custom = Settings(
        default_model="test-cleanup-model",
        default_provider="ollama",
        dictation_cleanup_system_prompt_template="EVAL-SYS-MARKER {{ vocabulary }}",
        dictation_cleanup_user_prompt_template="EVAL-USER {raw}",
    )

    with patch.object(eval_helpers, "get_default_settings", return_value=custom):
        with patch.object(eval_helpers, "run_pipeline", side_effect=fake_pipeline):
            run = await eval_helpers.run_cleanup_for_case(
                {
                    "id": "t",
                    "raw_transcript": "uh test phrase",
                },
                cfg={},
            )

    assert run.output == "cleaned"
    assert "EVAL-SYS-MARKER" in captured["system"]
    assert "EVAL-USER" in captured["user"]
    assert "test phrase" in captured["user"]
    assert "EVAL-SYS-MARKER" in run.prompts.system_prompt
    assert "test phrase" in run.prompts.user_prompt_for_transcript
    assert run.cleanup_endpoint.model_name == "test-cleanup-model"
