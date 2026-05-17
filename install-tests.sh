#!/usr/bin/env bash
# Voice dictation MVP — install AI eval / test harness (pytest, deepeval, jiwer, models).
#
# Uses CHEEAPPS_VENV: folder for the virtualenv (same convention as install.sh). If unset in an
# interactive terminal, you are prompted. Non-interactive: set CHEEAPPS_VENV, e.g.
#   CHEEAPPS_VENV="$HOME/venvs/cheeapps-stack" ./install-tests.sh
# The resolved path is written to .voice_dictation_venv for ./start.sh.
#
# Windows: use install-tests.bat in this directory (same flags, shared scripts/install_post_pip.py).
#
# Does not start ollama serve (use the Ollama app or an existing server on port 11434).
#
# Usage:
#   ./install-tests.sh                  # venv + dev/eval deps + whisper weights + ollama pull (if missing)
#   ./install-tests.sh --skip-ollama    # skip `ollama pull` (cleanup llama3.2:3b + judge qwen2.5:3b-instruct)
#   ./install-tests.sh --skip-whisper   # skip faster-whisper weight download
#   ./install-tests.sh --recreate-venv  # remove existing venv at CHEEAPPS_VENV path, then recreate
#
# Env:
#   CHEEAPPS_VENV                  virtualenv directory (required non-interactive; else prompted)
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
      sed -n '2,26p' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown option: $arg (try ./install-tests.sh --help)" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${CHEEAPPS_VENV:-}" ]]; then
  if [[ ! -t 0 ]]; then
    echo "CHEEAPPS_VENV must be set when running non-interactively (no TTY)." >&2
    echo "Example: CHEEAPPS_VENV=\"\$HOME/venvs/cheeapps-stack\" $0" >&2
    exit 1
  fi
  read -r -p "Path for virtual environment (created if missing): " CHEEAPPS_VENV
fi

CHEEAPPS_VENV="${CHEEAPPS_VENV#"${CHEEAPPS_VENV%%[![:space:]]*}"}"
CHEEAPPS_VENV="${CHEEAPPS_VENV%"${CHEEAPPS_VENV##*[![:space:]]}"}"

if [[ -z "$CHEEAPPS_VENV" ]]; then
  echo "Error: path is required (set CHEEAPPS_VENV or enter a path when prompted)." >&2
  exit 1
fi

case "$CHEEAPPS_VENV" in
  /*) VENV_DIR="$CHEEAPPS_VENV" ;;
  *) VENV_DIR="$ROOT/$CHEEAPPS_VENV" ;;
esac

mkdir -p "$(dirname "$VENV_DIR")"
VENV_DIR="$(cd "$(dirname "$VENV_DIR")" && pwd)/$(basename "$VENV_DIR")"

echo "Virtual environment: $VENV_DIR"
printf '%s\n' "$VENV_DIR" >"$ROOT/.voice_dictation_venv"

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
  echo "error: need python3 (3.10+; prefers python3.13, then 3.12, then 3.11) on PATH" >&2
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

if [[ "$RECREATE_VENV" == true ]]; then
  if [[ -d "$VENV_DIR" ]] && [[ -f "$VENV_DIR/pyvenv.cfg" ]]; then
    echo "==> Removing existing venv (--recreate-venv) at $VENV_DIR ..."
    rm -rf "$VENV_DIR"
  elif [[ -e "$VENV_DIR" ]]; then
    echo "error: --recreate-venv: $VENV_DIR exists but is not a Python venv (missing pyvenv.cfg)." >&2
    exit 1
  fi
fi

if [[ -d "$VENV_DIR" ]] && [[ -f "$VENV_DIR/pyvenv.cfg" ]]; then
  echo "==> Using existing virtual environment."
elif [[ -e "$VENV_DIR" ]]; then
  echo "error: $VENV_DIR exists but is not a Python venv (missing pyvenv.cfg)." >&2
  exit 1
else
  echo "==> Creating virtual environment..."
  "$PY" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

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
  echo "==> Ollama eval models (evals/eval_config.json: cleanup llama3.2:3b, judge qwen2.5:3b-instruct) ..."
  PULL_LINES="$(python "$ROOT/scripts/install_post_pip.py" print-eval-ollama-models-to-pull || true)"
  if [[ -z "${PULL_LINES//[$'\t\r\n ']/}" ]]; then
    echo "==> Eval models already present (or Ollama unreachable — start Ollama and re-run to pull)."
  else
    while IFS=$'\t' read -r role model || [[ -n "${role:-}${model:-}" ]]; do
      [[ -z "${model:-}" ]] && continue
      label="${role:-eval}"
      echo "==> Pulling ${model} (${label}) ..."
      ollama pull "$model" || {
        echo "warning: ollama pull $model failed (offline or wrong name?)." >&2
      }
    done <<<"$PULL_LINES"
  fi
elif [[ "$SKIP_OLLAMA" != true ]]; then
  echo "warning: ollama not on PATH; skipped model pull. Install from https://ollama.com" >&2
fi

echo ""
echo "==> Done (test harness)."
echo "    Path saved in .voice_dictation_venv. Next time: export CHEEAPPS_VENV=\"$VENV_DIR\" to skip the prompt."
echo "    Activate:  source \"$VENV_DIR/bin/activate\""
echo "    Full suite:  ./run-tests.sh"
echo "    Unit tests:  pytest tests/ -q"
echo "    Evals (all): pytest evals/ -q"
echo "    STT only:    pytest evals/ -m slow -q"
echo "    Cleanup:     pytest evals/ -m requires_ollama -q"
echo "    Skip GEval:  ./run-tests.sh --skip-geval"
echo "    Config:      evals/eval_config.json"
echo "    Windows:     install-tests.bat"
