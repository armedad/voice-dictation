#!/usr/bin/env bash
# Launch the Voice Dictation MVP settings web app (ai-frame / FastAPI).
#
# Usage:
#   ./start.sh                      # bind 127.0.0.1:8000, --reload; ensure Ollama is up
#   ./start.sh --port 8765          # override port (or env VOICE_DICTATION_PORT)
#   ./start.sh --no-reload
#   ./start.sh --skip-ollama-ensure  # do not check/start Ollama
#   ./start.sh --help
#
# Ollama: if http://127.0.0.1:11434/api/tags is unreachable and `ollama` is on PATH,
# runs `ollama serve` in the background (logs: logs/ollama-serve.log). Override host/port
# with OLLAMA_HOST / OLLAMA_PORT when matching your settings UI URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${VOICE_DICTATION_PORT:-8000}"
RELOAD_ARGS=(--reload)
SKIP_OLLAMA_ENSURE=false

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
    -h|--help)
      sed -n '1,28p' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

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
  # Pass through OLLAMA_* if already set in the environment; otherwise bind defaults via host/port.
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
  echo "warning: Ollama still not responding at ${base} after 30s — see $ROOT/logs/ollama-serve.log (port in use or daemon failed)." >&2
}

VENV_PY="$ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "error: missing $VENV_PY — run ./install.sh first." >&2
  exit 1
fi

if [[ "$SKIP_OLLAMA_ENSURE" != true ]]; then
  ensure_ollama
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Voice Dictation MVP — settings + dictation API (one server)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Activate this venv in another terminal (for run_agent.py / pip):"
echo "    source \"$ROOT/.venv/bin/activate\""
echo ""
echo "  Open the settings / chat UI in your browser:"
echo "    http://127.0.0.1:${PORT}/"
echo ""
echo "  First visit: create a local account in the UI (ai-frame stores data under users/)."
echo ""
echo "  In the UI (logged in): header button \"Dictate 10s\" records 10s, then types"
echo "  cleaned text into whichever app/field has keyboard focus (macOS; Accessibility)."
echo "  CLI alternative: source .venv/bin/activate && python run_agent.py record-once …"
echo ""
echo "  Local (Ollama): Settings → Models → URL should match http://127.0.0.1:11434 (use Default)."
echo "  Ollama logs (if started by this script): $ROOT/logs/ollama-serve.log"
echo ""
echo "  Mic capture needs PortAudio on macOS (install.sh installs via brew when possible)."
echo ""
echo "  Press Ctrl+C in this terminal to stop the FastAPI server (background Ollama keeps running)."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$ROOT/ai-frame"
exec "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" "${RELOAD_ARGS[@]}"
