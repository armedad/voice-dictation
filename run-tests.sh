#!/usr/bin/env bash
# Run unit/API pytest (tests/) and AI evals (evals/: jiwer STT + DeepEval cleanup).
#
# Prereq: ./install-tests.sh (or pip install -r requirements-dev.txt -r requirements-eval.txt).
# Ollama must be running for cleanup evals (requires_ollama); STT evals need local Whisper (slow).
#
# Venv: CHEEAPPS_VENV, else .voice_dictation_venv, else ./.venv
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

print_help() {
  cat <<'EOF'
run-tests.sh — run the voice-dictation MVP test suite

USAGE
  ./run-tests.sh [OPTIONS] [-- PYTEST_ARGS...]

  With no options: runs tests/ + evals/ (unit, API, STT WER, cleanup gates, GEval judge).

DEFAULTS
  DeepEval GEval judge tests run automatically (VOICE_DICTATION_RUN_GEVAL=1).
  Use --skip-geval to omit them (faster; deterministic cleanup gates still run).

OPTIONS
  -h, --help
      Show this help and exit.

  --unit-only
      Run only tests/ (fast deterministic pytest: chords, orchestrator mocks, twim API).
      Does not run evals/ (no Whisper, Ollama, or GEval).

  --evals-only
      Run only evals/ (STT WER + cleanup regression). Implies full eval behavior unless
      combined with --skip-slow or --skip-geval.

  --skip-slow
      Pass pytest -m "not slow" so faster-whisper WER cases in evals/ are skipped.
      Deterministic and GEval cleanup tests still run (unless --skip-geval).

  --skip-geval
      Skip DeepEval GEval judge tests (sets VOICE_DICTATION_SKIP_GEVAL=1).
      Deterministic cleanup substring gates still run when evals/ is included.

  -q, --quiet
      Quiet pytest output (same as pytest -q).

  -v, --verbose
      Verbose pytest output (same as pytest -v).

  --no-log
      Do not write logs/test-runs/pytest-<timestamp>.log or .xml (terminal only).

  --
      End of script options; remaining arguments are passed through to pytest
      (e.g. ./run-tests.sh -- -k test_health).

LOGGING (default)
  Each run writes a new file under logs/test-runs/ (not appended):
    pytest-YYYYMMDD-HHMMSS.log  — full terminal output (tee)
    pytest-YYYYMMDD-HHMMSS.xml  — JUnit XML for the same run

ENVIRONMENT
  CHEEAPPS_VENV
      Virtualenv directory. If unset, uses .voice_dictation_venv then ./.venv.

  VOICE_DICTATION_SKIP_GEVAL
      Set to 1 by --skip-geval. When set, GEval judge tests are skipped.

  VOICE_DICTATION_RUN_GEVAL
      Set to 1 by this script unless --skip-geval. GEval runs when unset or 1.

  OLLAMA_HOST / OLLAMA_PORT
      Ollama URL for cleanup evals (default 127.0.0.1:11434). Exits with an error if
      unreachable when evals/ is included (not needed for --unit-only).

EXAMPLES
  ./run-tests.sh
  ./run-tests.sh --unit-only -q
  ./run-tests.sh --evals-only --skip-geval
  ./run-tests.sh --skip-slow
  ./run-tests.sh -- --maxfail=1

PREREQUISITES
  ./install-tests.sh once. Ollama must be running for evals/ (errors if not); Whisper for slow STT.

SEE ALSO
  install-tests.sh, README.md (AI evals section), evals/eval_config.json
EOF
}

