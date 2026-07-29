# 一键部署（有头 / GUI 可见浏览器）

本目录提供基于 `linuxserver/webtop:debian-xfce` 的 Docker 方案，浏览器窗口在桌面内可见，适合观察与调试。

## 快速开始（关键步骤）

**必须在 `docker/` 目录下执行，并且带 `--build`**：

```bash
cd docker

# 完整重建（推荐第一次或代码有更新时）
docker compose down
docker compose build --no-cache
docker compose up -d

# 或者简写（如果之前已经 build 过）
docker compose up -d --build
```

然后：

1. 浏览器打开桌面：`http://你的宿主机IP:3000`
2. 在 XFCE 桌面里打开终端（Terminal / xfce4-terminal）
3. 执行：

```bash
cd /config/grok-register
python grok_register_ttk.py
```

### 为什么之前会报 “No such file or directory”？

你看到的错误：

```
bash: cd: /config/grok-register: No such file or directory
python: can't open file '/config/Desktop/grok_register_ttk.py'
```

说明你当前运行的容器**不是我们自定义构建的镜像**，而是直接跑的 `linuxserver/webtop:debian-xfce`（或者旧的缓存镜像），里面根本没有把项目代码拷贝进去。

常见原因：
- 在错误的目录（项目根目录）执行了 `docker compose up`
- 执行时没有加 `--build`
- 之前用你自己贴的那个只有 `image: linuxserver/webtop...` 的 compose 文件启动过
- 构建上下文错误（从 `docker/` 目录直接 `docker build .`）

解决方案：**删除旧容器，用正确方式重新 build**（见上面的命令）。

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

- 容器已安装 **Google Chrome 稳定版**（`google-chrome-stable`），并创建了常见路径软链接：
  - `/usr/bin/google-chrome`、`google-chrome-stable`、`chromium`、`chromium-browser`
- 所有路径均指向 Google Chrome 稳定版（实际测试中 Chromium 存在兼容性问题）
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
