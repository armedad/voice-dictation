#!/usr/bin/env bash
# Commit all changes in this repo and push to origin. Pass the commit message as arguments
# (one quoted string or multiple words joined with spaces). No other text is added to the commit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <commit message>" >&2
  exit 1
fi

MSG="$*"
if [[ -z "${MSG// }" ]]; then
  echo "error: empty commit message" >&2
  exit 1
fi

git add -A

if git diff --cached --quiet; then
  echo "Nothing to commit."
  exit 0
fi

printf '%s\n' "$MSG" | git commit -F -
git push
