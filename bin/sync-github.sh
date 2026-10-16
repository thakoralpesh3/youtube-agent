#!/usr/bin/env bash
# Quick CLI Shortcut: Sync all Antigravity changes to GitHub
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python3"

if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python3"
fi

exec "$PYTHON_EXEC" "$SCRIPT_DIR/core/github_sync.py" "$@"
