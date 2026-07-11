# Telegram-AI-Bot (Gemen)

一个基于 **Telegram** 的 AI Bot 项目，支持多角色管理、多会话管理、记忆系统、Token 用量统计与定时任务。

## 功能概览

- 文本对话（流式输出）
- 图片理解（Vision）
- 文件分析（文本/代码/图片）
- Persona 多角色管理
- Session 多会话管理
- 记忆系统
- Token 用量统计与限额
- 定时任务
- 按钮式新手引导、设置、会话、角色与定时任务面板
- Telegram 忙碌策略：新消息可中断当前回复或进入同会话队列
- 工具活动提示：关闭、精简、完整三档；每轮工具调用使用独立静默消息，并与助手文字按时间线交叉显示
- 中英文自动界面（可在主菜单切换）
- AI 工具系统（注册式架构，当前内置：config_file、database、memory、search、send_file、terminal）

## 技术栈

- Python 3.10+
- `python-telegram-bot`
- PostgreSQL + `psycopg2-binary`
- OpenAI Compatible API

## 项目结构

```text
.
├── main.py                   # 启动入口（拉起 Telegram 子进程）
├── entrypoints/              # 进程入口、子进程拉起、热更新、CLI bootstrap
├── adapters/                 # 外部平台适配：Telegram 与 HTTP/OpenAPI/Web
├── application/              # 应用用例与命令编排
├── domain/                   # 业务服务：user / persona / session / memory / cron 等
├── infrastructure/           # AI、cache、database、config、tools 等基础设施
├── shared/                   # 通用格式化、文案、文件、stream 等 helper
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
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`（也支持每个用户在 Bot 内单独配置）

### 3. 准备数据库

首次启动会自动建表（`CREATE TABLE IF NOT EXISTS`）。只要 `DATABASE_URL` 可连接即可。

### 4. 启动服务

```bash
python main.py
```

说明：

- `main.py` 会在配置了 `TELEGRAM_BOT_TOKEN` 时自动拉起 Telegram 子进程
- 子进程退出或热更新会触发自动重启

## 常用命令

命令使用 `/` 前缀：

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
- `skill`（技能管理；install 仅管理员）
- `cron`（定时任务管理与立即测试）
- `model`
- `reset`
- `restart`（管理员）
- `status`
- `stop`
- `update`（管理员）

## Telegram 交互设置

在私聊中打开“设置 → 生成与发送”，可以调整：

- 忙碌时：`interrupt`（默认，新消息中断当前回复）或 `queue`（按当前会话依次处理）
- 工具进度：`off`、`compact`（默认）或 `full`

工具进度消息不会触发额外通知。每轮工具调用会生成并原位更新一条独立消息，完成后保留在对话时间线中；下一段助手文字会从该消息之后继续。终端等高风险工具仍只向 `ADMIN_IDS` / `OWNER_ID` 中的管理员开放。

设置中心同时提供完整的中英文按钮入口：

- 模型服务连接：设置或更换 API Key、自定义兼容地址、恢复 OpenAI 官方地址、测试连接
- 已保存的模型服务：保存当前地址/密钥/模型组合，并一键切换或删除
- 生成与发送：推理强度、Telegram 消息刷新方式、思考摘要、忙碌策略、工具进度、温度
- 高级设置：全局提示词、会话标题模型、定时任务模型、当前角色 Token 限额
- 其他：对话模型、时区、用量与上下文、完整配置总览

可枚举的设置采用按钮优先设计：标题模型和定时任务模型会先选择当前/已保存的模型服务，再自动获取模型列表；Token 限额提供常用预设；定时任务提供常见执行计划。只有 API Key、自定义地址、名称、提示词等无法预先确定的内容才要求用户输入。

主菜单的“功能中心”提供以下按钮操作：

- 长期记忆：分页查看、添加、删除单条或清空全部
- 技能：分页查看、启用/停用、移除，管理员可安装新技能
- 会话维护：导出当前会话、清空当前会话及其用量
- 运行状态：查看代码、运行环境、数据量和资源占用
- 管理员操作：确认后检查更新或安全重启服务

## 工具/技能系统说明

工具基于注册式 `@tool` 架构（`infrastructure/tools/`）。内置工具位于 `infrastructure/tools/builtin/`，管理员可通过 `/skill install <github-url>` 安装第三方技能。

终端采用严格的 `/data` 持久文件系统：应用工作区实际运行在 `/data/telegram_ai_bot/workspace`，每条命令通过 proot 在 `/data/telegram_ai_bot/terminal/filesystem/rootfs` 中执行。因此 `apt` 写入的 `/usr`、NVM/npm 写入的用户目录、项目内 `node_modules`、虚拟环境、缓存和任意绝对路径文件都位于 `/data` 的可写层。镜像缺少 proot 或 rootfs seed 时终端会拒绝执行，不会退回临时宿主文件系统。启用该结构需要使用最新 Dockerfile 重新构建镜像，仅执行 `/update` 无法给旧镜像补装 proot。

搜索工具使用 Exa，并默认启用官方推荐的 `auto` 模式。结果会经过 URL 去重、相关性重排和域名多样化处理；优先使用 Exa 返回的相关正文片段，缺失时再安全抓取排名靠前的网页。模型被要求将网页内容视为不可信证据、交叉验证重要结论并在回答中附上来源链接。

搜索最少需要：

```env
EXA_API_KEYS=exa-key-1,exa-key-2
ENABLED_TOOLS=search,memory,send_file
```

可通过 `EXA_SEARCH_TYPE`、`EXA_CACHE_TTL` 和 `EXA_MODERATION` 调整搜索模式、缓存及安全过滤。工具调用不设固定轮次上限，会持续到模型完成任务、用户取消或现有超时机制中断。日常查询推荐 `auto`；`deep-lite`、`deep`、`deep-reasoning` 更慢且费用更高，只适合复杂研究。

## 关键环境变量

- 基础：`DATABASE_URL`
- Telegram：`TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`, `TELEGRAM_NATIVE_DRAFTS`, `TELEGRAM_RICH_MESSAGES`
- 模型默认值：`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_REASONING_EFFORT`
- OpenAPI 工具：`OPENAPI_TOOLS_TOKEN`（必填）、`OPENAPI_TOOLS_CORS_ORIGINS`；Terminal 还需 `OPENAPI_TOOLS_USER_ID` 指向管理员 ID
- 搜索：`EXA_API_KEYS`、`EXA_SEARCH_TYPE`、`EXA_CACHE_TTL`
- 体验：`DEFAULT_TIMEZONE`（默认 `Asia/Shanghai`）
- 其他：`SHOW_THINKING`

详细示例请参考 `.env.example`。

安全提示：API Key 只允许在 Telegram 私聊中设置；Bot 会尽量立即删除包含密钥的消息。群聊中使用 `/set api_key ...` 会被拒绝。

## 开发约定

- 新增业务逻辑放到 `domain/services/`
- 新增模型能力走 `infrastructure/ai/` 抽象层
- 平台无关命令逻辑放到 `application/use_cases/`
- Telegram 命令实现放到 `adapters/telegram/commands/`（命令注册见该处注册表）
- Telegram handler 放到 `adapters/telegram/handlers/`
- 用户面文案优先复用 `shared/utils/platform/`

## 许可证

当前仓库未附带 LICENSE 文件。若用于公开分发，请先补充许可证声明。
