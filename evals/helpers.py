"""Shared helpers for voice-dictation AI evals."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

EVALS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_ROOT.parent


def _ensure_import_paths() -> None:
    """Match pytest.ini ``pythonpath = . twim`` for ``python -c`` / install scripts."""
    for sub in ("", "twim"):
        p = str((PROJECT_ROOT / sub) if sub else PROJECT_ROOT)
        if p not in sys.path:
            sys.path.insert(0, p)


_ensure_import_paths()

from app.services.dictation_cleanup_prompts import (
    DictationCleanupPrompts,
    build_dictation_cleanup_prompts,
)
from app.services.storage import DEFAULT_DATA_DIR, get_default_settings
from core.models import AdapterEndpoint
from core.orchestrator import run_pipeline


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


def resolve_cleanup_for_eval() -> tuple[AdapterEndpoint, Optional[str]]:
    """
    Cleanup endpoint for evals: same as TWIM dictation (default-user Settings).

    Uses ``get_default_settings()`` + ``build_cleanup_endpoint`` — not ``eval_config.json``.
    """
    from app.services.dictation_cleanup import build_cleanup_endpoint

    settings = get_default_settings()
    return build_cleanup_endpoint(settings, DEFAULT_DATA_DIR)


def eval_ollama_role_models(cfg: Optional[dict[str, Any]] = None) -> list[tuple[str, str]]:
    """``(role, model)`` pairs: cleanup from TWIM defaults, judge from eval config."""
    seen: set[str] = set()
    roles: list[tuple[str, str]] = []
    try:
        ep, _key = resolve_cleanup_for_eval()
        prov = (ep.provider or "").lower().replace("-", "_")
        if prov in ("ollama_chat", "ollama"):
            name = (ep.model_name or "").strip()
            if name and name not in seen:
                seen.add(name)
                roles.append(("cleanup", name))
    except ValueError:
        pass

    block = (cfg or load_eval_config()).get("judge") or {}
    prov = (block.get("provider") or "").lower().replace("-", "_")
    if prov in ("ollama_chat", "ollama"):
        name = (block.get("model") or "").strip()
        if name and name not in seen:
            roles.append(("judge", name))
    return roles


def eval_ollama_model_names(cfg: Optional[dict[str, Any]] = None) -> list[str]:
    """Unique Ollama model names required for cleanup (TWIM default) + judge (eval config)."""
    names: list[str] = []
    for _role, name in eval_ollama_role_models(cfg):
        if name not in names:
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
            "(Cleanup uses TWIM default model from get_default_settings(); judge uses evals/eval_config.json. install-tests.sh can pull them.)"
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
    """TWIM default-user cleanup model/URL (``cfg`` ignored; judge still uses eval_config)."""
    del cfg  # noqa: ARG001 — signature kept for existing call sites
    ep, _openai_key = resolve_cleanup_for_eval()
    return ep


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


def build_cleanup_prompts_for_case(case: dict[str, Any]) -> DictationCleanupPrompts:
    """Rendered cleanup LLM prompts for an eval case (TWIM default-user templates)."""
    defaults = get_default_settings()
    return build_dictation_cleanup_prompts(
        defaults,
        case["raw_transcript"],
        vocabulary_override=case.get("vocabulary"),
        user_instructions_override=case.get("user_instructions"),
    )


def format_cleanup_failure_context(
    case: dict[str, Any],
    output: str,
    *,
    prompts: Optional[DictationCleanupPrompts] = None,
    cleanup_endpoint: Optional[AdapterEndpoint] = None,
) -> str:
    """Full verbatim strings for pytest logs (no truncation)."""
    expected = case_expected_output(case)
    lines: list[str] = []
    if cleanup_endpoint is not None:
        lines.extend(
            [
                "--- cleanup LLM (TWIM default model) ---",
                f"provider: {cleanup_endpoint.provider}",
                f"model: {cleanup_endpoint.model_name}",
                f"baseURL: {cleanup_endpoint.baseURL or ''}",
            ]
        )
    lines.extend(
        [
        "--- cleanup LLM system_prompt (verbatim) ---",
        (prompts.system_prompt if prompts is not None else "(not captured)"),
        "--- cleanup LLM user_prompt (verbatim) ---",
        (prompts.user_prompt_for_transcript if prompts is not None else "(not captured)"),
        "--- raw_transcript (INPUT) ---",
        case["raw_transcript"],
        "--- cleanup actual_output (verbatim) ---",
        output,
        ]
    )
    if expected is not None:
        lines.extend(["--- expected_output (golden) ---", expected])
    vocab = case.get("vocabulary")
    if vocab:
        lines.extend(["--- vocabulary ---", str(vocab)])
    instructions = case.get("user_instructions")
    if instructions:
        lines.extend(["--- user_instructions ---", str(instructions)])
    return "\n".join(lines)


@dataclass(frozen=True)
class CleanupRunResult:
    """Cleanup model output, prompts, and TWIM default cleanup endpoint used."""

    output: str
    prompts: DictationCleanupPrompts
    cleanup_endpoint: AdapterEndpoint


async def run_cleanup_only(
    raw_transcript: str,
    *,
    cfg: Optional[dict[str, Any]] = None,
    vocabulary: Optional[str] = None,
    user_instructions: Optional[str] = None,
    system_template_override: Optional[str] = None,
    user_template_override: Optional[str] = None,
) -> str:
    """Run cleanup using TWIM default-user templates via ``get_default_settings()``."""
    defaults = get_default_settings()
    prompts = build_dictation_cleanup_prompts(
        defaults,
        raw_transcript,
        vocabulary_override=vocabulary,
        user_instructions_override=user_instructions,
        system_template_override=system_template_override,
        user_template_override=user_template_override,
    )
    clean_ep, openai_key = resolve_cleanup_for_eval()
    output = await run_pipeline(
        b"",
        "dictation.txt",
        cleanup_endpoint=clean_ep,
        cleanup_openai_api_key=openai_key,
        cleanup_system_prompt=prompts.system_prompt,
        cleanup_user_prompt=prompts.user_prompt_for_transcript,
        skip_llm_cleanup=False,
        raw_transcript_override=raw_transcript,
    )
    return output


async def run_cleanup_for_case(
    case: dict[str, Any],
    *,
    cfg: Optional[dict[str, Any]] = None,
) -> CleanupRunResult:
    """Run cleanup for one eval case; returns output and prompts sent to the cleanup LLM."""
    del cfg  # noqa: ARG001 — cleanup model from TWIM defaults; judge may use eval_config elsewhere
    prompts = build_cleanup_prompts_for_case(case)
    clean_ep, openai_key = resolve_cleanup_for_eval()
    output = await run_pipeline(
        b"",
        "dictation.txt",
        cleanup_endpoint=clean_ep,
        cleanup_openai_api_key=openai_key,
        cleanup_system_prompt=prompts.system_prompt,
        cleanup_user_prompt=prompts.user_prompt_for_transcript,
        skip_llm_cleanup=False,
        raw_transcript_override=case["raw_transcript"],
    )
    return CleanupRunResult(
        output=output,
        prompts=prompts,
        cleanup_endpoint=clean_ep,
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
