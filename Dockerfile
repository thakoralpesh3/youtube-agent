# ==============================================================================
# 24/7 Autonomous YouTube & Social Media Agent - Cloud Dockerfile
# Optimized for running headlessly 24/7 on Oracle Cloud Free Tier, AWS, or VPS
# ==============================================================================

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DISPLAY=:99 \
    HEADLESS_BROWSER=1

# Install system utilities, multimedia codecs, headless Xvfb virtual display, and Firefox
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    firefox-esr \
    xvfb \
    fonts-liberation \
    fonts-dejavu-core \
    curl \
    wget \
    tar \
    bzip2 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Geckodriver for headless Firefox automation
RUN GECKO_VERSION="v0.35.0" && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        GECKO_FILE="geckodriver-${GECKO_VERSION}-linux64.tar.gz"; \
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
        GECKO_FILE="geckodriver-${GECKO_VERSION}-linux-aarch64.tar.gz"; \
    fi && \
    wget -q "https://github.com/mozilla/geckodriver/releases/download/${GECKO_VERSION}/${GECKO_FILE}" -O /tmp/gecko.tar.gz && \
    tar -xzf /tmp/gecko.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/geckodriver && \
    rm /tmp/gecko.tar.gz

WORKDIR /app

# Copy dependency manifest and install Python packages
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . /app/

# Ensure required directories exist and permissions are hardened
RUN mkdir -p /app/output /app/Story /app/assets/browser_profiles && \
    chmod 700 /app/output /app/assets/browser_profiles && \
    chmod +x /app/entrypoint.sh 2>/dev/null || true

EXPOSE 8080

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
