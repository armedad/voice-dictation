"""Post-``pip install`` steps shared by ``install.sh`` and ``install.bat`` (Whisper preload, Ollama model name)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _root() -> Path:
    r = os.environ.get("INSTALL_ROOT")
    if r:
        return Path(r)
    return Path(__file__).resolve().parent.parent


def cmd_prefetch_whisper() -> int:
    root = _root()
    cfg_path = root / "config" / "example-model-settings.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    t = cfg.get("transcription") or {}
    prov = (t.get("provider") or "").lower().replace("-", "_")
    if prov not in ("faster_whisper", "local_faster_whisper"):
        print("Skipping Whisper preload: transcription.provider is not faster_whisper in example config.")
        return 0
    model = t.get("model") or "base"
    device = os.environ.get("VOICE_DICTATION_WHISPER_DEVICE", "cpu")
    compute = os.environ.get("VOICE_DICTATION_WHISPER_COMPUTE", "int8")
    print(f"Loading WhisperModel({model!r}, device={device!r}, compute_type={compute!r}) ...")
    from faster_whisper import WhisperModel  # noqa: E402

    WhisperModel(model, device=device, compute_type=compute)
    print("Whisper weights ready.")
    return 0


def _normalize_ollama_pull_name(raw: object, *, default: str = "llama3.2:3b") -> str:
    """Single-line name safe for ``ollama pull`` (strip whitespace / CR; explicit tag avoids some 400s)."""
    if raw is None:
        return default
    s = str(raw).replace("\r", "").replace("\n", " ").strip()
    if not s:
        return default
    return s


def cmd_print_ollama_cleanup_model() -> int:
    """Print cleanup model name to stdout only (for shell capture); no output if not Ollama."""
    root = _root()
    cfg = json.loads((root / "config" / "example-model-settings.json").read_text(encoding="utf-8"))
    c = cfg.get("cleanup") or {}
    prov = (c.get("provider") or "").lower().replace("-", "_")
    if prov not in ("ollama_chat", "ollama"):
        return 0
    print(_normalize_ollama_pull_name(c.get("model"), default="llama3.2:3b"), end="")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Install helpers after pip (cross-platform).")
    p.add_argument(
        "command",
        choices=("prefetch-whisper", "print-ollama-cleanup-model"),
        help="prefetch-whisper: download Whisper weights; print-ollama-cleanup-model: print model name or nothing",
    )
    args = p.parse_args()
    if args.command == "prefetch-whisper":
        return cmd_prefetch_whisper()
    return cmd_print_ollama_cleanup_model()


if __name__ == "__main__":
    raise SystemExit(main())
