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
        model=clean.get("model", "llama3.2"),
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
