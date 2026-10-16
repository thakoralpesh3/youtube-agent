#!/usr/bin/env bash
# ==============================================================================
# YouTube & Social AI Agent — 1-Click Connection & Account Manager
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Activate Python Virtual Environment
if [ -d "$DIR/.venv" ]; then
    source "$DIR/.venv/bin/activate"
elif [ -d "$DIR/venv" ]; then
    source "$DIR/venv/bin/activate"
else
    echo "❌ Error: Virtual environment not found at .venv or venv."
    exit 1
fi

echo "🚀 Launching Account Connection Manager..."
python3 connect_accounts.py "$@"

echo ""
read -p "Press [Enter] to exit..."
