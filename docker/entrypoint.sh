#!/usr/bin/env bash
# Entrypoint for the grok-register webtop image.
# - Ensures a writable work tree under /config (mapped by docker-compose)
# - Copies the app from the image (/app/grok-register) into a user-writable location if needed
# - Creates a default config.json if missing
# - Keeps the desktop session alive

set -euo pipefail

APP_SRC="/app/grok-register"
APP_DST="/config/grok-register"

# 1) Ensure destination exists and is writable
mkdir -p "$APP_DST"

# 2) If the destination is empty or looks like a fresh mount, seed it from the image copy
if [ ! -f "$APP_DST/grok_register_ttk.py" ]; then
  echo "[entrypoint] Seeding /config/grok-register from image..."
  # Copy the whole project tree (except git and caches) into the writable location
  rsync -a --delete \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$APP_SRC/" "$APP_DST/" || cp -a "$APP_SRC/." "$APP_DST/"
fi

# 3) Create a data directory for outputs (accounts, pending, cpa_auths, screenshots)
mkdir -p /config/grok-register-data/{cpa_auths,screenshots}

# 4) Provide a default config.json in the writable tree if none exists
if [ ! -f "$APP_DST/config.json" ]; then
  if [ -f "$APP_DST/config.example.json" ]; then
    cp "$APP_DST/config.example.json" "$APP_DST/config.json"
    echo "[entrypoint] Created default config.json from config.example.json"
  fi
fi

# 5) Make sure venv python is preferred inside the container
export PATH="/opt/venv/bin:${PATH}"

# 6) Friendly reminder on first terminal open
cat >/tmp/grok-register-hint.txt <<'HINT'
============================================================
grok-register 运行提示（有头模式）

1) 打开终端，进入项目目录：
   cd /config/grok-register

2) GUI 方式（推荐）：
   python grok_register_ttk.py

3) CLI 方式：
   python grok_register_ttk.py cli

4) 恢复 pending：
   python grok_register_ttk.py retry-pending <xxx.pending.jsonl>

5) 配置：
   - 用编辑器打开 /config/grok-register/config.json 修改
   - 启动 GUI 后可在界面中继续编辑并保存

注意：
- 浏览器窗口会在桌面内弹出（有头）
- 代理可在 config.json 的 "proxy" 填写，支持多行/逗号分隔
- 账号输出默认写在项目目录下的 accounts_*.txt
- 持久化数据在宿主机 ./data 目录下

如需使用宿主机网络代理，可在容器内设置：
   export http_proxy=http://host.docker.internal:7890
   export https_proxy=http://host.docker.internal:7890
============================================================
HINT

# 7) Keep the container up (desktop + s6 stays in foreground from base image)
# If CMD was overridden to "sleep infinity", this does nothing harmful.
if [ "${1:-}" = "sleep" ] && [ "${2:-}" = "infinity" ]; then
  exec sleep infinity
fi

# Otherwise, exec whatever was passed (e.g. bash)
exec "$@"
