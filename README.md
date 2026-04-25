# Telegram-AI-Bot (Gemen)

一个支持 **Telegram / WeChat** 的 AI Bot 项目，带有统一启动入口、Web Dashboard、Persona（角色）与 Session（会话）管理、记忆系统、TTS 配置和定时任务。

## 功能概览

- 文本对话（流式输出）
- 图片理解（Vision）
- 文件分析（文本/代码/图片）
- Persona 多角色管理
- Session 多会话管理
- 记忆系统
- Token 用量统计与限额
- Web Dashboard（设置、日志、会话、记忆、模型、备份等）
- 定时任务
- AI 工具系统（当前启用：终端与 HF Sync）

## 技术栈

- Python 3.11+
- `python-telegram-bot`
- FastAPI + Uvicorn
- PostgreSQL + `psycopg2-binary`
- OpenAI Compatible API

## 项目结构

```text
.
├── main.py                   # 统一启动入口
├── platforms/                # 平台运行时（Telegram / WeChat）
├── web/                      # FastAPI Web Dashboard
├── handlers/                 # Telegram handlers（命令、消息、回调）
├── services/                 # 业务逻辑层
├── ai/                       # AI 客户端封装
├── cache/                    # 进程内缓存与同步
├── database/                 # 数据库连接与 schema
├── config/                   # 常量与环境配置
├── utils/                    # 通用工具函数
├── tools/                    # 当前启用的 AI 工具
├── scripts/                  # 脚本
└── docs/                     # 设计、评审与工具归档文档
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
- `WECHAT_ENABLED=1`（启 WeChat 时）
- `OPENAI_API_KEY`（也支持每个用户在 Bot 内单独配置）

### 3. 准备数据库

首次启动会自动建表与迁移。只要 `DATABASE_URL` 可连接即可。

### 4. 启动服务

#### 统一启动

```bash
python main.py
```

说明：

- `main.py` 会按环境变量自动拉起 Telegram / WeChat
- 每个平台会使用自己的 `PORT`
- 默认端口：
  - Telegram：`7860`
  - WeChat：`7862`

## 常用命令

Telegram 使用 `/` 前缀。

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

## 工具系统说明

当前运行时仅保留并启用：

- `terminal`
- `hf_sync`（对象存储模式，S3-like）

`docs/tool-*.md` 仅作历史设计参考，不代表当前运行时代码。

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
- `wechat`

鉴权通过短时 token 与 JWT（`/web` 命令下发链接）。

## 关键环境变量

- 基础：`PORT`, `DATABASE_URL`
- Telegram：`TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`
- 模型默认值：`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_REASONING_EFFORT`
- TTS：`TTS_VOICE`, `TTS_STYLE`, `TTS_ENDPOINT`, `TTS_OUTPUT_FORMAT`
- 其他：`SHOW_THINKING`, `PORT`

详细示例请参考 `.env.example`。

## 开发建议

- 新增业务逻辑优先放到 `services/`
- 新增模型能力优先走 `ai/` 抽象层
- Bot 文案优先复用 `utils/platform_parity.py`，保持平台文案一致
- 修改缓存结构时同步检查 `cache/` 与相关数据库 loader/sync 逻辑
- 若要扩展工具能力，优先从当前 `tools/` 与 `services/` 实现继续演进

## 许可证

当前仓库未附带 LICENSE 文件。若用于公开分发，请先补充许可证声明。
