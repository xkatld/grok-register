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
# Workdir for the project
WORKDIR /app/grok-register

# Copy requirements first for better layer caching
COPY requirements.txt ./

# Create venv and install Python deps
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# Make venv default
ENV PATH="/opt/venv/bin:${PATH}"

# Copy the rest of the project
COPY . .

# Ensure turnstilePatch exists (browser extension for cloudflare turnstile bypass)
# If empty in your build context, create a minimal placeholder dir so the app won't crash on add_extension
RUN mkdir -p turnstilePatch && ls -la turnstilePatch || true

# ---- Permissions (match PUID/PGID from env) ----
# linuxserver base runs as user abc (PUID=911, PGID=911 by default).
# We keep the app under /app and allow the container user to access it.
RUN chown -R abc:abc /app || true

# ---- Runtime user (from linuxserver base) ----
# The base image drops to abc at runtime; keep that behavior.
USER abc

# ---- Entrypoint / default command ----
# Start an XFCE desktop session (via s6 from linuxserver) and leave a terminal ready.
# Users will typically open a terminal inside the desktop and run:
#   cd /app/grok-register && python grok_register_ttk.py
# Or use CLI: python grok_register_ttk.py cli
#
# We provide a tiny convenience launcher that also pre-creates config.json if missing.
COPY --chown=abc:abc docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh || true

ENTRYPOINT ["/entrypoint.sh"]
# Default to a long-lived shell so the desktop stays up.
# You can override with: docker compose run --rm webtop bash -lc "cd /app/grok-register && python grok_register_ttk.py cli"
CMD ["sleep", "infinity"]
