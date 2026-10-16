#!/usr/bin/env bash
# ==============================================================================
# Cloudflare Tunnel Setup for Free, Secure HTTPS Online Access
# Exposes Web Control Center to your phone with zero router port forwarding
# ==============================================================================

set -e

echo "=========================================================================="
echo "🔒 FREE CLOUDFLARE HTTPS TUNNEL SETUP (ZERO PORT FORWARDING)"
echo "=========================================================================="
echo ""
echo "This script installs Cloudflare Tunnel to give your agent a secure HTTPS URL"
echo "so you can access your dashboard from your smartphone anywhere in the world."
echo ""

ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
    CLOUDFLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    CLOUDFLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
else
    CLOUDFLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
fi

if ! command -v cloudflared &> /dev/null; then
    echo "⬇️ Downloading cloudflared..."
    wget -q "$CLOUDFLARED_URL" -O /tmp/cloudflared
    chmod +x /tmp/cloudflared
    sudo mv /tmp/cloudflared /usr/local/bin/cloudflared 2>/dev/null || mv /tmp/cloudflared /usr/local/bin/cloudflared
    echo "✅ cloudflared installed successfully in /usr/local/bin/cloudflared."
else
    echo "✅ cloudflared is already installed."
fi

echo ""
echo "🚀 Starting Cloudflare Quick Tunnel to port 8080..."
echo "Your free HTTPS address will appear below:"
echo "--------------------------------------------------------------------------"
cloudflared tunnel --url http://localhost:8080
