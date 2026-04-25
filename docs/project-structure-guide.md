# Telegram-AI-Bot 项目结构梳理

> 面向规划的代码级说明文档。目标不是“列目录”，而是帮助你快速判断：这个项目现在是怎么跑起来的、各层职责怎么分、哪些地方适合扩展、哪些地方已经出现历史包袱。

## 1. 项目一句话概述

这是一个支持 **Telegram / WeChat** 的多平台 AI Bot 项目，核心能力包括：

- 多平台消息接入
- 基于 OpenAI Compatible API 的对话与工具调用
- Persona（角色）与 Session（会话）管理
- 记忆系统与 Token 用量统计
- Web Dashboard
- Cron 定时任务
- 内置工具系统（终端、对象存储、搜索、抓取、快速部署等）

技术栈大致是：

- Python 3.11+
- `python-telegram-bot`
- FastAPI + Uvicorn
- PostgreSQL + `psycopg2-binary`
- OpenAI Compatible API

从仓库规模看，当前大约有：

- `404` 个 Python 文件
- `20` 个 Markdown 文件
- 前端为原生静态页面，无单独前端工程

---

## 2. 先看结论：这个项目现在的真实架构

如果只用一句话描述当前架构：

**这是一个“多平台子进程 + 各自内嵌 Web + 各自内存缓存 + 共享 PostgreSQL” 的单仓库系统。**

最重要的不是目录，而是下面这件事：

### 2.1 运行时拓扑

`main.py` 不是直接跑一个 Bot，而是按环境变量决定要不要拉起多个子进程：

```text
main.py
├── Telegram 子进程  -> Telegram Bot + Web Dashboard + 内存缓存 + Cron
└── WeChat 子进程    -> WeChat Bot   + Web Dashboard + 内存缓存 + Cron
```

也就是说：

- **Web 不是独立服务**
- **每个平台进程里都内嵌了一个 FastAPI**
- **每个平台进程都有自己的一份进程内缓存**
- **多个进程通过 PostgreSQL 共享数据**

这对后续规划很关键，因为它天然带来：

- 部署简单，但结构偏耦合
- 跨进程状态一致性不是“实时强一致”，更像“数据库为准 + 缓存按需刷新”
- 如果两端都启用，你实际上会有两个 Dashboard 入口（不同端口）

---

## 3. 启动链路

### 3.1 顶层入口

- `main.py`
  - 统一入口
  - 读取 `.env`
  - 根据 `TELEGRAM_BOT_TOKEN` / `WECHAT_ENABLED` 决定启哪些平台
  - 为每个平台分配端口
  - 启动子进程
  - 负责 `/update` 后的整进程重启

### 3.2 启动辅助

- `launcher/`
  - `env_helpers.py`
    - 解析 `ENV_TEXT` / `ENV_CONTENT`
    - 识别 token 是否已配置
    - 返回 Telegram / WeChat 的端口
  - `process_helpers.py`
    - 启动/停止子进程
    - 等待任一子进程退出
  - `bootstrap_cli.py`
    - 启动前可执行一组持久化的 CLI 命令
    - 用于恢复环境或补装依赖

### 3.3 每个平台启动时都会做什么

以 Telegram / WeChat 为例，逻辑都非常接近：

1. `init_database()`
2. 启动内嵌 Web Server
3. 启动平台 Bot Runtime
4. 启动 Cron Scheduler

关键入口文件：

- `platforms/telegram/app.py`
- `platforms/wechat/app.py`

---

## 4. 项目目录总览

## 4.1 顶层目录树

```text
.
├── main.py                    # 统一启动入口
├── launcher/                  # 多子进程启动、环境注入、bootstrap
├── platforms/                 # Telegram / WeChat 平台接入层
├── handlers/                  # Telegram 侧 handler 与通用消息处理
├── services/                  # 业务服务层
├── ai/                        # OpenAI Compatible 客户端封装
├── tools/                     # 模型可调用工具注册与实现
├── web/                       # FastAPI Web Dashboard
├── static/                    # Dashboard 静态前端
├── cache/                     # 进程内缓存与数据库回写
├── database/                  # 数据库连接、建表、行解析
├── core/                      # 纯文本命令核心逻辑（Persona / Session 等）
├── config/                    # 环境变量与常量
├── utils/                     # 格式化、发送、平台文案、限流等工具
├── scripts/                   # 迁移、检查、构建脚本
├── docs/                      # 现有文档与历史资料
├── Dockerfile                 # 主容器镜像
├── Dockerfile.hfspace         # Hugging Face Space 用镜像
├── requirements.txt           # Python 依赖
└── start_bots.sh              # 简单启动脚本
```

