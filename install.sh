#!/usr/bin/env bash
# Voice dictation MVP — one-shot dev install (venv, Python deps, optional model prefetch).
#
# Uses CHEEAPPS_VENV: folder for the virtualenv (same convention as gauth). If unset in an
# interactive terminal, you are prompted. Non-interactive: set CHEEAPPS_VENV, e.g.
#   CHEEAPPS_VENV="$HOME/venvs/cheeapps-stack" ./install.sh
# The resolved path is written to .voice_dictation_venv for ./start.sh.
#
# Windows: use install.bat in this directory (same flags, shared scripts/install_post_pip.py).
#
# Usage:
#   ./install.sh                  # full: agent + twim + faster-whisper weights + ollama pull
#   ./install.sh --agent-only     # venv + requirements-agent.txt only
#   ./install.sh --skip-ollama    # skip `ollama pull`
#   ./install.sh --skip-whisper   # skip faster-whisper weight download
#   ./install.sh --skip-twim      # skip twim UI dependencies (alias: --skip-ai-frame)
#   ./install.sh --with-spike     # also install spike/ requirements (mac permission lab)
#   ./install.sh --recreate-venv  # remove existing venv at CHEEAPPS_VENV path, then recreate
#
# Env:
#   CHEEAPPS_VENV                  virtualenv directory (required non-interactive; else prompted)
# Env (optional, for Whisper preload):
#   VOICE_DICTATION_WHISPER_DEVICE   default cpu (cuda if you have NVIDIA + CUDA build)
#   VOICE_DICTATION_WHISPER_COMPUTE  default int8
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

AGENT_ONLY=false
SKIP_OLLAMA=false
SKIP_WHISPER=false
SKIP_TWIM=false
WITH_SPIKE=false
RECREATE_VENV=false

for arg in "$@"; do
  case "$arg" in
    --agent-only) AGENT_ONLY=true ;;
    --skip-ollama) SKIP_OLLAMA=true ;;
    --skip-whisper) SKIP_WHISPER=true ;;
    --skip-twim|--skip-ai-frame) SKIP_TWIM=true ;;
    --with-spike) WITH_SPIKE=true ;;
    --recreate-venv) RECREATE_VENV=true ;;
    -h|--help)
      sed -n '2,25p' "$0"
      exit 0
      ;;
  esac
done

if [[ "$AGENT_ONLY" == true ]]; then
  SKIP_TWIM=true
  SKIP_OLLAMA=true
  SKIP_WHISPER=true
  WITH_SPIKE=false
fi

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

echo "==> Voice dictation MVP install (root: $ROOT)"

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
  echo "error: need python3 (3.10+; install.sh prefers python3.13, then 3.12, then 3.11) on PATH" >&2
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

echo "==> Installing agent dependencies (requirements-agent.txt) ..."
echo "    (includes PyObjC + quickmachotkey for macOS global hotkeys; mic/STT/httpx/pynput per that file)"
python -m pip install -r requirements-agent.txt
if ! python -c 'import importlib; raise SystemExit(0 if importlib.util.find_spec("quickmachotkey") else 1)' >/dev/null 2>&1; then
  echo "==> Installing quickmachotkey (missing from environment) ..."
  python -m pip install quickmachotkey
fi

if [[ "$SKIP_TWIM" != true ]]; then
  echo "==> Installing twim (settings UI) dependencies ..."
  python -m pip install -r twim/requirements.txt
fi

if [[ "$WITH_SPIKE" == true ]]; then
  echo "==> Installing spike lab dependencies ..."
  python -m pip install -r spike/requirements.txt
fi

DEFAULT_SETTINGS_SRC="$ROOT/config/default-twim-settings.json"
DEFAULT_SETTINGS_DST="$ROOT/twim/users/_default/settings.json"
if [[ -f "$DEFAULT_SETTINGS_SRC" && ! -f "$DEFAULT_SETTINGS_DST" ]]; then
  echo "==> Seeding twim default settings ..."
  mkdir -p "$ROOT/twim/users/_default"
  cp "$DEFAULT_SETTINGS_SRC" "$DEFAULT_SETTINGS_DST"
fi

export INSTALL_ROOT="$ROOT"
export VOICE_DICTATION_WHISPER_DEVICE="${VOICE_DICTATION_WHISPER_DEVICE:-cpu}"
export VOICE_DICTATION_WHISPER_COMPUTE="${VOICE_DICTATION_WHISPER_COMPUTE:-int8}"

if [[ "$SKIP_WHISPER" != true ]]; then
  echo "==> Pre-downloading faster-whisper weights (from config/example-model-settings.json) ..."
  python "$ROOT/scripts/install_post_pip.py" prefetch-whisper
fi

if [[ "$SKIP_OLLAMA" != true ]] && command -v ollama >/dev/null 2>&1; then
  echo "==> Pulling Ollama cleanup model (from config/example-model-settings.json) ..."
  OLLAMA_MODEL="$(
    python "$ROOT/scripts/install_post_pip.py" print-ollama-cleanup-model
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
echo "    Path saved in .voice_dictation_venv. Next time: export CHEEAPPS_VENV=\"$VENV_DIR\" to skip the prompt."
echo "    Activate:  source \"$VENV_DIR/bin/activate\""
echo "    Pipeline CLI: python dictation_cli.py record-once --seconds 4 --no-type"
echo "    Settings:  ./start.sh  → http://127.0.0.1:8946/ (see banner printed by start.sh)"
echo "    Config:    ~/.voice-dictation/config.json (created on first agent run if missing)"
echo "    Windows:   install.bat (same flags; shared scripts/install_post_pip.py)"
