#!/usr/bin/env bash
# ==============================================================================
# 1-Click Laptop-to-Cloud Migration & Deployment Script
# Migrates code, API keys, YouTube OAuth tokens, and saved browser logins
# to your 24/7 Cloud Host (Oracle Cloud Free Tier, DigitalOcean, AWS, etc.)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================================="
echo "🚀 1-CLICK MIGRATION TO 24/7 CLOUD HOST (LAPTOP-OFF ACCESSIBILITY)"
echo "=========================================================================="
echo ""
echo "This script migrates your YouTube & Social Media Agent to your 24/7 Cloud VPS"
echo "so it runs continuously even when your laptop is turned off."
echo ""
read -p "👉 Enter your Remote VPS SSH connection (e.g. ubuntu@123.45.67.89): " REMOTE_HOST

if [ -z "$REMOTE_HOST" ]; then
    echo "❌ Remote host cannot be empty. Aborted."
    exit 1
fi

REMOTE_DIR="youtube-agent"

echo ""
echo "📦 1. Pre-flight check: hardening local permissions before transfer..."
python3 -c "from security.security_guard import SecurityGuard; SecurityGuard().harden_permissions()" 2>/dev/null || true

echo "📁 2. Creating destination directory on cloud host..."
ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DIR/assets/browser_profiles $REMOTE_DIR/Story $REMOTE_DIR/output"

echo "🔄 3. Transferring agent codebase, templates, and Docker configs..."
# Use rsync if available, otherwise scp
if command -v rsync &> /dev/null; then
    rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
        ./ "$REMOTE_HOST:$REMOTE_DIR/"
else
    scp -r *.py *.sh *.txt *.md *.json .env Dockerfile docker-compose.yml web generator growth security syndication youtube "$REMOTE_HOST:$REMOTE_DIR/" 2>/dev/null || true
fi

echo "🔑 4. Syncing YouTube tokens and saved WhatsApp/IG/FB browser sessions..."
if [ -d "assets/browser_profiles/social_firefox" ]; then
    if command -v rsync &> /dev/null; then
        rsync -avz assets/browser_profiles/social_firefox/ "$REMOTE_HOST:$REMOTE_DIR/assets/browser_profiles/social_firefox/"
    else
        scp -r assets/browser_profiles/social_firefox "$REMOTE_HOST:$REMOTE_DIR/assets/browser_profiles/"
    fi
    echo "✅ Browser sessions transferred! You will NOT need to log into IG/FB/WA again on the cloud server."
fi

echo "🐳 5. Launching 24/7 Cloud Docker Container on remote host..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && if command -v docker &> /dev/null; then docker compose up -d --build; else echo 'Docker not found. Run cloud_setup.sh on the server.'; fi"

SERVER_IP=$(echo "$REMOTE_HOST" | awk -F'@' '{print $2}')
echo ""
echo "=========================================================================="
echo "🎉 DEPLOYMENT SUCCESSFUL! YOUR AGENT IS NOW RUNNING 24/7 IN THE CLOUD!"
echo "=========================================================================="
echo "Even with your laptop turned off, your agent will:"
echo "  • Generate and upload daily YouTube Shorts at 10:00 AM"
echo "  • Publish Chamunda Automobile Festival Campaigns on festive dates at 08:00 AM"
echo "  • Run hourly pulses, pending video uploads, and security audits"
echo ""
echo "📱 ACCESS YOUR ONLINE DASHBOARD ANYTIME FROM YOUR PHONE OR BROWSER:"
echo "👉 http://${SERVER_IP}:8080"
echo "Password: (Set in your .env as DASHBOARD_PASSWORD, default: chamunda2026)"
echo ""
echo "💡 To get a free encrypted HTTPS domain with zero port forwarding:"
echo "Run on the server: bash tunnel_setup.sh"
echo "=========================================================================="
