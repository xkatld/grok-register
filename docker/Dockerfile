# Dockerfile for grok-register on linuxserver/webtop:debian-xfce (headed / GUI)
# Provides a desktop environment with Google Chrome + the project running inside.

FROM lscr.io/linuxserver/webtop:debian-xfce

LABEL maintainer="grok-register docker"
LABEL description="Grok Register (headed) running inside linuxserver/webtop with XFCE desktop"

# ---- Environment ----
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # DrissionPage / Chromium friendly flags for container
    CHROME_NO_SANDBOX=1

# ---- Base packages + Chinese locale + Python + Google Chrome ----
# webtop base may include a browser, but we explicitly install Google Chrome stable
# because Chromium has compatibility issues in real testing (user reported).
RUN apt-get update && apt-get install -y --no-install-recommends \
        locales \
        ca-certificates \
        curl \
        gnupg \
        git \
        build-essential \
        python3 \
        python3-venv \
        python3-pip \
        python3-tk \
        x11-utils \
        xvfb \
        fonts-wqy-zenhei \
        fonts-wqy-microhei \
        libglib2.0-0 \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libasound2 \
        libatspi2.0-0 \
        fonts-liberation \
        libappindicator3-1 \
        xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Generate zh_CN locale
RUN sed -i 's/# zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen zh_CN.UTF-8

# ---- Install Google Chrome stable ----
# Official Google Chrome is required; Chromium has compatibility issues in practice.
# We add Google's apt repo and install the stable channel.
RUN curl -fsSL https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-linux-signing-key.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux-signing-key.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/google-chrome-stable /usr/bin/google-chrome \
    && ln -sf /usr/bin/google-chrome-stable /usr/bin/chromium \
    && ln -sf /usr/bin/google-chrome-stable /usr/bin/chromium-browser \
    && echo "Google Chrome installed:" && /usr/bin/google-chrome-stable --version 2>/dev/null || true

# ---- Symlink common paths for DrissionPage/browser_runtime discovery ----
# Ensure all probed paths resolve to Google Chrome.
RUN set -eux; \
    for p in \
        /usr/bin/chromium \
        /usr/bin/chromium-browser \
        /usr/bin/google-chrome \
        /usr/bin/google-chrome-stable; do \
        if [ ! -e "$p" ] || [ ! -x "$p" ]; then \
            if [ -x /usr/bin/google-chrome-stable ]; then ln -sf /usr/bin/google-chrome-stable "$p"; fi; \
        fi; \
    done; \
    # Force canonical names to Google Chrome stable when present
    if [ -x /usr/bin/google-chrome-stable ]; then \
        ln -sf /usr/bin/google-chrome-stable /usr/bin/google-chrome 2>/dev/null || true; \
        ln -sf /usr/bin/google-chrome-stable /usr/bin/chromium 2>/dev/null || true; \
        ln -sf /usr/bin/google-chrome-stable /usr/bin/chromium-browser 2>/dev/null || true; \
    fi; \
    # Final debug listing
    ls -l /usr/bin/chromium* /usr/bin/google-chrome* 2>/dev/null || true; \
    /usr/bin/google-chrome --version 2>/dev/null || true

# ---- App setup ----
# Workdir for the project (source lives here in the image)
WORKDIR /app/grok-register

# Copy requirements first for better layer caching
COPY requirements.txt ./

# Create venv and install Python deps
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# Make venv default
ENV PATH="/opt/venv/bin:${PATH}"

# Copy the rest of the project (this brings grok_register_ttk.py, cpa_xai/, turnstilePatch/, etc.)
COPY . .

# Build-time sanity check: ensure the main entry script is present in the image.
# If this fails, the build context was wrong (e.g. building from docker/ dir instead of project root).
RUN set -eux; \
    ls -la /app/grok-register/grok_register_ttk.py || (echo 'ERROR: grok_register_ttk.py not found in image. Check build context.'; ls -la /app/grok-register || true; exit 1)

# Ensure turnstilePatch dir exists (for Turnstile bypass extension).
# If your build context has files in turnstilePatch/, they will be copied by the previous step.
RUN mkdir -p turnstilePatch && ls -la turnstilePatch || true

# ---- Permissions ----
# The linuxserver base will manage ownership via PUID/PGID at runtime.
# We ensure the app tree is readable.
RUN chown -R abc:abc /app/grok-register || true

COPY --chown=root:root docker/entrypoint.sh /tmp/raw.sh
RUN set -eux; \
    { \
      printf '#!/bin/bash\n'; \
      printf 'set -euo pipefail\n'; \
      tail -n +3 /tmp/raw.sh | tr -d '\r'; \
    } > /entrypoint.sh && \
    chmod +x /entrypoint.sh && \
    rm -f /tmp/raw.sh
ENTRYPOINT ["/entrypoint.sh"]

# No custom CMD — let the base image define the default desktop/web services.
# Users open a terminal in the XFCE desktop (via :3000) and run the app from /config/grok-register.
