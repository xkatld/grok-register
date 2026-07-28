# 一键部署（有头 / GUI 可见浏览器）- 根目录入口

本项目现已提供 Docker 一键部署方案，基于 `linuxserver/webtop:debian-xfce`，浏览器窗口在 XFCE 桌面内可见，便于观察与调试。

## 快速开始（3 步）

```bash
# 1) 进入 docker 目录
cd docker

# 2) 启动容器（首次会拉取 webtop 镜像并构建）
docker compose up -d

# 3) 浏览器打开桌面
#    http://你的宿主机IP:3000
#    在桌面内打开终端，运行：
cd /config/grok-register
python grok_register_ttk.py
```

更多细节见 [docker/README.md](docker/README.md)。

## 重要说明

- **有头模式**：注册流程与 CPA 导出默认以有头浏览器运行（`cpa_headless=false`）
- **中文环境**：容器已配置 `LC_ALL=zh_CN.UTF-8` 并安装中文字体
- **持久化**：
  - 桌面/用户配置：宿主机 `./docker/webtop-config`
  - 项目数据与输出：宿主机 `./docker/data`（accounts、pending、cpa_auths 等）
- **代理**：在 `config.json` 的 `proxy` 字段配置，支持多行/逗号/分号分隔

## 目录

```
docker/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
└── README.md
```

## 兼容性

- 需要 Docker + docker compose（或 Docker Desktop）
- 宿主机需有一定内存/共享内存（推荐 shm_size 2GB）
- 容器默认使用 `abc` 用户（linuxserver 惯例），PUID/PGID 可在 compose 中调整

## 常见问题

- 端口冲突：把 `3000:3000` 改成 `3xxx:3000`
- 看不到浏览器：确认是“有头”配置；必要时在 GUI 设置中把 `cpa_headless` 设为 false
- 代理不生效：检查格式，或在容器终端内 `curl` 测试目标地址
