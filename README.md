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
- 浏览器：`BROWSER_HEADLESS`, `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`
- HF Dataset 持久化：`HF_DATASET_USERNAME`, `HF_DATASET_TOKEN`, `HF_DATASET_NAME`, `HF_DATASET_ENCRYPTION_KEY`

详细示例请参考 `.env.example`。

## HF Dataset 持久化（可选）

如果部署在临时文件系统（如 Hugging Face Spaces 默认运行盘），可配置：

- `HF_DATASET_USERNAME`
- `HF_DATASET_TOKEN`
- `HF_DATASET_NAME`
- `HF_DATASET_ENCRYPTION_KEY`（必填；用于加密所有持久化数据）

启用后：

- `browser_agent` 会自动保存/恢复 Playwright `storage_state`（cookie + localStorage 等登录态）
- `shell` 会自动恢复并回传工作目录快照（默认不限制大小，可通过环境变量限制）

## 开发建议

- 新增业务逻辑优先放到 `services/`
- 新增模型能力优先走 `ai/` 抽象层
- 新增工具按 `tools/registry.py` 约定注册
- Bot 文案优先复用 `utils/platform_parity.py`，保持 Telegram/Discord 一致
- 修改缓存结构时同步检查 `cache/` 与 `services/state_sync_service.py`

## 许可证

当前仓库未附带 LICENSE 文件。若用于公开分发，请先补充许可证声明。
