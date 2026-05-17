"""GEval criteria loading (no Ollama)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepeval.test_case.llm_test_case import SingleTurnParams

from evals.helpers import (
    GEVAL_CLEANUP_CRITERIA_PATH,
    build_geval_criteria_for_case,
    case_expected_output,
    geval_evaluation_params_for_case,
    load_cleanup_cases,
    load_cleanup_cases_for_geval,
    load_geval_cleanup_base_criteria,
)


def test_base_criteria_file_exists() -> None:
    assert GEVAL_CLEANUP_CRITERIA_PATH.is_file()
    base = load_geval_cleanup_base_criteria()
    assert "ACTUAL OUTPUT" in base


def test_build_geval_criteria_augment() -> None:
    base = load_geval_cleanup_base_criteria()
    merged = build_geval_criteria_for_case(
        {"geval_criteria_augment": "EXTRA RULE for this story."}
    )
    assert merged.startswith(base)
    assert "EXTRA RULE for this story." in merged


def test_case_expected_output() -> None:
    assert case_expected_output({}) is None
    assert case_expected_output({"expected_output": "  hi  "}) == "hi"


def test_geval_params_without_expected() -> None:
    params = geval_evaluation_params_for_case({"id": "x"})
    assert params == [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]


def test_geval_params_with_expected() -> None:
    params = geval_evaluation_params_for_case(
        {"expected_output": "Golden text."}
    )
    assert SingleTurnParams.EXPECTED_OUTPUT in params


def test_build_geval_criteria_adds_expected_suffix() -> None:
    base_only = build_geval_criteria_for_case({})
    with_expected = build_geval_criteria_for_case(
        {"expected_output": "Golden text."}
    )
    assert "EXPECTED OUTPUT is provided" not in base_only
    assert "EXPECTED OUTPUT is provided" in with_expected


def test_build_geval_criteria_override(tmp_path: Path) -> None:
    merged = build_geval_criteria_for_case(
        {
            "geval_criteria": "Custom base rubric.",
            "geval_criteria_augment": "Plus augment.",
        }
    )
    assert merged == "Custom base rubric. Plus augment."


def test_load_cleanup_cases_for_geval_excludes_skip() -> None:
    all_ids = {c["id"] for c in load_cleanup_cases()}
    geval_ids = {c["id"] for c in load_cleanup_cases_for_geval()}
    assert "question_not_answered" in all_ids
    assert "question_not_answered" not in geval_ids
    assert geval_ids <= all_ids


def test_load_base_criteria_rejects_empty(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"criteria": ""}), encoding="utf-8")
    with pytest.raises(ValueError, match="criteria"):
        load_geval_cleanup_base_criteria(bad)