### 4.2 顶层模块规模

| 目录 | Python 文件数 | 作用 |
| --- | ---: | --- |
| `services/` | 103 | 业务逻辑主层 |
| `platforms/` | 48 | 两个平台运行时 |
| `utils/` | 46 | 通用工具 |
| `handlers/` | 40 | Telegram handlers 与通用消息流 |
| `tools/` | 40 | 工具系统 |
| `cache/` | 36 | 内存缓存与 DB 同步 |
| `web/` | 35 | Dashboard API |
| `core/` | 19 | 纯命令逻辑 |
| `database/` | 13 | 建表/连接/加载器 |
| `ai/` | 10 | AI 客户端封装 |

结论：

- 业务重心明显在 `services/`
- 平台适配较重，尤其 WeChat 单独 runtime 很厚
- 前端很轻，后端是核心

---

## 5. 分层理解：每层到底干什么

## 5.1 平台接入层：`platforms/`

这是“把 Telegram / WeChat 接进来”的地方。

### 目录结构

```text
platforms/
├── commands/          # 共享的命令入口逻辑
├── telegram/          # Telegram 启动与注册
└── wechat/            # WeChat 自定义 runtime
```

### 两个平台的差异

#### Telegram

- 用 `python-telegram-bot`
- 入口：`platforms/telegram/app.py`
- 构建器：`platforms/telegram/app_builder.py`
- `handlers/` 目录是 Telegram 侧的主要消息处理代码

Telegram 这一侧比较“传统”：

- 命令通过 `CommandHandler`
- 文本消息通过 `MessageHandler`
- 图片 / 文档分别有独立 handler

#### WeChat

- 入口：`platforms/wechat/app.py`
- 主 runtime：`platforms/wechat/runtime/app.py`
- 主循环：`platforms/wechat/runtime/loop.py`
- 命令分发：`platforms/wechat/commands/dispatch.py`

WeChat 不是简单的 SDK 事件回调，而是一个比较完整的 runtime：

- 登录状态维护
- 轮询
- 消息去重
- 上下文 token 记忆
- 文件发送 / 文本发送
- 打字状态

**结论：WeChat 是两端里最“重”的接入层。**

---

## 5.2 共享命令层：`platforms/commands/` + `core/`

这部分是项目做得比较统一的一层。

### 设计思路

- `platforms/commands/`
  - 负责“平台无关的命令入口”
  - 例如 `start`、`help`、`settings`、`persona`、`chat`
- `core/`
  - 负责更纯粹的业务命令逻辑
  - 例如 Persona 的创建/切换/删除
  - Session 的创建/重命名/删除/切换

### 这层的价值

它让多端命令复用了一套核心逻辑：

- Telegram 只是做 adapter
- WeChat 的文本命令也走同一套 dispatcher

如果你未来要加一个新平台，这层是可以继续复用的。

---

## 5.3 业务服务层：`services/`

这是项目的真正中心。

### 主要子模块

```text
services/
├── cron/              # 定时任务
├── deployments/       # 静态页面部署
├── hf_sync/           # Hugging Face Dataset 对象存储
├── log/               # 日志读写
├── memory/            # 记忆系统
├── platform/          # 平台共享展示/配置逻辑
├── session/           # 会话管理
├── skill_terminal/    # AI 驱动终端流程
├── skills/            # 技能管理（当前基本禁用）
├── state_sync/        # 跨进程状态刷新
├── terminal_exec/     # 持久化终端执行
├── wechat/            # WeChat 服务与官方 SDK 封装
├── user.py            # 用户设置访问
├── token.py           # token 使用统计
├── persona.py         # persona 逻辑
├── refresh.py         # 用户状态刷新入口
├── runtime_queue.py   # 会话串行与停止机制
└── hot_update.py      # git pull + 进程重启
```

### 你可以这样理解 `services/`

- `platforms/` 决定“消息从哪来”
- `services/` 决定“消息进来后怎么处理”

### 最重要的几个服务

#### `services/user.py`

- 读写用户设置
- 底层其实是读写缓存

#### `services/persona.py`

