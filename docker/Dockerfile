# Dockerfile for grok-register on linuxserver/webtop:debian-xfce (headed / GUI)
# Provides a desktop environment with Chromium + the project running inside.

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

# ---- Base packages + Chinese locale + Python + Chromium ----
# webtop already ships Chromium (or Chrome). We ensure common paths exist.
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
        # ensure chromium is present under common paths that the app probes
        chromium \
        chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Generate zh_CN locale
RUN sed -i 's/# zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen zh_CN.UTF-8

# Symlink common chromium paths so DrissionPage/browser_runtime can find it
RUN set -eux; \
    for p in \
        /usr/bin/chromium \
        /usr/bin/chromium-browser \
        /usr/bin/google-chrome \
        /usr/bin/google-chrome-stable; do \
        if [ ! -e "$p" ]; then \
            if [ -x /usr/bin/chromium ]; then ln -sf /usr/bin/chromium "$p"; \
            elif [ -x /usr/bin/chromium-browser ]; then ln -sf /usr/bin/chromium-browser "$p"; \
            fi; \
        fi; \
    done; \
    # Also expose a stable name if chromium binary is chromium-browser
    if [ -x /usr/bin/chromium-browser ] && [ ! -x /usr/bin/chromium ]; then \
        ln -sf /usr/bin/chromium-browser /usr/bin/chromium; \
    fi; \
    # Print what we have for debugging
    ls -l /usr/bin/chromium* /usr/bin/google-chrome* 2>/dev/null || true

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