UNIT_ONLY=false
EVALS_ONLY=false
SKIP_SLOW=false
SKIP_GEVAL=false
NO_LOG=false
PYTEST_QUIET=()
EXTRA_PYTEST=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unit-only) UNIT_ONLY=true; shift ;;
    --evals-only) EVALS_ONLY=true; shift ;;
    --skip-slow) SKIP_SLOW=true; shift ;;
    --skip-geval) SKIP_GEVAL=true; shift ;;
    --no-log) NO_LOG=true; shift ;;
    --with-geval)
      echo "warning: --with-geval is deprecated (GEval runs by default). Use --skip-geval to omit." >&2
      shift
      ;;
    -q|--quiet) PYTEST_QUIET=(-q); shift ;;
    -v|--verbose) PYTEST_QUIET=(-v); shift ;;
    -h|--help) print_help; exit 0 ;;
    --)
      shift
      EXTRA_PYTEST=("$@")
      break
      ;;
    *)
      echo "error: unknown option: $1 (try ./run-tests.sh --help)" >&2
      exit 1
      ;;
  esac
done

if [[ "$UNIT_ONLY" == true && "$EVALS_ONLY" == true ]]; then
  echo "error: --unit-only and --evals-only are mutually exclusive" >&2
  exit 1
fi

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

PY="$VENV_DIR/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: no venv at $VENV_DIR (run ./install-tests.sh first)" >&2
  exit 1
fi

if ! "$PY" -c "import pytest" 2>/dev/null; then
  echo "error: pytest not installed in venv. Run: ./install-tests.sh" >&2
  exit 1
fi

MARKER_ARGS=()
if [[ "$SKIP_SLOW" == true ]]; then
  MARKER_ARGS+=(-m "not slow")
fi

if [[ "$SKIP_GEVAL" == true ]]; then
  export VOICE_DICTATION_SKIP_GEVAL=1
  export VOICE_DICTATION_RUN_GEVAL=0
else
  unset VOICE_DICTATION_SKIP_GEVAL || true
  export VOICE_DICTATION_RUN_GEVAL=1
fi

PATHS=()
if [[ "$EVALS_ONLY" == true ]]; then
  PATHS=(evals/)
elif [[ "$UNIT_ONLY" == true ]]; then
  PATHS=(tests/)
else
  PATHS=(tests/ evals/)
fi

echo "==> Voice dictation tests (venv: $VENV_DIR)"
echo "    Paths: ${PATHS[*]}"
[[ "$SKIP_SLOW" == true ]] && echo "    Markers: not slow"
if [[ "$SKIP_GEVAL" == true ]]; then
  echo "    GEval judge: skipped (--skip-geval)"
else
  echo "    GEval judge: enabled (default)"
fi

NEEDS_OLLAMA=false
for p in "${PATHS[@]}"; do
  if [[ "$p" == "evals/" || "$p" == evals/* ]]; then
    NEEDS_OLLAMA=true
    break
  fi
done

if [[ "$NEEDS_OLLAMA" == true ]]; then
  echo "    Checking Ollama (required for evals/)..."
  "$PY" -c "from evals.helpers import require_ollama_for_evals; require_ollama_for_evals()"
fi

PYTEST_CMD=("$PY" -m pytest "${PATHS[@]}")
if [[ ${#PYTEST_QUIET[@]} -gt 0 ]]; then
  PYTEST_CMD+=("${PYTEST_QUIET[@]}")
fi
if [[ ${#MARKER_ARGS[@]} -gt 0 ]]; then
  PYTEST_CMD+=("${MARKER_ARGS[@]}")
fi
if [[ ${#EXTRA_PYTEST[@]} -gt 0 ]]; then
  PYTEST_CMD+=("${EXTRA_PYTEST[@]}")
fi

if [[ "$NO_LOG" == true ]]; then
  exec "${PYTEST_CMD[@]}"
fi

LOG_DIR="$ROOT/logs/test-runs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/pytest-${STAMP}.log"
JUNIT_FILE="$LOG_DIR/pytest-${STAMP}.xml"
echo "    Log:   $LOG_FILE"
echo "    JUnit: $JUNIT_FILE"

set +e
"${PYTEST_CMD[@]}" --junitxml="$JUNIT_FILE" 2>&1 | tee "$LOG_FILE"
EXIT_CODE="${PIPESTATUS[0]}"
set -e
exit "$EXIT_CODE"
