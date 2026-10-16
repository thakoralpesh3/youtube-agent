#!/usr/bin/env bash
# ==============================================================================
# 1-Click Interactive Social Login Wizard (Instagram & Facebook)
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

export DISPLAY="${DISPLAY:-:0}"

if [ -f "$DIR/.venv/bin/activate" ]; then
    source "$DIR/.venv/bin/activate"
elif [ -f "$DIR/venv/bin/activate" ]; then
    source "$DIR/venv/bin/activate"
fi

echo "=================================================================="
echo "🌐 Launching Firefox to Log in to Instagram & Facebook"
echo "=================================================================="
echo "👉 Instructions:"
echo "   1. Log into 'royal_chamunda_auto' on Instagram."
echo "   2. Log into 'Alpeshsinh Thakor' on Facebook."
echo "   3. Close the Firefox browser window when done."
echo "   ✅ Your sessions will be locked & permanently saved for auto-posting!"
echo "=================================================================="

python3 "$DIR/connect_accounts.py" --login-browser

echo ""
echo "🎉 Done! You can now close this terminal."