- Persona 的创建、切换、删除、更新
- 组装系统提示词
- 会把 `global_prompt + persona prompt + tool policy` 合并起来

#### `services/session/`

- 会话列表
- 当前会话
- 创建、删除、切换、重命名
- 首轮对话后自动生成标题

#### `services/memory/`

- 记忆增删改查
- 可选 embedding 去重
- embedding 默认走 NVIDIA 的 OpenAI Compatible 接口

#### `services/token.py`

- 统计 prompt / completion / total tokens
- 管理每个 persona 的 token limit

#### `services/cron/`

- Cron 调度器
- 定时执行 AI prompt
- 将结果回发到对应平台

#### `services/runtime_queue.py`

- 同一会话串行执行
- 新消息到来时取消旧响应
- `/stop` 的底层就是这里

这是聊天稳定性的关键模块之一。

---

## 5.4 AI 层：`ai/`

这里是 AI Provider 抽象层。

### 当前真实情况

抽象是有的，但目前实际上只实现了：

- OpenAI Compatible API

### 结构

```text
ai/
├── base.py                 # AIClient / StreamChunk / ToolCall 抽象
└── openai_client/
    ├── client.py           # OpenAIClient
    ├── chat_api.py
    ├── chat_stream.py
    ├── chat_nonstream.py
    ├── chat_create.py
    ├── models_api.py
    └── helpers.py
```

### 当前能力

- 流式输出
- 非流式输出
- 模型列表拉取
- reasoning content 支持
- tool call 支持

---

## 5.5 工具层：`tools/`

这层是“让模型调用本地工具”的地方。

### 当前注册到运行时的工具

代码里实际注册了 6 个：

- `terminal`
- `hf_sync`
- `project_config`
- `quick_deploy`
- `scrapling`
- `sosearch`

注册位置：

- `tools/__init__.py`

### 各工具职责

#### `tools/terminal/`

- 无沙箱终端执行
- 支持前台执行
- 支持后台任务
- 支持查询后台任务

#### `tools/hf_sync/`

- 基于 Hugging Face Dataset 的对象存储
- 支持 upload / list / get / delete / copy / move / url

#### `tools/project_config/`

- 读写仓库内配置文件
- 支持 `.env` / JSON / INI / 文本

#### `tools/quick_deploy/`

- 快速部署静态 HTML/CSS/JS 到 `runtime/deployments`
- 对外暴露 `/deploy/{slug}`

#### `tools/scrapling/`

- 网页抓取
- HTML 解析
- cookie vault

#### `tools/sosearch/`

- 内置搜索服务封装

### 工具执行路径

模型生成 tool calls 后，执行流大致是：

1. `handlers/messages/text/generation.py`
2. `tools.get_all_tools(enabled_tools="all")`
3. `tools.process_tool_calls(...)`
4. `tools/core/registry.py`
5. 具体工具 `execute()`

**重要：当前代码里工具是按 `enabled_tools="all"` 直接全开。**

---

## 5.6 Web 层：`web/` + `static/`

这是 Dashboard。

### 后端

- `web/app.py`
  - FastAPI app factory
- `web/app_routes.py`
  - 健康检查
  - 静态文件挂载
  - 登录 token 交换
- `web/auth.py`
  - JWT 验证
- `web/auth_tokens.py`
  - JWT / short token / artifact token 编解码
- `web/routes/`
  - Dashboard API
  - 集成接口

### 前端

- `static/index.html`
  - 整个 Dashboard 页面
- `static/app.js`
  - 所有前端逻辑，当前是压缩后的单文件
- `static/custom.css` + `static/css/`
  - 样式

### Dashboard 当前功能页

从前端实际代码看，现在有这些 pane：

- General Settings
- Personas
- Sessions
- Memories
- Providers
- Models
- Cron
- Usage
- Logs

也就是说，前端功能面和后端 API 是对得上的，基础管理能力已经比较完整。

---

## 5.7 数据层：`cache/` + `database/`

这一层很关键，因为它决定了系统到底是不是“直接操作数据库”。

答案是：

**不是。项目优先读写进程内缓存，再由后台线程定期回写 PostgreSQL。**

### `database/` 做什么

- `db.py`
  - 获取 PostgreSQL 连接
- `tables.py`
  - 建表入口
- `schema_sql/`
  - 按领域拆分建表 SQL
- `loaders/`
  - DB 行 -> Python dict 的解析器

### `cache/` 做什么

