#!/usr/bin/env bash
# Launch twim (FastAPI + static UI): always via run_combined_app.py.
# Runs stop.sh first to terminate any prior run_combined_app / uvicorn processes.
#
# Venv: CHEEAPPS_VENV, else first line of .voice_dictation_venv (from install.sh), else ./.venv.
#
# Usage:
#   ./start.sh                      # macOS: uvicorn + hotkeys; else: API + --reload
#   ./start.sh --port 8765          # or env VOICE_DICTATION_PORT
#   ./start.sh --no-reload          # (non-macOS only; macOS ignores reload when hotkeys on)
#   ./start.sh --skip-ollama-ensure
#   ./start.sh --skip-hotkey-agent  # API on main thread; --reload allowed (all OSes)
#   ./start.sh --help
#
# Ollama: if http://127.0.0.1:11434/api/tags is unreachable and `ollama` is on PATH,
# runs `ollama serve` in the background (logs: logs/ollama-serve.log).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -n "${CHEEAPPS_VENV:-}" ]]; then
  case "$CHEEAPPS_VENV" in
    /*) VENV_DIR="$CHEEAPPS_VENV" ;;
    *) VENV_DIR="$ROOT/$CHEEAPPS_VENV" ;;
  esac
elif [[ -f "$ROOT/.voice_dictation_venv" ]]; then
  VENV_DIR="$(head -n 1 "$ROOT/.voice_dictation_venv" | tr -d '\r')"
else
  VENV_DIR="$ROOT/.venv"
fi

PORT="${VOICE_DICTATION_PORT:-8946}"
RELOAD_ARGS=(--reload)
SKIP_OLLAMA_ENSURE=false
SKIP_HOTKEY_AGENT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      if [[ -z "${2:-}" ]]; then echo "error: --port needs a value" >&2; exit 1; fi
      PORT="$2"
      shift 2
      ;;
    --no-reload)
      RELOAD_ARGS=()
      shift
      ;;
    --skip-ollama-ensure)
      SKIP_OLLAMA_ENSURE=true
      shift
      ;;
    --skip-hotkey-agent)
      SKIP_HOTKEY_AGENT=true
      shift
      ;;
    -h|--help)
      sed -n '1,25p' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

echo "==> Stopping any existing dictation stack (stop.sh)"
bash "$ROOT/stop.sh"

ensure_ollama() {
  mkdir -p "$ROOT/logs"
  local host="${OLLAMA_HOST:-127.0.0.1}"
  local port="${OLLAMA_PORT:-11434}"
  local base="http://${host}:${port}"

  if command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 2 "${base}/api/tags" >/dev/null 2>&1; then
      echo "==> Ollama already reachable at ${base}"
      return 0
    fi
  else
    echo "warning: curl not found; skipping Ollama auto-start check." >&2
    return 0
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    echo "warning: Ollama not reachable at ${base} and 'ollama' not on PATH — start Ollama manually." >&2
    return 0
  fi

  echo "==> Ollama not reachable at ${base} — starting in background: ollama serve"
  echo "    (log file: $ROOT/logs/ollama-serve.log)"
  env OLLAMA_HOST="${OLLAMA_HOST:-$host}" OLLAMA_PORT="${OLLAMA_PORT:-$port}" \
    nohup ollama serve >>"$ROOT/logs/ollama-serve.log" 2>&1 &

  local i=0
  while [[ $i -lt 30 ]]; do
    if curl -fsS --max-time 2 "${base}/api/tags" >/dev/null 2>&1; then
      echo "==> Ollama is up at ${base}"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "warning: Ollama still not responding at ${base} after 30s — see $ROOT/logs/ollama-serve.log" >&2
}

VENV_PY="$VENV_DIR/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "error: missing $VENV_PY — run ./install.sh first (optional: CHEEAPPS_VENV=/path/to/venv ./install.sh)." >&2
  exit 1
fi

if [[ "$SKIP_OLLAMA_ENSURE" != true ]]; then
  ensure_ollama
fi

echo ""
echo "==> Voice dictation MVP (twim)  http://127.0.0.1:${PORT}/"
echo "    Entry: run_combined_app.py  |  venv: source \"$VENV_DIR/bin/activate\""
echo "    Pipeline CLI: python dictation_cli.py record-once --seconds 4 --no-type"
echo ""

COMBINED_ARGS=(--port "$PORT")
if [[ "$SKIP_HOTKEY_AGENT" == true ]]; then
  COMBINED_ARGS+=(--skip-hotkey-agent)
  if [[ ${#RELOAD_ARGS[@]} -gt 0 ]]; then
    COMBINED_ARGS+=(--reload)
  fi
elif [[ "$(uname -s)" == "Darwin" ]]; then
  if [[ ${#RELOAD_ARGS[@]} -gt 0 ]]; then
    echo "warning: --reload ignored on macOS with hotkeys (use --skip-hotkey-agent for reload)." >&2
  fi
else
  # Linux / Git Bash, etc.: embedded hotkeys unsupported → API-only + reload
  COMBINED_ARGS+=(--skip-hotkey-agent)
  if [[ ${#RELOAD_ARGS[@]} -gt 0 ]]; then
    COMBINED_ARGS+=(--reload)
  fi
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  exec env \
    VOICE_DICTATION_PORT="$PORT" \
    "$VENV_PY" "$ROOT/run_combined_app.py" "${COMBINED_ARGS[@]}"
fi

exec env \
  VOICE_DICTATION_PORT="$PORT" \
  "$VENV_PY" "$ROOT/run_combined_app.py" "${COMBINED_ARGS[@]}"
