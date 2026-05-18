"""LLM cleanup regression: one run per case — deterministic gates + optional GEval judge."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.models import OllamaModel
from deepeval.test_case import LLMTestCase

from app.services.dictation_cleanup_prompts import DictationCleanupPrompts
from core.models import AdapterEndpoint
from evals.helpers import (
    build_geval_criteria_for_case,
    case_expected_output,
    format_cleanup_failure_context,
    geval_evaluation_params_for_case,
    judge_base_url,
    judge_model_name,
    judge_temperature,
    load_cleanup_cases,
    run_cleanup_for_case,
)

pytestmark = pytest.mark.requires_ollama


def _geval_enabled() -> bool:
    """GEval runs by default; opt out with VOICE_DICTATION_SKIP_GEVAL=1 or RUN_GEVAL=0."""
    skip = os.environ.get("VOICE_DICTATION_SKIP_GEVAL", "").strip().lower()
    if skip in ("1", "true", "yes"):
        return False
    run = os.environ.get("VOICE_DICTATION_RUN_GEVAL", "").strip().lower()
    if run in ("0", "false", "no"):
        return False
    return True


def _judge_model(cfg: dict[str, Any]) -> OllamaModel:
    return OllamaModel(
        model=judge_model_name(cfg),
        base_url=judge_base_url(cfg),
        temperature=judge_temperature(cfg),
    )


def _raise_cleanup_failure(
    case: dict[str, Any],
    output: str,
    message: str,
    *,
    prompts: Optional[DictationCleanupPrompts] = None,
    cleanup_endpoint: Optional[AdapterEndpoint] = None,
    cause: BaseException | None = None,
    suppress_cause: bool = False,
) -> None:
    """
    Raise with full verbatim cleanup context (LLM prompts, input, output).

    GEval failures pass ``suppress_cause=True`` so pytest does not print the inner
    ``assert_test`` frame (``saferepr`` truncates ``LLMTestCase`` at 240 chars).
    """
    err = AssertionError(
        f"{message}\n\n{format_cleanup_failure_context(case, output, prompts=prompts, cleanup_endpoint=cleanup_endpoint)}"
    )
    if cause is not None:
        if suppress_cause:
            raise err from None
        raise err from cause
    raise err


def _assert_deterministic_gates(
    case: dict[str, Any],
    output: str,
    *,
    prompts: DictationCleanupPrompts,
    cleanup_endpoint: AdapterEndpoint,
) -> None:
    case_id = case["id"]
    if not (output or "").strip():
        _raise_cleanup_failure(
            case,
            output,
            f"Case {case_id!r}: cleanup returned empty output",
            prompts=prompts,
            cleanup_endpoint=cleanup_endpoint,
        )

    lower = output.lower()
    for phrase in case.get("expected_contains") or []:
        if phrase.lower() not in lower:
            _raise_cleanup_failure(
                case,
                output,
                f"Case {case_id!r}: output must contain {phrase!r}",
                prompts=prompts,
                cleanup_endpoint=cleanup_endpoint,
            )
    for phrase in case.get("expected_not_contains") or []:
        if phrase.lower() in lower:
            _raise_cleanup_failure(
                case,
                output,
                f"Case {case_id!r}: output must not contain {phrase!r}",
                prompts=prompts,
                cleanup_endpoint=cleanup_endpoint,
            )


def _assert_geval_rubric(
    case: dict[str, Any],
    eval_config: dict[str, Any],
    output: str,
    *,
    prompts: DictationCleanupPrompts,
    cleanup_endpoint: AdapterEndpoint,
) -> None:
    threshold = float(
        case.get("min_geval_score", eval_config.get("cleanup_geval_threshold", 0.5))
    )
    metric = GEval(
        name=f"cleanup_{case['id']}",
        criteria=build_geval_criteria_for_case(case),
        evaluation_params=geval_evaluation_params_for_case(case),
        model=_judge_model(eval_config),
        threshold=threshold,
        async_mode=False,
    )
    test_case = LLMTestCase(
        input=case["raw_transcript"],
        actual_output=output,
        expected_output=case_expected_output(case),
    )
    try:
        assert_test(test_case, [metric], run_async=False)
    except AssertionError as exc:
        _raise_cleanup_failure(
            case,
            output,
            f"Case {case['id']!r}: GEval judge failed (threshold {threshold}): {exc}",
            prompts=prompts,
            cleanup_endpoint=cleanup_endpoint,
            cause=exc,
            suppress_cause=True,
        )


@pytest.mark.parametrize("case", load_cleanup_cases(), ids=lambda c: c["id"])
def test_cleanup(case: dict[str, Any], eval_config: dict[str, Any]) -> None:
    """
    Run cleanup once, then substring gates and (unless skipped) DeepEval GEval.

    GEval skipped when ``skip_geval`` is true on the case, or globally via
    VOICE_DICTATION_SKIP_GEVAL / ./run-tests.sh --skip-geval.
    """
    run = asyncio.run(run_cleanup_for_case(case, cfg=eval_config))
    _assert_deterministic_gates(
        case,
        run.output,
        prompts=run.prompts,
        cleanup_endpoint=run.cleanup_endpoint,
    )

    if case.get("skip_geval") or not _geval_enabled():
        return

    _assert_geval_rubric(
        case,
        eval_config,
        run.output,
        prompts=run.prompts,
        cleanup_endpoint=run.cleanup_endpoint,
    )