- `manager/`
  - 各类缓存 mixin
- `sync/`
  - 启动时载入数据库
  - 后台回写数据库

### 缓存里实际维护的内容

`cache/manager/state_caches.py` 里可见当前缓存镜像：

- `_settings_cache`
- `_personas_cache`
- `_sessions_cache`
- `_conversations_cache`
- `_persona_tokens_cache`
- `_memories_cache`
- `_cron_tasks_cache`
- `_skills_cache`
- `_skill_states_cache`

### 同步机制

启动时：

1. `create_tables()`
2. `load_from_database()`
3. 启动后台同步线程

后台线程：

- 每 `30s`（`DB_SYNC_INTERVAL`）回写一次数据库

跨进程刷新：

- 入口处调用 `services.refresh.ensure_user_state(user_id)`
- 由 `services/state_sync/` 控制刷新频率
- 默认 `2s` 内重复调用会被 debounce

### 这意味着什么

这是一个：

- **数据库持久化**
- **进程内缓存加速**
- **跨进程最终一致**

的设计。

这对单进程很方便，但多平台多进程下会带来一致性边界，需要你在规划时特别注意。

---

## 6. 关键目录逐个解释

## 6.1 `main.py`

角色：

- 整个系统的统一启动入口

关键点：

- 会读 `.env`
- 会应用 `ENV_TEXT`
- 会按条件启动 Telegram / WeChat
- 某个子进程退出时会把其他子进程一起停掉

适合改这里的场景：

- 想改统一启动方式
- 想引入独立 Web 服务
- 想把多平台合并/拆分部署

---

## 6.2 `launcher/`

角色：

- 给 `main.py` 提供平台启动、环境注入、CLI bootstrap 能力

适合改这里的场景：

- 想支持更多启动参数
- 想做 sidecar 初始化
- 想接入更正规的 supervisor/process manager

---

## 6.3 `platforms/`

角色：

- 平台 SDK 接入
- 平台上下文适配
- 平台差异逻辑处理

适合改这里的场景：

- 新增平台
- 修改 Telegram / WeChat 的接入行为
- 改平台专属消息格式、回复策略、群组触发条件

---

## 6.4 `handlers/`

角色：

- 主要是 Telegram 侧 handler
- 也承载一部分通用消息处理流程

关键子目录：

- `handlers/commands/`
  - Telegram 命令包装层
- `handlers/messages/`
  - 文本、图片、文档消息处理
- `handlers/common/`
  - 群组判断、媒体预处理、日志上下文

要点：

- Telegram 的消息流大量写在这里
- WeChat 则更多在各自 `platforms/*/chat/`

---

## 6.5 `services/`

角色：

- 业务主层

如果你以后要做功能规划，这里是最核心的目录。大多数“功能需求”最终都应该落在这一层，而不是直接塞进平台 handler。

---

## 6.6 `ai/`

角色：

- Provider 抽象层
- 流式响应解析
- 模型列表

适合改这里的场景：

- 新增新 provider 类型
- 改 tool call 解析策略
- 改 streaming 行为

---

## 6.7 `tools/`

角色：

- 模型可调用的工具定义与执行

适合改这里的场景：

- 新增工具
- 控制哪些工具可见
- 调整工具串行/并行策略

---

## 6.8 `web/`

角色：

- Dashboard API
- 鉴权
- 静态站挂载

适合改这里的场景：

- 新增后台管理接口
- 改登录逻辑
- 把 Web 独立出来

---

## 6.9 `static/`

角色：

- Dashboard 前端静态页面

当前问题也很明显：

- `app.js` 是压缩后的单文件
- 没有模块化工程
- 维护成本会随功能增长快速上升

适合改这里的场景：

- 想做前端重构
- 想引入 React/Vue
- 想拆分页面与状态管理

---

## 6.10 `cache/`

角色：

- 进程内缓存
- 脏数据记录
- 定期回写数据库

这是性能与一致性平衡层。

---

## 6.11 `database/`

角色：

- 建表
- 连接
- DB row 解析

适合改这里的场景：

- 新增表
- 增字段
- 调整 schema

---

## 6.12 `core/`

角色：

- 比 `services/` 更轻的一层命令逻辑
- 主要做文本命令的结果拼装

理解上可以把它看成：

- `services/` 是“业务能力”
- `core/` 是“命令 use case”

---

## 6.13 `config/`

角色：

