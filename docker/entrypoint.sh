#!/bin/bash
set -euo pipefail

APP_SRC="/app/grok-register"
APP_DST="/config/grok-register"
DATA_DIR="/config/grok-register-data"

log() {
  echo "[grok-register-init] $*"
}

# --- 1. Seed the project into the persistent /config location ---
if [ -d "$APP_SRC" ]; then
  mkdir -p "$APP_DST"

  if [ ! -f "$APP_DST/grok_register_ttk.py" ]; then
    log "Seeding writable copy from $APP_SRC to $APP_DST ..."

    # Use simple cp -a (portable, no rsync dependency).
    # The source dir in the image is guaranteed by the Dockerfile build check.
    if cp -a "$APP_SRC/." "$APP_DST/"; then
      log "Copy completed."
    else
      log "ERROR: Failed to copy project files from $APP_SRC to $APP_DST"
      ls -la "$APP_SRC" || true
      ls -la "$APP_DST" || true
    fi
  else
    log "Writable copy already exists at $APP_DST (skipping seed)"
  fi
else
  log "ERROR: $APP_SRC not found inside the image. Did the build use the correct context?"
  log "Listing /app:"
  ls -la /app || true
fi

# After possible copy, verify the critical file
if [ ! -f "$APP_DST/grok_register_ttk.py" ]; then
  log "WARNING: $APP_DST/grok_register_ttk.py still missing after seeding attempt."
  log "Contents of $APP_DST (if any):"
  ls -la "$APP_DST" 2>/dev/null || true
else
  log "Verified: $APP_DST/grok_register_ttk.py exists."
fi

# --- 2. Prepare persistent data dirs (optional extra mount) ---
mkdir -p "$DATA_DIR"/{cpa_auths,screenshots}
log "Ensured data directories in $DATA_DIR"

# --- 3. Provide a default config.json if none exists ---
if [ -d "$APP_DST" ] && [ ! -f "$APP_DST/config.json" ]; then
  if [ -f "$APP_DST/config.example.json" ]; then
    cp "$APP_DST/config.example.json" "$APP_DST/config.json"
    log "Created default config.json from config.example.json"
    # Fix permissions so the desktop user (abc or PUID) can edit it
    chown -R "${PUID:-1000}:${PGID:-1000}" "$APP_DST/config.json" 2>/dev/null || true
  fi
fi

# Make sure the whole writable tree is owned by the target user (best effort)
if [ -d "$APP_DST" ]; then
  chown -R "${PUID:-1000}:${PGID:-1000}" "$APP_DST" 2>/dev/null || true
fi
chown -R "${PUID:-1000}:${PGID:-1000}" "$DATA_DIR" 2>/dev/null || true

# --- 4. Write a one-time hint to the user's Desktop (if Desktop dir exists or can be created) ---
# linuxserver webtop typically creates home under /config/home/<user> based on PUID.
# We try $HOME first (if set and points inside /config), then common fallbacks.
try_write_desktop_hint() {
  local target_dir=""
  if [ -n "${HOME:-}" ] && [ -d "$HOME" ]; then
    target_dir="$HOME/Desktop"
  fi
  # Fallbacks for common webtop layouts
  for candidate in \
    "/config/home/abc/Desktop" \
    "/config/home/$(id -u 2>/dev/null || echo 1000)/Desktop" \
    "/config/Desktop"; do
    if [ -z "$target_dir" ] && [ -d "$(dirname "$candidate" 2>/dev/null || true)" ]; then
      target_dir="$candidate"
      break
    fi
  done

  if [ -n "$target_dir" ]; then
    mkdir -p "$target_dir" 2>/dev/null || true
    if [ -d "$target_dir" ]; then
      cat > "$target_dir/grok-register-README.txt" <<'DESK'
grok-register 一键部署（有头模式）

项目位置（推荐从这里运行）：
  /config/grok-register

常用命令：
  cd /config/grok-register
  python grok_register_ttk.py          # 启动 GUI（推荐）
  python grok_register_ttk.py cli      # 命令行模式

配置：
  编辑 /config/grok-register/config.json

输出文件（账号、pending、CPA 等）默认写在项目目录下。
持久化目录：宿主机 docker/data/

代理：
  在 config.json 的 "proxy" 字段填写，支持多行/逗号/分号分隔。
  或在终端临时设置：
    export http_proxy=http://host.docker.internal:7890
    export https_proxy=http://host.docker.internal:7890

注意：
- 这是容器内的有头浏览器，会在 XFCE 桌面弹出窗口。
- 如需更新项目代码，重建镜像并重启容器（或手动 rsync /app 到 /config）。
DESK
      chown -R "${PUID:-1000}:${PGID:-1000}" "$target_dir/grok-register-README.txt" 2>/dev/null || true
      log "Desktop hint written to $target_dir/grok-register-README.txt"
    fi
  else
    log "Could not determine Desktop location for hint (will rely on /tmp hint)"
  fi
}

# Also write a global hint in /tmp that is always visible from any terminal
cat > /tmp/grok-register-hint.txt <<'HINT'
============================================================
grok-register 运行提示（有头模式）

项目位置（推荐）：
  cd /config/grok-register

启动：
  python grok_register_ttk.py          # GUI（推荐）
  python grok_register_ttk.py cli      # CLI

配置在 /config/grok-register/config.json
输出和 pending 在项目目录下。
持久化数据对应宿主机 ./data 目录。
============================================================
HINT

try_write_desktop_hint || true

# --- 5. Hand off to linuxserver s6 init ---
# This is critical: the base image expects /init to start all services (desktop, nginx for :3000, etc.)
log "Handing off to /init (linuxserver s6 supervisor)..."
exec /init "$@"
