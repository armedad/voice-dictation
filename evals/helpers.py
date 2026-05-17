"""Shared helpers for voice-dictation AI evals."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx

from core.models import (
    AdapterEndpoint,
    format_dictation_cleanup_user_message_with_template,
    render_dictation_cleanup_system_prompt,
)
from core.orchestrator import run_pipeline

EVALS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_ROOT.parent


def load_eval_config() -> dict[str, Any]:
    path = EVALS_ROOT / "eval_config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def ollama_base_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    port = os.environ.get("OLLAMA_PORT", "11434").strip() or "11434"
    return f"http://{host}:{port}"


def ollama_is_up(timeout: float = 2.0) -> bool:
    try:
        r = httpx.get(f"{ollama_base_url()}/api/tags", timeout=timeout)
        return r.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def ollama_has_model(model_name: str, timeout: float = 2.0) -> bool:
    try:
        r = httpx.get(f"{ollama_base_url()}/api/tags", timeout=timeout)
        r.raise_for_status()
        tags = r.json()
    except (httpx.HTTPError, OSError):
        return False
    want = model_name.strip().lower()
    for entry in tags.get("models") or []:
        name = str(entry.get("name") or "").lower()
        if name == want or name.startswith(f"{want}:"):
            return True
    return False


def eval_ollama_model_names(cfg: Optional[dict[str, Any]] = None) -> list[str]:
    """Unique cleanup + judge model names from eval config."""
    c = cfg or load_eval_config()
    names: list[str] = []
    for key in ("cleanup", "judge"):
        block = c.get(key) or {}
        prov = (block.get("provider") or "").lower().replace("-", "_")
        if prov not in ("ollama_chat", "ollama"):
            continue
        name = (block.get("model") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def ollama_eval_prereq_error() -> Optional[str]:
    """
    Return a human-readable error if Ollama eval prerequisites are not met, else None.
    """
    base = ollama_base_url()
    if not ollama_is_up():
        return (
            f"Ollama is not reachable at {base}.\n"
            "Start the Ollama app (menu bar on macOS) or ensure one server is listening on "
            "OLLAMA_HOST / OLLAMA_PORT (default 127.0.0.1:11434).\n"
            "If you see 'address already in use', Ollama is likely already running — "
            "do not start a second 'ollama serve'.\n"
            "Cleanup and GEval evals require a running Ollama instance."
        )

    cfg = load_eval_config()
    missing = [m for m in eval_ollama_model_names(cfg) if not ollama_has_model(m)]
    if missing:
        pulls = " && ".join(f"ollama pull {m}" for m in missing)
        return (
            f"Ollama at {base} is up but required eval model(s) are missing: {', '.join(missing)}.\n"
            f"Pull them with: {pulls}\n"
            "(Models are listed in evals/eval_config.json; install-tests.sh can pull them.)"
        )
    return None


def require_ollama_for_evals() -> None:
    """Exit the process with a clear message if Ollama eval prerequisites are not met."""
    err = ollama_eval_prereq_error()
    if err:
        raise SystemExit(f"error: {err}")


def transcription_endpoint(cfg: Optional[dict[str, Any]] = None) -> AdapterEndpoint:
    c = cfg or load_eval_config()
    t = c["transcription"]
    return AdapterEndpoint(
        provider=t.get("provider", "faster_whisper"),
        baseURL=t.get("baseURL", ""),
        model=t.get("model", "base"),
    )


def cleanup_endpoint(cfg: Optional[dict[str, Any]] = None) -> AdapterEndpoint:
    c = cfg or load_eval_config()
    clean = c["cleanup"]
    base = (clean.get("baseURL") or "").strip() or ollama_base_url()
    return AdapterEndpoint(
        provider=clean.get("provider", "ollama_chat"),
        baseURL=base,
        model=clean.get("model", "llama3.2:3b"),
    )


def judge_model_name(cfg: Optional[dict[str, Any]] = None) -> str:
    c = cfg or load_eval_config()
    return str(c.get("judge", {}).get("model", "qwen2.5:3b-instruct"))


def judge_base_url(cfg: Optional[dict[str, Any]] = None) -> str:
    c = cfg or load_eval_config()
    j = c.get("judge", {})
    return (j.get("baseURL") or "").strip() or ollama_base_url()


def judge_temperature(cfg: Optional[dict[str, Any]] = None) -> float:
    c = cfg or load_eval_config()
    return float(c.get("judge", {}).get("temperature", 0))


def normalize_for_wer(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for WER comparison."""
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


async def run_stt_only(
    wav_path: Path,
    *,
    cfg: Optional[dict[str, Any]] = None,
    transcription_initial_prompt: Optional[str] = None,
) -> str:
    data = wav_path.read_bytes()
    return await run_pipeline(
        data,
        wav_path.name,
        transcription_endpoint=transcription_endpoint(cfg),
        skip_llm_cleanup=True,
        transcription_initial_prompt=transcription_initial_prompt,
    )


