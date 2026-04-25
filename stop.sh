#!/usr/bin/env bash
# Stop the combined dictation stack.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

kill_by_pattern() {
  local pattern="$1"
  local pids
  pids="$(pgrep -f "$pattern" || true)"
  if [[ -z "$pids" ]]; then
    echo "==> No processes matching: $pattern"
    return 0
  fi
  echo "==> Sending TERM to: $pattern ($pids)"
  kill $pids 2>/dev/null || true
  sleep 0.4
  pids="$(pgrep -f "$pattern" || true)"
  if [[ -n "$pids" ]]; then
    echo "==> Still running, sending KILL: $pattern ($pids)"
    kill -9 $pids 2>/dev/null || true
  fi
}

kill_by_pattern "run_combined_app.py"
kill_by_pattern "uvicorn app.main:app"
kill_by_pattern "run_hotkey_agent.py"