- 所有环境变量
- 默认设置
- 常量

关键文件：

- `config/env.py`
- `config/util.py`
- `config/app.py`

---

## 6.14 `utils/`

角色：

- 杂项但很重要

关键内容：

- Markdown / HTML / LaTeX 格式化
- Telegram 安全发送与编辑
- 平台统一文案
- 限流器
- provider model 解析
- tool status 提示

---

## 6.15 `scripts/`

角色：

- 开发和维护脚本

当前有这些：

- `migrate_legacy_data_to_new_schema.py`
  - 旧数据迁移到新 schema
- `inspect_memories.py`
  - 检查 DB 中的记忆数据
- `find_long_files.py`
  - 查超长文件
- `check_file_length.py`
  - 作为约束检查脚本
- `docker_build_push.sh`
  - 构建并推送 Docker 镜像

---

## 7. 消息处理主链路

这里是最值得看懂的一部分。

## 7.1 文本消息主流程

以 Telegram 为例，主链路是：

```text
用户消息
-> handlers/messages/text/preflight.py
-> ensure_user_state()
-> 读取 settings / persona / session / conversation
-> 拼 system prompt + 历史消息 + 当前消息
-> ai client 流式调用
-> 如果模型发起 tool calls，则进入 tools/
-> 结果回写 session / token usage / logs
-> 定时同步进 PostgreSQL
```

关键文件：

- `handlers/messages/text/preflight.py`
- `handlers/messages/text/chat.py`
- `handlers/messages/text/generation.py`
- `handlers/messages/streaming.py`
- `ai/openai_client/*`
- `tools/*`

## 7.2 系统提示词怎么组成

来源主要有三段：

1. 用户设置里的 `global_prompt`
2. 当前 persona 的 `system_prompt`
3. 代码里附加的工具执行策略和日期时间提示

组装位置：

- `services/persona.py`
- `utils/template.py`

## 7.3 多轮会话怎么保证串行

通过：

- `services/runtime_queue.py`

它做两件事：

- 同一个会话 key 同时只跑一个响应
- 同用户新请求到来时，取消旧请求

## 7.4 图片和文件处理

### 图片

- `handlers/messages/photo.py`
- 会把图片转成 base64 data URL
- 作为多模态输入交给模型

### 文档

- `handlers/messages/document.py`
- `handlers/messages/document_payload.py`
- 会根据文件类型构建模型输入

### WeChat

WeChat 的文本/文件/语音解析逻辑主要在：

- `platforms/wechat/message/`

---

## 8. Web Dashboard 与 API

## 8.1 认证方式

登录流程：

1. 用户在 Bot 里发 `/web`
2. Bot 下发短期 token 链接
3. 前端访问后调用 `/api/auth/exchange`
4. 后端把 short token 换成 JWT
5. 前端把 JWT 存在 `localStorage`

相关文件：

- `handlers/commands/web.py`
- `platforms/commands/account.py`
- `web/auth.py`
- `web/auth_tokens.py`

## 8.2 Dashboard API 分组

### 基础

- `GET /health`
- `GET /logs`
- `POST /api/auth/exchange`

### Settings

- `GET /api/settings`
- `PUT /api/settings`

### Personas

- `GET /api/personas`
- `POST /api/personas`
- `POST /api/personas/{name}/switch`
- `PUT /api/personas/{name}`
- `DELETE /api/personas/{name}`

### Providers

- `GET /api/providers`
- `POST /api/providers`
- `POST /api/providers/save-current`
- `PUT /api/providers/{name}`
- `DELETE /api/providers/{name}`
- `POST /api/providers/{name}/load`

### Models

- `GET /api/models`

### Sessions

- `GET /api/sessions`
- `POST /api/sessions`
- `GET /api/sessions/{session_id}/messages`
- `GET /api/sessions/{session_id}/export`
- `POST /api/sessions/{session_id}/switch`
- `PUT /api/sessions/{session_id}/title`
- `POST /api/sessions/{session_id}/clear`
- `DELETE /api/sessions/{session_id}`

### Memories

- `GET /api/memories`
- `POST /api/memories`
- `PUT /api/memories/{index}`
- `DELETE /api/memories/{index}`
- `DELETE /api/memories`

### Usage

- `GET /api/usage`
- `POST /api/usage/reset`
- `PUT /api/usage/token-limit`

### Logs

