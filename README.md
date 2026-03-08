# Telegram-AI-Bot (Gemen)

一个支持 **Telegram / Discord 双平台** 的 AI Bot 项目，带有 Web Dashboard、可扩展工具系统、Persona（角色）与 Session（会话）管理、记忆系统、TTS、定时任务与 MCP 接口。

## 功能概览

- 文本对话（流式输出）
- 图片理解（Vision）
- 文件分析（文本/代码/图片）
- Persona 多角色管理
- Session 多会话管理
- 记忆系统（手动记忆 + AI 工具记忆）
- Token 用量统计与限额
- 工具调用（search / fetch / wikipedia / tts / shell / cron / playwright / crawl4ai / browser_agent）
- Web Dashboard（设置、日志、会话、记忆、模型、备份等）
- MCP Server（可挂载到同端口，供外部 MCP 客户端调用）

## 技术栈

- Python 3.11+
- `python-telegram-bot` / `discord.py`
- FastAPI + Uvicorn
- PostgreSQL + `psycopg2-binary`
- OpenAI Compatible API
- Playwright (Chromium)
- Crawl4AI

## 项目结构

```text
.
├── bot.py                    # Telegram 入口
├── discord_bot.py            # Discord 入口
├── web/                      # FastAPI Web Dashboard
├── handlers/                 # Telegram handlers（命令、消息、回调）
├── services/                 # 业务逻辑层
├── tools/                    # 可扩展工具系统（Tool Registry）
├── ai/                       # AI 客户端封装
├── cache/                    # 进程内缓存与同步
├── database/                 # 数据库连接与 schema
├── config/                   # 常量与环境配置
├── utils/                    # 通用工具函数
├── scripts/                  # 脚本
└── docs/                     # 设计与评审文档
```

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少需要配置：

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`（启 Telegram 时）
- `DISCORD_BOT_TOKEN`（启 Discord 时）
- `OPENAI_API_KEY`（也支持每个用户在 Bot 内单独配置）

### 3. 准备数据库

首次启动会自动建表与迁移。只要 `DATABASE_URL` 可连接即可。

### 4. 启动服务

#### 启动 Telegram Bot

```bash
python bot.py
```

#### 启动 Discord Bot

```bash
python discord_bot.py
```

说明：两个入口都会启动 Web 服务（默认 `PORT=8080`）。如果要同时运行两者，请为不同进程设置不同端口。

Docker 默认行为：会按 token 自动启用平台（可单开或双开）：

- 配置了 `TELEGRAM_BOT_TOKEN` → 启动 Telegram
- 配置了 `DISCORD_BOT_TOKEN` → 启动 Discord
- 两个都配置 → 两个平台都启动

#### Docker 构建体积说明

镜像体积大的主要原因通常是：

- `playwright install --with-deps chromium`（浏览器二进制 + 系统依赖）
- `fonts-noto-cjk`（中日韩字体）
- shell 工具附带的一组 CLI 工具

现在 `Dockerfile` 支持按需裁剪：

```bash
# 全功能默认版（有头浏览器 + 依赖 + CJK 字体 + shell 工具）
docker build -t gemen .

# 平衡版：保留浏览器，改为 headless，并去掉 CJK 字体和 headful 支持
docker build -t gemen-balanced \
  --build-arg BROWSER_HEADLESS=1 \
  --build-arg INSTALL_HEADFUL_SUPPORT=0 \
  --build-arg INSTALL_CJK_FONTS=0 \
  .

# 瘦身版：不安装浏览器，仅保留 bot 主功能
docker build -t gemen-slim \
  --build-arg BROWSER_HEADLESS=1 \
  --build-arg INSTALL_BROWSER=0 \
  --build-arg INSTALL_CJK_FONTS=0 \
  --build-arg INSTALL_HEADFUL_SUPPORT=0 \
  --build-arg INSTALL_SHELL_UTILS=0 \
  .
```

说明：

- 默认 `docker build -t gemen .` 现在就是全功能有头配置
- `INSTALL_BROWSER=0` 会明显减小体积，但 `browser_agent` / `crawl4ai` 等浏览器能力将不可用
- `INSTALL_CJK_FONTS=0` 可再省一部分体积，但中文网页截图/渲染可能缺字
- `INSTALL_HEADFUL_SUPPORT=0` 适合纯 headless 部署

## 常用命令

Telegram 使用 `/` 前缀，Discord 使用 `!`（可配置）。

- `start`
- `help`
- `clear`
- `settings`
- `set`
- `persona`
- `chat`
- `usage`
- `export`
- `remember`
- `memories`
- `forget`
- `web`（发送 Dashboard 登录链接）

## 工具系统

当前支持工具：

- `memory`
- `search`
- `fetch`
- `wikipedia`
- `tts`
- `shell`
- `cron`
- `playwright`
- `crawl4ai`
- `browser_agent`

可在用户设置中通过 `enabled_tools` 与 `cron_enabled_tools` 控制启用范围。

## Web Dashboard

入口：`http://<host>:<PORT>/`

