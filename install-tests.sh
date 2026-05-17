#!/usr/bin/env bash
# Voice dictation MVP — install AI eval / test harness (pytest, deepeval, jiwer, models).
#
# Windows: use install-tests.bat in this directory (same flags, shared scripts/install_post_pip.py).
#
# Does not start ollama serve (use the Ollama app or an existing server on port 11434).
#
# Usage:
#   ./install-tests.sh                  # venv + dev/eval deps + whisper weights + ollama pull
#   ./install-tests.sh --skip-ollama    # skip `ollama pull`
#   ./install-tests.sh --skip-whisper   # skip faster-whisper weight download
#   ./install-tests.sh --recreate-venv  # rm -rf .venv before creating
#
# Env (optional, for Whisper preload):
#   VOICE_DICTATION_WHISPER_DEVICE   default cpu
#   VOICE_DICTATION_WHISPER_COMPUTE  default int8
#   OLLAMA_HOST / OLLAMA_PORT        default 127.0.0.1 / 11434
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

SKIP_OLLAMA=false
SKIP_WHISPER=false
RECREATE_VENV=false

for arg in "$@"; do
  case "$arg" in
    --skip-ollama) SKIP_OLLAMA=true ;;
    --skip-whisper) SKIP_WHISPER=true ;;
    --recreate-venv) RECREATE_VENV=true ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown option: $arg (try ./install-tests.sh --help)" >&2
      exit 1
      ;;
  esac
done

echo "==> Voice dictation test harness install (root: $ROOT)"

if command -v python3.13 >/dev/null 2>&1; then
  PY=python3.13
elif command -v python3.12 >/dev/null 2>&1; then
  PY=python3.12
elif command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
else
  PY=python3
fi

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: need python3 (3.10+) on PATH" >&2
  exit 1
fi

VER="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "==> Using $PY (Python $VER)"

if ! "$PY" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "warning: Python < 3.10 may hit typing issues; 3.11+ recommended." >&2
fi

if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
  if ! brew list portaudio >/dev/null 2>&1; then
    echo "==> Installing PortAudio via Homebrew (needed for sounddevice / agent deps)..."
    brew install portaudio
  else
    echo "==> PortAudio already installed (brew)."
  fi
elif [[ "$(uname -s)" == "Darwin" ]]; then
  echo "warning: Homebrew not found. If sounddevice fails, install PortAudio." >&2
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

echo "==> Installing test dependencies (requirements-dev.txt + requirements-eval.txt) ..."
python -m pip install -r requirements-dev.txt -r requirements-eval.txt

export INSTALL_ROOT="$ROOT"
export VOICE_DICTATION_WHISPER_DEVICE="${VOICE_DICTATION_WHISPER_DEVICE:-cpu}"
export VOICE_DICTATION_WHISPER_COMPUTE="${VOICE_DICTATION_WHISPER_COMPUTE:-int8}"

if [[ "$SKIP_WHISPER" != true ]]; then
  echo "==> Pre-downloading faster-whisper weights (from evals/eval_config.json) ..."
  python "$ROOT/scripts/install_post_pip.py" prefetch-whisper-eval
fi

OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_BASE="http://${OLLAMA_HOST}:${OLLAMA_PORT}"

if command -v curl >/dev/null 2>&1; then
  if curl -fsS --max-time 2 "${OLLAMA_BASE}/api/tags" >/dev/null 2>&1; then
    echo "==> Ollama already reachable at ${OLLAMA_BASE}"
  else
    echo "==> Ollama not reachable at ${OLLAMA_BASE} (start the Ollama app; do not run a second 'ollama serve' if port 11434 is in use)."
  fi
else
  echo "warning: curl not found; skipping Ollama reachability check." >&2
fi

if [[ "$SKIP_OLLAMA" != true ]] && command -v ollama >/dev/null 2>&1; then
  echo "==> Pulling Ollama eval models (from evals/eval_config.json) ..."
  while IFS= read -r model || [[ -n "${model:-}" ]]; do
    [[ -z "${model:-}" ]] && continue
    ollama pull "$model" || {
      echo "warning: ollama pull $model failed (offline or wrong name?)." >&2
    }
  done < <(python "$ROOT/scripts/install_post_pip.py" print-eval-ollama-models)
elif [[ "$SKIP_OLLAMA" != true ]]; then
  echo "warning: ollama not on PATH; skipped model pull. Install from https://ollama.com" >&2
fi

echo ""
echo "==> Done (test harness)."
echo "    Activate:  source .venv/bin/activate"
echo "    Unit tests:  pytest tests/ -q"
echo "    Evals (all): pytest evals/ -q"
echo "    STT only:    pytest evals/ -m slow -q"
echo "    Cleanup:     pytest evals/ -m requires_ollama -q"
echo "    GEval judge: VOICE_DICTATION_RUN_GEVAL=1 pytest evals/ -m geval_judge -q"
echo "    Config:      evals/eval_config.json"
echo "    Windows:     install-tests.bat"
