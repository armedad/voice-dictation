"""Pytest fixtures for voice-dictation AI evals."""

from __future__ import annotations

import pytest

from evals.helpers import (
    cleanup_endpoint,
    judge_model_name,
    load_eval_config,
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
        "geval_judge: optional DeepEval GEval (set VOICE_DICTATION_RUN_GEVAL=1)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not ollama_is_up():
        skip_ollama = pytest.mark.skip(reason="Ollama not reachable at OLLAMA_HOST/PORT")
        for item in items:
            if "requires_ollama" in item.keywords:
                item.add_marker(skip_ollama)
