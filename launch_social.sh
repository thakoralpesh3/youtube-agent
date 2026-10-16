#!/usr/bin/env bash
# ==============================================================================
# Social Media Stories AI - Dedicated Launcher (Instagram, Facebook, WhatsApp)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "============================================================"
echo "🌐 SOCIAL MEDIA STORIES & STATUS CREATOR"
echo "🏍️ Chamunda Automobile Parts & Services (Royal Enfield Only)"
echo "Target: Instagram, Facebook & WhatsApp (Stories & Status)"
echo "Autonomous Festival Marketing: ACTIVE"
echo "============================================================"

python3 "$SCRIPT_DIR/runner_ui.py" --platform social "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "⚠️ Process finished with exit code $EXIT_CODE."
    read -p "Press Enter to close..."
fi
