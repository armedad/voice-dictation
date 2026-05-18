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


def _load_whisper_model(model: str) -> int:
    device = os.environ.get("VOICE_DICTATION_WHISPER_DEVICE", "cpu")
    compute = os.environ.get("VOICE_DICTATION_WHISPER_COMPUTE", "int8")
    print(f"Loading WhisperModel({model!r}, device={device!r}, compute_type={compute!r}) ...")
    from faster_whisper import WhisperModel  # noqa: E402

    WhisperModel(model, device=device, compute_type=compute)
    print("Whisper weights ready.")
    return 0


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
    return _load_whisper_model(model)


def _load_eval_config(root: Path) -> dict:
    cfg_path = root / "evals" / "eval_config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def cmd_prefetch_whisper_eval() -> int:
    root = _root()
    cfg = _load_eval_config(root)
    t = cfg.get("transcription") or {}
    prov = (t.get("provider") or "").lower().replace("-", "_")
    if prov not in ("faster_whisper", "local_faster_whisper"):
        print(
            "Skipping Whisper preload: transcription.provider is not faster_whisper in evals/eval_config.json."
        )
        return 0
    model = t.get("model") or "base"
    return _load_whisper_model(model)


def _eval_ollama_role_models(cfg: dict) -> list[tuple[str, str]]:
    """(role, model) pairs: cleanup from TWIM default settings, judge from eval config."""
    root = _root()
    sys.path.insert(0, str(root))
    from evals.helpers import eval_ollama_role_models

    return eval_ollama_role_models(cfg)


def cmd_print_eval_ollama_models() -> int:
    """Print unique Ollama model names from eval config (one per line)."""
    for _role, name in _eval_ollama_role_models(_load_eval_config(_root())):
        print(name)
    return 0


def cmd_print_eval_ollama_models_to_pull() -> int:
    """
    Print ``role<TAB>model`` for eval models that should be pulled.

    If Ollama is reachable, skips models already present (/api/tags).
    If Ollama is down, prints all configured models so install can still ``ollama pull``.
    """
    root = _root()
    roles = _eval_ollama_role_models(_load_eval_config(root))
    if not roles:
        return 0

    sys.path.insert(0, str(root))
    try:
        from evals.helpers import ollama_has_model, ollama_is_up
    except ImportError:
        for role, name in roles:
            print(f"{role}\t{name}")
        return 0

    if ollama_is_up():
        roles = [(role, name) for role, name in roles if not ollama_has_model(name)]
    for role, name in roles:
        print(f"{role}\t{name}")
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
        choices=(
            "prefetch-whisper",
            "print-ollama-cleanup-model",
            "prefetch-whisper-eval",
            "print-eval-ollama-models",
            "print-eval-ollama-models-to-pull",
        ),
        help=(
            "prefetch-whisper: Whisper weights from example config; "
            "prefetch-whisper-eval: from evals/eval_config.json; "
            "print-ollama-cleanup-model: cleanup model from example config; "
            "print-eval-ollama-models: unique cleanup/judge models from eval config; "
            "print-eval-ollama-models-to-pull: role+model lines for models not yet local"
        ),
    )
    args = p.parse_args()
    if args.command == "prefetch-whisper":
        return cmd_prefetch_whisper()
    if args.command == "prefetch-whisper-eval":
        return cmd_prefetch_whisper_eval()
    if args.command == "print-eval-ollama-models":
        return cmd_print_eval_ollama_models()
    if args.command == "print-eval-ollama-models-to-pull":
        return cmd_print_eval_ollama_models_to_pull()
    return cmd_print_ollama_cleanup_model()


if __name__ == "__main__":
    raise SystemExit(main())
