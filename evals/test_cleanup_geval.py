"""LLM cleanup regression: deterministic gates + optional DeepEval GEval judge."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.models import OllamaModel
from deepeval.test_case import LLMTestCase
from deepeval.test_case.llm_test_case import SingleTurnParams

from evals.helpers import (
    judge_base_url,
    judge_model_name,
    judge_temperature,
    load_cleanup_cases,
    load_eval_config,
    run_cleanup_only,
)

pytestmark = pytest.mark.requires_ollama

_SHARED_GEVAL_CRITERIA = (
    "Score 1.0 (pass) when ACTUAL OUTPUT is an acceptable dictation rewrite of INPUT: "
    "removes filler, preserves intent, plain text, no assistant preamble. "
    "Using vocabulary terms (e.g. Q3 report) is allowed. "
    "If INPUT is a question, OUTPUT must stay a question and must NOT state factual answers "
    "(e.g. do not say Paris). "
    "Score 0.0 only for clear violations. Minor wording differences are fine."
)


def _judge_model(cfg: dict[str, Any]) -> OllamaModel:
    return OllamaModel(
        model=judge_model_name(cfg),
        base_url=judge_base_url(cfg),
        temperature=judge_temperature(cfg),
    )


def _assert_substrings(
    output: str,
    required: list[str],
    *,
    case_id: str,
) -> None:
    lower = output.lower()
    for phrase in required:
        if phrase.lower() not in lower:
            raise AssertionError(
                f"Case {case_id!r}: output must contain {phrase!r}; got: {output!r}"
            )


async def _run_case_output(case: dict, eval_config: dict) -> str:
    return await run_cleanup_only(
        case["raw_transcript"],
        cfg=eval_config,
        vocabulary=case.get("vocabulary"),
        user_instructions=case.get("user_instructions"),
    )


@pytest.mark.parametrize("case", load_cleanup_cases(), ids=lambda c: c["id"])
def test_cleanup_deterministic(case: dict, eval_config: dict, ollama_models_ready: bool) -> None:
    """Hard gates: run real cleanup pipeline and check substring expectations."""
    if not ollama_models_ready:
        clean = eval_config["cleanup"]["model"]
        pytest.skip(f"Ollama missing cleanup model {clean!r}. Run: ollama pull {clean}")

    output = asyncio.run(_run_case_output(case, eval_config))
    assert (output or "").strip(), f"Case {case['id']!r}: cleanup returned empty output"

    _assert_substrings(output, case.get("expected_contains") or [], case_id=case["id"])
    lower = output.lower()
    for phrase in case.get("expected_not_contains") or []:
        if phrase.lower() in lower:
            raise AssertionError(
                f"Case {case['id']!r}: output must not contain {phrase!r}; got: {output!r}"
            )


@pytest.mark.geval_judge
@pytest.mark.parametrize("case", load_cleanup_cases(), ids=lambda c: c["id"])
def test_cleanup_geval_rubric(case: dict, eval_config: dict, ollama_models_ready: bool) -> None:
    """
    Optional LLM-as-judge rubric (flaky with small local models).

    Enable with: VOICE_DICTATION_RUN_GEVAL=1 pytest evals/ -m geval_judge
    """
    if not os.environ.get("VOICE_DICTATION_RUN_GEVAL", "").strip():
        pytest.skip("Set VOICE_DICTATION_RUN_GEVAL=1 to run DeepEval GEval judge tests")
    if case.get("skip_geval"):
        pytest.skip(f"Case {case['id']!r} uses deterministic gates only (skip_geval)")

    if not ollama_models_ready:
        clean = eval_config["cleanup"]["model"]
        judge = judge_model_name(eval_config)
        pytest.skip(
            f"Ollama missing cleanup model {clean!r} or judge {judge!r}. "
            f"Run: ollama pull {clean} && ollama pull {judge}"
        )

    output = asyncio.run(_run_case_output(case, eval_config))
    threshold = float(
        case.get("min_geval_score", eval_config.get("cleanup_geval_threshold", 0.5))
    )

    metric = GEval(
        name=f"cleanup_{case['id']}",
        criteria=_SHARED_GEVAL_CRITERIA,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=_judge_model(eval_config),
        threshold=threshold,
        async_mode=False,
    )
    test_case = LLMTestCase(input=case["raw_transcript"], actual_output=output)
    assert_test(test_case, [metric], run_async=False)
