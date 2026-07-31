# Grok Register 简明使用与部署指南

### 环境基础要求

| 环境组件 | 版本要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Linux / Windows | 支持 Ubuntu、Debian 及 Docker 环境 |
| Python | 3.9 及以上 | 运行主程序与注册逻辑 |
| 内存配置 | 2GB 及以上 | 保证浏览器与代理桥顺畅运行 |

---

### 方案一：普通 Linux 服务器直接部署

#### 步骤1：安装基础依赖与工具

```bash
apt update
apt install -y python3 python3-pip python3-venv xz-utils curl git
```

#### 步骤2：创建并激活虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 步骤3：安装项目依赖与 Playwright 组件

```bash
pip install -r requirements.txt
pip install playwright
playwright install
```

#### 步骤4：配置代理与启动注册机

编辑根目录下的 `config.json` 写入代理后启动程序：

```bash
python grok_register_ttk.py
```

---

### 方案二：Docker 一键桌面部署

#### 步骤1：进入 Docker 构建目录

```bash
cd docker
```

#### 步骤2：构建并启动 Docker 容器

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

#### 步骤3：访问桌面与运行程序

1. 浏览器打开桌面控制台：`http://宿主机IP:3000`
2. 在桌面终端内执行启动命令：

```bash
cd /config/grok-register
python grok_register_ttk.py
```

---

### 代理配置规范说明

在配置文件 `config.json` 中的 `proxy` 字段，统一使用多行格式：

```
socks5://user:pass@108.165.180.187:6150
socks5://user:pass@108.165.180.187:6151
```

[正确] 配置完成后程序将自动启动本地 HTTP 转 SOCKS5 代理桥，保证浏览器与全接口无缝过验。
