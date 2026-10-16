#!/usr/bin/env bash
# ==============================================================================
# Upload Pending Shorts to YouTube
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "============================================================"
echo "📤 YOUTUBE PENDING CONTENT UPLOADER"
echo "Target: Uploading all ready generated videos to YouTube"
echo "============================================================"

python3 "$SCRIPT_DIR/upload_to_youtube.py" "$@"

echo ""
read -p "Press [Enter] to close..."
