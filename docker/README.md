# 一键部署（有头 / GUI 可见浏览器）

本目录提供基于 `linuxserver/webtop:debian-xfce` 的 Docker 方案，浏览器窗口在桌面内可见，适合观察与调试。

## 快速开始

```bash
cd docker

# 1) 启动
docker compose up -d

# 2) 打开浏览器访问桌面
#    http://你的宿主机IP:3000
#    默认用户/密码见 linuxserver/webtop 文档（首次可设置）

# 3) 在桌面内打开终端，执行：
cd /config/grok-register
python grok_register_ttk.py
```

## 目录结构

```
docker/
├── Dockerfile
├── docker-compose.yml
└── entrypoint.sh
```

- `docker-compose.yml`：暴露 3000 端口，挂载：
  - `./webtop-config` → `/config`（桌面/用户配置持久化）
  - `./data` → `/config/grok-register-data`（账号、pending、cpa_auths 等持久化）
- 应用源码会从镜像内 `/app/grok-register` 拷贝到 `/config/grok-register`（可写位置）
- 首次启动会基于 `config.example.json` 生成默认 `config.json`

## 浏览器与有头

- 容器已安装 Chromium，并创建了常见路径软链接：
  - `/usr/bin/chromium`、`chromium-browser`、`google-chrome` 等
- `cpa_headless` 默认 `false`，注册浏览器与 CPA 授权浏览器都会以有头方式启动
- 如需强制无头，仅改配置即可，不影响容器本身

## 代理与网络

- 代理在 `config.json` 中配置（支持多行/逗号/分号分隔）
- 如需让容器走宿主机代理，可在容器终端内设置：
  ```bash
  export http_proxy=http://host.docker.internal:7890
  export https_proxy=http://host.docker.internal:7890
  ```
- 也可把代理直接写进 `config.json` 的 `proxy` 字段

## 持久化与输出

- 账号输出：`/config/grok-register/accounts_*.txt`
- 邮箱凭证：`/config/grok-register/mail_credentials.txt`
- Pending：`/config/grok-register/*.pending.jsonl`
- CPA 导出：`/config/grok-register/cpa_auths/`
- 以上路径映射到宿主机 `./data`，便于取回

## 升级与重建

```bash
# 拉取最新 webtop 镜像 + 重建本镜像
docker compose build --no-cache
docker compose up -d
```

## 常见问题

- 没有看到浏览器窗口：确认是“有头”配置（`cpa_headless=false`，主注册流程默认有头）
- 中文显示异常：容器已安装 `fonts-wqy-*`，一般无需额外操作
- 内存不足：`shm_size` 建议 2GB 以上
- 连接代理失败：检查 `proxy` 字段格式，或在容器内测试 `curl -I https://grok.com`