核心 API 路由位于 `web/routes/`：

- `settings`
- `personas`
- `providers`
- `sessions`
- `usage`
- `memories`
- `models`
- `logs`
- `cron`
- `backup`
- `browser_view`

鉴权通过短时 token 与 JWT（`/web` 命令下发链接）。

## MCP 支持

项目内置 MCP 适配，可独立运行：

```bash
python mcp_server.py
```

或在 Web 应用内挂载（默认会尝试挂载到同端口）。

## 关键环境变量

- 基础：`PORT`, `DATABASE_URL`
- Telegram：`TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`
- Discord：`DISCORD_BOT_TOKEN`, `DISCORD_COMMAND_PREFIX`
- 模型默认值：`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_REASONING_EFFORT`
- 工具默认值：`ENABLED_TOOLS`, `CRON_ENABLED_TOOLS`
- TTS：`TTS_VOICE`, `TTS_STYLE`, `TTS_ENDPOINT`, `TTS_OUTPUT_FORMAT`
- 浏览器：`BROWSER_HEADLESS`, `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`, `BROWSER_AUTO_START`, `BROWSER_AUTO_START_BACKGROUND`, `BROWSER_AUTO_START_CRAWL4AI`
- HF Dataset 持久化：`HF_DATASET_USERNAME`, `HF_DATASET_TOKEN`, `HF_DATASET_NAME`, `HF_DATASET_ENCRYPTION_KEY`

详细示例请参考 `.env.example`。

## 浏览器工具启动预热

启动 `bot.py` / `discord_bot.py` 时会自动预热浏览器运行时：

- `playwright`：预先启动 Chromium worker
- `browser_agent`：预先启动会话 worker
- `crawl4ai`：预先做浏览器栈可用性预热（可关闭）

可选环境变量：

- `BROWSER_AUTO_START`（默认 `1`）：总开关
- `BROWSER_AUTO_START_BACKGROUND`（默认 `1`）：后台线程预热，避免阻塞启动
- `BROWSER_AUTO_START_CRAWL4AI`（默认 `1`）：是否包含 `crawl4ai` 预热

## HF Dataset 持久化（可选）

如果部署在临时文件系统（如 Hugging Face Spaces 默认运行盘），可配置：

- `HF_DATASET_USERNAME`
- `HF_DATASET_TOKEN`
- `HF_DATASET_NAME`
- `HF_DATASET_ENCRYPTION_KEY`（必填；用于加密所有持久化数据）

启用后：

- `browser_agent` 会自动保存/恢复 Playwright `storage_state`（cookie + localStorage 等登录态）
- `browser_agent` 不会恢复重启前的标签页、下载文件、运行中的浏览器进程或内存会话
- `shell` 默认会在每次命令结束后保存当前 `working_directory` 的完整快照，并在容器重启后按目录恢复
- `shell` 还会额外保存常见用户运行时目录（默认包括 `~/.local`、`~/.nvm`、`~/.npm`、`~/.yarn` 等），尽量恢复 `npm` / `yarn` / `nvm` / `pip --user` 等安装结果
- `shell` 会自动推断 `apt/apt-get install|remove|purge` 命令并维护系统包清单，不再依赖工具调用显式传 `persist_packages`
- 若你想精确恢复某个项目目录，请优先传 `working_directory`，不要只在命令里写 `cd ... && ...`
- 仍需注意：系统级运行时和外部服务能否 100% 恢复，还取决于底层镜像、HF Dataset 上传成功与否，以及目标环境是否允许重新安装对应包

## 开发建议

- 新增业务逻辑优先放到 `services/`
- 新增模型能力优先走 `ai/` 抽象层
- 新增工具按 `tools/registry.py` 约定注册
- Bot 文案优先复用 `utils/platform_parity.py`，保持 Telegram/Discord 一致
- 修改缓存结构时同步检查 `cache/` 与 `services/state_sync_service.py`

## 许可证

当前仓库未附带 LICENSE 文件。若用于公开分发，请先补充许可证声明。
