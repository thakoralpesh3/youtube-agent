#!/usr/bin/env bash
# Quick CLI Shortcut: Sync all Antigravity changes to GitHub
set -e

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python3"

if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python3"
fi

exec "$PYTHON_EXEC" "$SCRIPT_DIR/core/github_sync.py" "$@"