- `GET /api/logs`
- `DELETE /api/logs/{log_id}`
- `POST /api/logs/delete`

### Cron

- `GET /api/cron`
- `POST /api/cron`
- `PUT /api/cron/{name}`
- `DELETE /api/cron/{name}`
- `POST /api/cron/{name}/run`

### WeChat 登录辅助

- `GET /api/wechat/login`
- `POST /api/wechat/login/new`

### Artifact / Deployment

- `GET /artifacts/{token}`
- `GET /deploy/{slug}`
- `GET /deploy/{slug}/{asset_path}`

## 8.3 前端当前形态

前端不是工程化项目，而是：

- 一个 `index.html`
- 一个压缩后的 `app.js`
- 一组 CSS

优点：

- 部署简单

缺点：

- 维护性弱
- 扩展到更多页面或复杂交互会很吃力

---

## 9. 数据库表设计

当前建表逻辑在 `database/schema_sql/`，核心表如下。

## 9.1 用户设置与对话

### `user_settings`

每个用户一行，主要字段：

- `api_key`
- `base_url`
- `model`
- `temperature`
- `reasoning_effort`
- `show_thinking`
- `token_limit`
- `current_persona`
- `api_presets`
- `title_model`
- `cron_model`
- `stream_mode`
- `global_prompt`
- `tts_*`

### `user_personas`

- 用户的 persona 列表
- 每个 persona 有 `system_prompt`
- 记录当前 session id

### `user_sessions`

- 会话列表
- 按 `user_id + persona_name` 组织

### `user_conversations`

- 具体消息历史
- 字段包括 `session_id`, `role`, `content`

## 9.2 统计与记忆

### `user_persona_tokens`

- 记录每个 persona 的 token usage

### `user_memories`

- 用户记忆
- 可存 embedding

### `user_logs`

- AI 调用日志
- 错误日志
- Web 操作日志
- 终端执行日志

### `user_cron_tasks`

- 用户定时任务

## 9.3 技能与 WeChat 状态

### `user_skills`
### `user_skill_states`
### `user_skill_artifacts`

这些表还在，但当前技能管理在代码里基本被 stub 掉了。

### `wechat_runtime_state`

- 存 WeChat 登录态和轮询上下文

---

## 10. 缓存与数据库的关系

这是规划时必须明确的一层。

## 10.1 读写路径

大多数业务读写不是直接碰数据库，而是：

```text
服务层
-> cache manager
-> 脏状态记录
-> 后台 sync 写入 PostgreSQL
```

## 10.2 优点

- 读快
- 服务代码简单
- 会话状态操作方便

## 10.3 风险

### 风险 1：多进程缓存不天然强一致

Telegram、WeChat 各自一个进程，各自一份缓存。

这意味着：

- 你在 Telegram 进程内的 Web 改了设置
- WeChat 进程不一定立刻知道
- 需要依赖数据库刷新逻辑

### 风险 2：Web 也嵌在平台进程中

所以 Dashboard 实际上不是一个“统一控制面”，而是“绑定在某个子进程上的控制面”。

### 风险 3：刷新策略是 debounce + 脏状态保护

这在流量不大时够用，但如果你后面想做更强的后台管理、跨端实时联动、甚至多实例部署，就会是重点改造对象。

---

## 11. Cron 系统

主要目录：

- `services/cron/`

关键文件：

- `scheduler.py`
- `execution.py`
- `trigger.py`
- `client_factory.py`

机制：

1. 平台启动时启动 Cron scheduler
2. 轮询缓存中的任务
3. 匹配 cron expression
4. 独立线程执行
5. 生成 AI 内容
6. 回发到对应平台

补充说明：

- `title_model` 和 `cron_model` 都支持单独指定模型
- provider 解析逻辑在 `utils/provider.py`

---

## 12. Deploy / Artifact / HF Sync

这个项目除了聊天，还内置了“对象存储”和“静态部署”能力。

## 12.1 HF Sync

位置：

- `services/hf_sync/`
- `tools/hf_sync/`

作用：

- 将内容放进 Hugging Face Dataset Repo
- 支持对象上传、读取、删除、列举、复制、移动
- 可选 AES-GCM 加密

用途：

- 持久化运行时文件
- 产物下载
- Artifact 链接分发

## 12.2 静态部署

位置：

- `services/deployments/`
- `tools/quick_deploy/`
- `web/routes/integration/deployments.py`

作用：

