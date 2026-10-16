#!/usr/bin/env bash
# ==============================================================================
# 1-Click Interactive YouTube Login Wizard
# Opens Google Sign-in in your browser to authorize YouTube upload access,
# saves credentials permanently, and immediately uploads pending videos.
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
echo "🔴 Launching Google OAuth 2.0 Authorization for YouTube"
echo "=================================================================="
echo "👉 Instructions:"
echo "   1. A browser window will open asking to sign into Google."
echo "   2. Choose your channel Google account ('IT'S GROWN UP TIME')."
echo "   3. Click 'Continue' / 'Allow' to grant YouTube upload permissions."
echo "   ✅ Credentials will be saved and all pending Shorts will publish!"
echo "=================================================================="

python3 "$DIR/connect_accounts.py" --login-youtube "$@"

echo ""
echo "🎉 Operation finished! Closing in 20 seconds (or press Enter to close now)..."
read -t 20 -p "" || true
