#!/usr/bin/env bash
# Voice dictation MVP — one-shot dev install (venv, Python deps, optional model prefetch).
#
# Usage:
#   ./install.sh                  # full: agent + ai-frame + faster-whisper weights + ollama pull
#   ./install.sh --agent-only     # venv + requirements-agent.txt only
#   ./install.sh --skip-ollama    # skip `ollama pull`
#   ./install.sh --skip-whisper   # skip faster-whisper weight download
#   ./install.sh --skip-ai-frame  # skip ai-frame UI dependencies
#   ./install.sh --with-spike     # also install spike/ requirements (mac permission lab)
#   ./install.sh --recreate-venv  # rm -rf .venv before creating
#
# Env (optional, for Whisper preload):
#   VOICE_DICTATION_WHISPER_DEVICE   default cpu (cuda if you have NVIDIA + CUDA build)
#   VOICE_DICTATION_WHISPER_COMPUTE  default int8
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

AGENT_ONLY=false
SKIP_OLLAMA=false
SKIP_WHISPER=false
SKIP_AI_FRAME=false
WITH_SPIKE=false
RECREATE_VENV=false

for arg in "$@"; do
  case "$arg" in
    --agent-only) AGENT_ONLY=true ;;
    --skip-ollama) SKIP_OLLAMA=true ;;
    --skip-whisper) SKIP_WHISPER=true ;;
    --skip-ai-frame) SKIP_AI_FRAME=true ;;
    --with-spike) WITH_SPIKE=true ;;
    --recreate-venv) RECREATE_VENV=true ;;
    -h|--help)
      sed -n '1,25p' "$0"
      exit 0
      ;;
  esac
done

if [[ "$AGENT_ONLY" == true ]]; then
  SKIP_AI_FRAME=true
  SKIP_OLLAMA=true
  SKIP_WHISPER=true
  WITH_SPIKE=false
fi

echo "==> Voice dictation MVP install (root: $ROOT)"

if command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
elif command -v python3.12 >/dev/null 2>&1; then
  PY=python3.12
else
  PY=python3
fi

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: need python3 (ideally 3.11+) on PATH" >&2
  exit 1
fi

VER="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "==> Using $PY (Python $VER)"

if ! "$PY" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "warning: Python < 3.10 may hit typing issues; 3.11+ recommended." >&2
fi

if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
  if ! brew list portaudio >/dev/null 2>&1; then
    echo "==> Installing PortAudio via Homebrew (needed for sounddevice / mic)..."
    brew install portaudio
  else
    echo "==> PortAudio already installed (brew)."
  fi
elif [[ "$(uname -s)" == "Darwin" ]]; then
  echo "warning: Homebrew not found. If sounddevice fails to install, install PortAudio." >&2
fi

if [[ "$RECREATE_VENV" == true ]] && [[ -d .venv ]]; then
  echo "==> Removing existing .venv (--recreate-venv) ..."
  rm -rf .venv
fi

if [[ ! -d .venv ]]; then
  echo "==> Creating venv .venv ..."
  "$PY" -m venv .venv
else
  echo "==> Reusing existing .venv (use --recreate-venv to start clean) ..."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -U pip wheel setuptools

echo "==> Installing agent dependencies (requirements-agent.txt) ..."
python -m pip install -r requirements-agent.txt

if [[ "$SKIP_AI_FRAME" != true ]]; then
  echo "==> Installing ai-frame (settings UI) dependencies ..."
  python -m pip install -r ai-frame/requirements.txt
fi

if [[ "$WITH_SPIKE" == true ]]; then
  echo "==> Installing spike lab dependencies ..."
  python -m pip install -r spike/requirements.txt
fi

export INSTALL_ROOT="$ROOT"
export VOICE_DICTATION_WHISPER_DEVICE="${VOICE_DICTATION_WHISPER_DEVICE:-cpu}"
export VOICE_DICTATION_WHISPER_COMPUTE="${VOICE_DICTATION_WHISPER_COMPUTE:-int8}"

if [[ "$SKIP_WHISPER" != true ]]; then
  echo "==> Pre-downloading faster-whisper weights (from config/example-model-settings.json) ..."
  python <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["INSTALL_ROOT"])
cfg_path = root / "config" / "example-model-settings.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
t = cfg.get("transcription") or {}
prov = (t.get("provider") or "").lower().replace("-", "_")
if prov not in ("faster_whisper", "local_faster_whisper"):
    print("Skipping Whisper preload: transcription.provider is not faster_whisper in example config.")
    raise SystemExit(0)
model = t.get("model") or "base"
device = os.environ.get("VOICE_DICTATION_WHISPER_DEVICE", "cpu")
compute = os.environ.get("VOICE_DICTATION_WHISPER_COMPUTE", "int8")
print(f"Loading WhisperModel({model!r}, device={device!r}, compute_type={compute!r}) ...")
from faster_whisper import WhisperModel  # noqa: E402

WhisperModel(model, device=device, compute_type=compute)
print("Whisper weights ready.")
PY
fi

if [[ "$SKIP_OLLAMA" != true ]] && command -v ollama >/dev/null 2>&1; then
  echo "==> Pulling Ollama cleanup model (from config/example-model-settings.json) ..."
  OLLAMA_MODEL="$(
    python <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["INSTALL_ROOT"])
cfg = json.loads((root / "config" / "example-model-settings.json").read_text(encoding="utf-8"))
c = cfg.get("cleanup") or {}
prov = (c.get("provider") or "").lower().replace("-", "_")
if prov not in ("ollama_chat", "ollama"):
    raise SystemExit(0)
print(c.get("model") or "llama3.2")
PY
  )"
  if [[ -n "${OLLAMA_MODEL:-}" ]]; then
    ollama pull "$OLLAMA_MODEL" || {
      echo "warning: ollama pull failed (offline or model name wrong?). Fix cleanup.model in config and run: ollama pull <name>" >&2
    }
  else
    echo "==> Skipping ollama pull (cleanup.provider is not ollama_chat in example config)."
  fi
elif [[ "$SKIP_OLLAMA" != true ]]; then
  echo "warning: ollama not on PATH; skipped model pull. Install from https://ollama.com" >&2
fi

echo ""
echo "==> Done."
echo "    Activate:  source .venv/bin/activate"
echo "    Agent:     python run_agent.py record-once --seconds 4 --no-type"
echo "    Settings:  ./start.sh  → http://127.0.0.1:8000/ (see banner printed by start.sh)"
echo "    Config:    ~/.voice-dictation/config.json (created on first agent run if missing)"