- 把 HTML/CSS/JS 静态项目部署到 `runtime/deployments/`
- 对外通过 `/deploy/{slug}` 暴露

适合：

- 小型 demo
- 临时前端页面
- 工具生成产物展示

---

## 13. 环境变量与部署方式

## 13.1 最关键环境变量

### 基础

- `DATABASE_URL`
- `PORT`

### Telegram

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_API_BASE`

### WeChat

- `WECHAT_ENABLED`
- `WECHAT_COMMAND_PREFIX`
- `WECHAT_STATE_DIR`

### OpenAI Compatible

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_TEMPERATURE`
- `OPENAI_REASONING_EFFORT`

### Embedding

- `NVIDIA_API_KEY`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_MODEL`

### HF Dataset 持久化

- `HF_DATASET_USERNAME`
- `HF_DATASET_TOKEN`
- `HF_DATASET_NAME`
- `HF_DATASET_ENCRYPTION_KEY`

## 13.2 部署相关文件

- `Dockerfile`
- `Dockerfile.hfspace`
- `start_bots.sh`
- `.github/workflows/docker-cloud-build.yml`

当前 CI/CD 现状：

- 只有 Docker build/push workflow
- **没有自动化测试流程**

---

## 14. 现状中的“文档与代码不一致 / 历史包袱”

这部分是最适合规划前先统一认知的。

## 14.1 工具启用状态文档过时

`README.md` 里写：

- 当前只启用 `terminal`
- 当前只启用 `hf_sync`

但代码里实际注册了：

- `terminal`
- `hf_sync`
- `project_config`
- `quick_deploy`
- `scrapling`
- `sosearch`

结论：

- **README 过时，运行时代码更准**

## 14.2 `.env.example` 有过时配置项

示例里仍有：

- `ENABLED_TOOLS`
- `CRON_ENABLED_TOOLS`

但代码检索不到实际消费逻辑。

结论：

- 这两个看起来是旧设计遗留

## 14.3 技能系统是“表还在，服务基本禁用”

`services/skills/__init__.py` 当前是兼容性 stub：

- 大部分接口返回空值或报 disabled
- 但数据库表、缓存结构、部分 skill_terminal 逻辑还在

结论：

- **技能系统处于半拆不拆状态**

## 14.4 Dashboard 是真实在用的，但前端维护性差

- `static/index.html` 单页
- `static/app.js` 单文件压缩脚本

结论：

- 小改没问题
- 想继续加后台功能，很快会难维护

## 14.5 TTS 配置字段还在，但实际调用链不明显

从代码检索看：

- `tts_voice / tts_style / tts_endpoint` 仍存在于设置和 schema
- 但当前没有明显的 TTS 输出执行主链

结论：

- 这更像“预留/遗留字段”，不是成熟功能

## 14.6 有一些明显的历史残留文件

例如：

- `handlers/messages/delivery.py` 标记为 legacy removed
- `handlers/messages/tool_dispatch.py` 标记为 legacy removed
- `docs/gemini.md` 更像外部资料拷贝，不像当前项目核心文档

结论：

- 仓库已有一定历史包袱，适合做一次“真实功能面 vs 保留遗留”的梳理

## 14.7 没有测试目录

当前未发现：

- `tests/`
- `test_*.py`
- `*_test.py`

结论：

- 当前项目主要依赖手工验证
- 如果后续要重构，测试补齐要提前纳入规划

---

## 15. 如果你要改某类需求，应该从哪里下手

## 15.1 新增一个 Bot 命令

看这里：

- `platforms/commands/`
- `core/`
- Telegram 绑定：`handlers/commands/`
- WeChat 绑定：`platforms/wechat/commands/dispatch.py`

## 15.2 新增一个 Dashboard 功能页

看这里：

- 后端 API：`web/routes/dashboard/`
- 前端 HTML：`static/index.html`
- 前端逻辑：`static/app.js`

## 15.3 新增一个数据库字段

至少要看：

- `database/schema_sql/`
- `database/loaders/`
- `cache/manager/`
- `cache/sync/`
- 相关 `services/`

## 15.4 新增一个工具

看这里：

- `tools/<your_tool>/`
- `tools/core/base.py`
- `tools/__init__.py`

## 15.5 新增一个 AI Provider

看这里：

- `ai/`
- `utils/provider.py`
- `services/platform/provider.py`
- `web/routes/dashboard/models.py`

## 15.6 想把 Web 独立出去

你至少要改：

- `main.py`
- 各平台 `app.py` 中的 `start_web_server`
- `services/platform/runtime.py`
- 缓存与状态同步机制

这是一个中等以上量级改造。

---

## 16. 规划建议：最值得优先做的 6 件事

下面不是“必须”，而是基于当前结构最值得优先规划的方向。

## 16.1 先统一“真实功能清单”

建议先做一轮清理，把下面几类分开：

- 真实在用
- 半废弃但代码还在
- 文档遗留
- 表结构保留但功能关闭

优先对象：

- tools
- skills
- TTS
- docs
- `.env.example`

## 16.2 把 Web 从平台进程中解耦

这是最重要的架构升级点之一。

原因：

- 现在每个平台一个 Web 实例
- 每个平台一份缓存
- 控制面不是单点

如果后续要做：

- 统一后台
- 更清晰的部署方式
- 更强的一致性
- 多实例扩展

这一步几乎绕不开。

## 16.3 明确缓存策略：继续保留还是改为 DB-first

当前是 cache-first。

后续可以考虑两条路：

### 路线 A：继续保留缓存

适合：

- 单机部署
- 中小规模
- 重视响应速度

但要补：

- 更清晰的刷新策略
- 统一控制面
- 更明确的跨进程同步

### 路线 B：逐步转 DB-first

适合：

- 想简化一致性问题
- 想做更标准的后端服务化

代价：

- 需要重写部分 `cache/` 相关逻辑

## 16.4 把前端从单文件静态页升级为可维护结构

当前后台功能已经不少，继续堆在一个压缩 `app.js` 里会很痛苦。

最少也建议：

- 先把 `app.js` 解压成模块化原生 JS
- 再决定是否引入 React/Vue

## 16.5 给“平台适配”和“聊天主流程”做边界再清理

当前：

- Telegram 的聊天流程更多在 `handlers/`
- WeChat 更多在 `platforms/*/chat`

规划上可以考虑：

- 抽一个统一的 chat orchestration 层
- 平台只保留 adapter 和 outbound 差异

这会让多端行为更统一。

## 16.6 补测试，优先补服务层和路由层

建议优先补这几块：

- persona / session / memory / token 的 service 测试
- web routes 的 API 测试
- tool registry 的工具调用测试

先别一上来测平台 SDK，对回报率不高。

---

## 17. 推荐你下一步怎么规划

如果你准备进入正式规划阶段，我建议按这个顺序：

### 阶段 1：认知清理

- 清理 README / `.env.example` / docs 的过时内容
- 标注哪些模块已废弃
- 拉一份真实功能清单

### 阶段 2：架构定型

- 决定 Web 是否独立
- 决定缓存策略
- 决定 skill/TTS/tool 的产品边界

### 阶段 3：工程化提升

- 前端拆分
- 测试补齐
- 日志/监控补充
- 部署方案统一

### 阶段 4：功能演进

- 新平台
- 新 provider
- 新工具
- 更复杂的工作流

---

## 18. 最后给你的一个“读代码顺序”

如果你想自己继续看源码，推荐这个顺序：

1. `main.py`
2. `launcher/`
3. `platforms/telegram/app.py`
4. `handlers/messages/text/chat.py`
5. `handlers/messages/text/generation.py`
6. `tools/__init__.py`
7. `services/__init__.py`
8. `services/persona.py`
9. `services/session/`
10. `services/memory/`
11. `services/runtime_queue.py`
12. `cache/`
13. `database/schema_sql/`
14. `web/app.py`
15. `web/routes/dashboard/*`
16. `static/index.html` + `static/app.js`

按这个顺序看，理解成本最低。

---

## 19. 总结

这个项目现在已经不是一个“纯 Telegram Bot 小项目”了，而是一个：

- 多平台接入
- 多进程运行
- 带控制面
- 带工具调用
- 带对象存储
- 带定时任务
- 带状态缓存

的中型后端项目。

它的优势是功能已经很全，扩展点也不少。

它的主要问题不是“功能不够”，而是：

- 架构边界还不够清晰
- 历史遗留和当前实现混在一起
- 多进程缓存一致性需要更明确的策略
- 文档没有跟上代码演化

如果你后面要继续规划，这份文档最值得你抓住的三个关键词是：

- **多平台**
- **内嵌 Web + 进程缓存**
- **历史包袱清理**
