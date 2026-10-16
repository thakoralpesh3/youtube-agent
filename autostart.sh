#!/usr/bin/env bash
# ==============================================================================
# YouTube & Social Media Agent - Laptop Startup Auto-Activation Script
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure only one instance of the autostart daemon runs at any time
LOCK_FILE="/tmp/youtube_agent_autostart.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "ℹ️ YouTube Agent background daemon is already running."
    # When the user logs in to desktop, display the status banner so notifications are always visible!
    if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
        source "$SCRIPT_DIR/.venv/bin/activate"
    fi
    python3 -c "
try:
    from growth.notifier import notifier
    notifier.send_desktop_login_banner()
except Exception:
    import subprocess
    subprocess.run(['notify-send', '-a', 'YouTube & Social AI', '-u', 'normal', '🤖 YouTube & Social Media AI Active', 'Background daemon active and running.'], check=False)
" 2>/dev/null || true
    exit 0
fi


LOG_FILE="$SCRIPT_DIR/output/autostart.log"
mkdir -p "$SCRIPT_DIR/output"

echo "============================================================" >> "$LOG_FILE"
echo "🚀 [$(date '+%Y-%m-%d %H:%M:%S')] Laptop Started - Activating Agent Daemon" >> "$LOG_FILE"
echo "============================================================" >> "$LOG_FILE"

# Function to verify internet connectivity via HTTPS or IPv4 ping
check_network() {
    curl -s --head --connect-timeout 2 https://www.google.com >/dev/null 2>&1 || ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1
}

# Wait for network connection on boot (up to 30 seconds)
MAX_WAIT=30
WAIT_COUNT=0
while ! check_network; do
    echo "⏳ Waiting for network connection... ($WAIT_COUNT/$MAX_WAIT)" >> "$LOG_FILE"
    sleep 2
    WAIT_COUNT=$((WAIT_COUNT + 2))
    if [ "$WAIT_COUNT" -ge "$MAX_WAIT" ]; then
        echo "⚠️ Network not yet available after $MAX_WAIT seconds. Proceeding to background retry..." >> "$LOG_FILE"
        break
    fi
done

# Activate virtual environment
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Dispatch accurate startup desktop banner via resilient notifier
python3 -c "
try:
    from growth.notifier import notifier
    notifier.send_desktop_login_banner()
except Exception:
    pass
" 2>/dev/null || true


# Enforce Cybersecurity Vault Hardening & Integrity Audit on Startup
echo "🛡️ [$(date '+%Y-%m-%d %H:%M:%S')] Enforcing Cybersecurity Vault Hardening & File Permissions..." >> "$LOG_FILE"
python3 -c "from security.security_guard import SecurityGuard; SecurityGuard().run_security_audit(auto_harden=True, alert_on_threat=True)" >> "$LOG_FILE" 2>&1 || true

# Start master autonomous scheduler daemon
# scheduler.py automatically checks and runs both YouTube & Social agents in the background
# strictly 1 time per day on laptop startup (with persistent daily limiters).
echo "🤖 [$(date '+%Y-%m-%d %H:%M:%S')] Starting master background automation daemon (YouTube & Social AI)..." >> "$LOG_FILE"
exec python3 "$SCRIPT_DIR/scheduler.py" >> "$LOG_FILE" 2>&1

