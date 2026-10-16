#!/usr/bin/env bash
# ==============================================================================
# Cloud VPS Auto-Setup Script for YouTube & Social Media AI Agent
# Run on fresh Ubuntu 22.04 / 24.04 (e.g. Oracle Cloud Free Tier, DigitalOcean, AWS)
# ==============================================================================

set -e

echo "=========================================================================="
echo "🚀 AUTONOMOUS YOUTUBE & SOCIAL MEDIA AGENT - 24/7 CLOUD HOST PROVISIONER"
echo "=========================================================================="

if [ "$EUID" -ne 0 ]; then
  echo "⚠️ Please run as root or with sudo: sudo bash cloud_setup.sh"
  exit 1
fi

echo "📦 1. Updating APT repositories and installing core packages..."
apt-get update -y
apt-get install -y \
    curl \
    wget \
    git \
    rsync \
    tar \
    bzip2 \
    ffmpeg \
    imagemagick \
    firefox-esr \
    xvfb \
    fonts-liberation \
    fonts-dejavu-core \
    python3 \
    python3-pip \
    python3-venv

echo "🐳 2. Installing Docker & Docker Compose..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl enable docker
    systemctl start docker
    echo "✅ Docker installed successfully."
else
    echo "✅ Docker already installed."
fi

# Add current user to docker group if applicable
TARGET_USER=${SUDO_USER:-$USER}
if [ -n "$TARGET_USER" ] && [ "$TARGET_USER" != "root" ]; then
    usermod -aG docker "$TARGET_USER" 2>/dev/null || true
fi

echo "🦎 3. Installing Geckodriver for Headless Firefox Automation..."
GECKO_VERSION="v0.35.0"
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
    GECKO_FILE="geckodriver-${GECKO_VERSION}-linux64.tar.gz"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    GECKO_FILE="geckodriver-${GECKO_VERSION}-linux-aarch64.tar.gz"
else
    GECKO_FILE="geckodriver-${GECKO_VERSION}-linux64.tar.gz"
fi

wget -q "https://github.com/mozilla/geckodriver/releases/download/${GECKO_VERSION}/${GECKO_FILE}" -O /tmp/gecko.tar.gz
tar -xzf /tmp/gecko.tar.gz -C /usr/local/bin
chmod +x /usr/local/bin/geckodriver
rm /tmp/gecko.tar.gz
echo "✅ Geckodriver installed in /usr/local/bin/geckodriver."

echo "🔒 4. Configuring Firewall (UFW) to allow Web Dashboard Port 8080..."
if command -v ufw &> /dev/null; then
    ufw allow 8080/tcp 2>/dev/null || true
    echo "✅ Port 8080 opened in UFW."
fi

echo "=========================================================================="
echo "🎉 CLOUD SERVER PROVISIONING COMPLETE!"
echo ""
echo "Next step:"
echo "From your laptop, run: bash deploy_to_cloud.sh"
echo "to migrate your credentials, browser logins, and start the 24/7 agent!"
echo "=========================================================================="
