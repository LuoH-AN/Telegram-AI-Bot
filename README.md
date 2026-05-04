# Telegram-AI-Bot (Gemen)

一个支持 **Telegram / WeChat / OneBot(QQ)** 的多平台 AI Bot 项目，支持多角色管理、多会话管理、记忆系统、Token 用量统计与定时任务。

## 功能概览

- 文本对话（流式输出）
- 图片理解（Vision）
- 文件分析（文本/代码/图片）
- Persona 多角色管理
- Session 多会话管理
- 记忆系统
- Token 用量统计与限额
- 定时任务
- AI 工具系统（plugin 架构，当前内置：terminal、scrapling、search、s3、project_config）

## 技术栈

- Python 3.11+
- `python-telegram-bot`
- PostgreSQL + `psycopg2-binary`
- OpenAI Compatible API

## 项目结构

```text
.
├── main.py                   # 统一启动入口（按环境变量拉子进程）
├── launcher/                 # 多进程拉起、热更新、CLI bootstrap
├── platforms/                # 平台运行时
│   ├── telegram/             # Telegram bot + handlers
│   ├── onebot/               # OneBot/NapCat (QQ)
│   ├── wechat/               # WeChat 个人号 + 公众号
│   ├── commands/             # 跨平台命令分发
│   └── shared/               # 共享 chat 流水线、context 协议、runtime 辅助
├── core/                     # 命令编排（persona / session / provider / plugins）
├── services/                 # 业务逻辑层（user / persona / session / memory / cron 等）
├── ai/                       # AI 客户端封装（OpenAI 兼容）+ 流式协议
├── cache/                    # 进程内缓存与脏页同步
├── database/                 # PostgreSQL 连接与 schema
├── config/                   # 常量与环境变量
├── utils/                    # 通用工具函数
├── tools/                    # 内置插件（plugin 架构）
└── scripts/                  # 一次性脚本与维护工具
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
- `ONEBOT_ENABLED=1`（启 OneBot/QQ 时）
- `OPENAI_API_KEY`（也支持每个用户在 Bot 内单独配置）

### 3. 准备数据库

首次启动会自动建表（`CREATE TABLE IF NOT EXISTS`）。只要 `DATABASE_URL` 可连接即可。

### 4. 启动服务

```bash
python main.py
```

说明：

- `main.py` 会按环境变量自动拉起 Telegram / WeChat / OneBot 子进程
- 每个平台独立进程，互不影响

## 常用命令

Telegram 使用 `/` 前缀；OneBot/WeChat 默认使用各自前缀（见 `.env.example`）。

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
- `skill`（插件管理：list / install / remove / enable / disable / info）

## 工具/插件系统说明

工具基于 plugin 架构（`core/plugins/`）。`tools/` 下为内置插件，第三方插件可通过 `/skill install <github-url>` 安装到 `~/.gemen/plugins/`。

## 关键环境变量

- 基础：`DATABASE_URL`
- Telegram：`TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`
- OneBot：
  - `ONEBOT_ENABLED`, `ONEBOT_MODE`（client/server/ws）
  - `ONEBOT_WS_URL`（client 模式连接目标）
  - `ONEBOT_WS_BIND_HOST`、`ONEBOT_WS_BIND_PORT`、`ONEBOT_WS_PATH`（ws 模式监听）
  - `QQ_COMMAND_PREFIX`
- WeChat：`WECHAT_ENABLED`, `WECHAT_COMMAND_PREFIX`
- 模型默认值：`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_REASONING_EFFORT`
- 其他：`SHOW_THINKING`

详细示例请参考 `.env.example`。

## 开发约定

- 新增业务逻辑放到 `services/`
- 新增模型能力走 `ai/` 抽象层
- 跨平台命令编排放 `core/`，平台特定 handler 放 `platforms/<platform>/`
- 共用对话流水线在 `platforms/shared/chat/inbound.py`
- 用户面文案优先复用 `utils/platform/`，保持平台一致

## 许可证

当前仓库未附带 LICENSE 文件。若用于公开分发，请先补充许可证声明。