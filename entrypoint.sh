#!/usr/bin/env bash
# ==============================================================================
# Container Entrypoint for 24/7 Cloud YouTube & Social Media Agent
# ==============================================================================

set -e

echo "🚀 [Cloud Agent] Initializing 24/7 Headless Environment..."

# Clean up any stale X11 lock files
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

# Start Xvfb virtual framebuffer on DISPLAY=:99
echo "🖥️ [Cloud Agent] Starting Xvfb virtual display on DISPLAY=:99..."
Xvfb :99 -screen 0 1366x768x24 -ac +extension GLX +render -noreset &
export DISPLAY=:99
sleep 1

# Pre-flight security audit and vault permission hardening
echo "🛡️ [Cloud Agent] Hardening vault permissions..."
python3 -c "from security.security_guard import SecurityGuard; SecurityGuard().harden_permissions()" 2>/dev/null || true

# Start the master daily scheduler (runs scheduler, story watcher, web control center & telegram bot)
echo "🤖 [Cloud Agent] Launching Master Daily Scheduler & Web Control Center..."
exec python3 scheduler.py
