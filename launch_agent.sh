#!/usr/bin/env bash
# ==============================================================================
# YouTube Automation Agent - Interactive Terminal Launcher
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

python3 "$SCRIPT_DIR/runner_ui.py" "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "⚠️ Process finished with exit code $EXIT_CODE."
    read -p "Press Enter to close..."
fi