async def run_cleanup_only(
    raw_transcript: str,
    *,
    cfg: Optional[dict[str, Any]] = None,
    vocabulary: Optional[str] = None,
    user_instructions: Optional[str] = None,
    cleanup_user_prompt_template: Optional[str] = None,
) -> str:
    system_prompt = render_dictation_cleanup_system_prompt(
        None,
        vocabulary=vocabulary,
        user_instructions=user_instructions,
    )
    user_builder = (
        lambda raw: format_dictation_cleanup_user_message_with_template(
            raw, cleanup_user_prompt_template
        )
    )
    return await run_pipeline(
        b"",
        "dictation.txt",
        cleanup_endpoint=cleanup_endpoint(cfg),
        cleanup_system_prompt=system_prompt,
        cleanup_user_prompt_builder=user_builder,
        skip_llm_cleanup=False,
        raw_transcript_override=raw_transcript,
    )


async def run_cleanup_for_case(
    case: dict[str, Any],
    *,
    cfg: Optional[dict[str, Any]] = None,
) -> str:
    """Run cleanup for one eval case dict (``raw_transcript``, vocabulary, user_instructions)."""
    return await run_cleanup_only(
        case["raw_transcript"],
        cfg=cfg,
        vocabulary=case.get("vocabulary"),
        user_instructions=case.get("user_instructions"),
    )


def load_stt_cases() -> list[dict[str, Any]]:
    meta = EVALS_ROOT / "cases" / "stt" / "metadata.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    stt_dir = meta.parent
    for row in data.get("cases") or []:
        wav_name = row["wav"]
        cases.append({**row, "wav_path": stt_dir / wav_name})
    return cases


def load_cleanup_cases() -> list[dict[str, Any]]:
    cases_dir = EVALS_ROOT / "cases" / "cleanup"
    out: list[dict[str, Any]] = []
    for path in sorted(cases_dir.glob("*.json")):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def load_cleanup_cases_for_geval() -> list[dict[str, Any]]:
    """Cleanup cases that run GEval (excludes ``skip_geval: true``)."""
    return [c for c in load_cleanup_cases() if not c.get("skip_geval")]


GEVAL_CLEANUP_CRITERIA_PATH = EVALS_ROOT / "geval_cleanup_criteria.json"


def load_geval_cleanup_base_criteria(
    path: Path | None = None,
) -> str:
    """Load shared GEval rubric text from evals/geval_cleanup_criteria.json."""
    p = path or GEVAL_CLEANUP_CRITERIA_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    criteria = data.get("criteria")
    if not isinstance(criteria, str) or not criteria.strip():
        raise ValueError(f"{p}: missing non-empty string field 'criteria'")
    return criteria.strip()


def case_expected_output(case: dict[str, Any]) -> Optional[str]:
    """Golden cleaned text for GEval, from case JSON field ``expected_output``."""
    eo = case.get("expected_output")
    if isinstance(eo, str) and eo.strip():
        return eo.strip()
    return None


_GEVAL_EXPECTED_OUTPUT_SUFFIX = (
    " When EXPECTED OUTPUT is provided, score 1.0 if ACTUAL OUTPUT matches its meaning "
    "(minor punctuation or wording differences are fine unless case-specific rules say otherwise)."
)


def build_geval_criteria_for_case(case: dict[str, Any]) -> str:
    """
    GEval rubric for one cleanup case: base criteria plus optional per-case augment.

    Case JSON may include ``geval_criteria_augment`` (appended to the base) or
    ``geval_criteria`` (replaces the shared base file; augment still appended if present).
    """
    override = case.get("geval_criteria")
    if isinstance(override, str) and override.strip():
        base = override.strip()
    else:
        base = load_geval_cleanup_base_criteria()

    if case_expected_output(case) is not None:
        base = f"{base}{_GEVAL_EXPECTED_OUTPUT_SUFFIX}"

    augment = case.get("geval_criteria_augment")
    if isinstance(augment, str) and augment.strip():
        return f"{base} {augment.strip()}"
    return base


def geval_evaluation_params_for_case(case: dict[str, Any]) -> list[Any]:
    """DeepEval ``SingleTurnParams`` list; includes EXPECTED_OUTPUT when case provides it."""
    from deepeval.test_case.llm_test_case import SingleTurnParams

    params: list[Any] = [
        SingleTurnParams.INPUT,
        SingleTurnParams.ACTUAL_OUTPUT,
    ]
    if case_expected_output(case) is not None:
        params.append(SingleTurnParams.EXPECTED_OUTPUT)
    return params
