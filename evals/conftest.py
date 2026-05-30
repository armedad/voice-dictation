"""Pytest fixtures for voice-dictation AI evals."""

from __future__ import annotations

import pytest

from evals.helpers import (
    cleanup_endpoint,
    judge_model_name,
    load_eval_config,
    ollama_eval_prereq_error,
    ollama_has_model,
    ollama_is_up,
)


@pytest.fixture(scope="session")
def eval_config() -> dict:
    return load_eval_config()


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    return ollama_is_up()


@pytest.fixture(scope="session")
def ollama_models_ready(eval_config: dict) -> bool:
    if not ollama_is_up():
        return False
    clean_model = cleanup_endpoint(eval_config).model_name
    judge = judge_model_name(eval_config)
    return ollama_has_model(clean_model) and ollama_has_model(judge)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: runs local ML models")
    config.addinivalue_line("markers", "requires_ollama: needs Ollama with eval models")
    config.addinivalue_line(
        "markers",
        "geval_judge: DeepEval GEval judge (default on; skip with VOICE_DICTATION_SKIP_GEVAL=1)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    for item in items:
        if item.name.startswith("test_cleanup[") and item.callspec is not None:
            case = item.callspec.params.get("case")
            if isinstance(case, dict) and not case.get("skip_geval"):
                item.add_marker(pytest.mark.geval_judge)

    if not any("requires_ollama" in item.keywords for item in items):
        return
    err = ollama_eval_prereq_error()
    if err:
        pytest.exit(f"error: {err}", returncode=1)
