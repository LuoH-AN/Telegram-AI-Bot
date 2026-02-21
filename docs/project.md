# Gemen — Telegram AI Bot 完整项目说明

更新时间：2026-02-20  
适用代码：当前仓库工作区版本

---

## 1. 项目简介

Gemen 是一个运行在 Telegram 上的 AI Bot，使用 OpenAI 兼容接口与大模型交互。项目强调“聊天体验 + 数据持久化 + 工具扩展 + 多会话管理”，核心能力包括：

- 文本流式对话（含工具调用循环）
- 图片理解（Vision）
- 文件分析（文本/代码/图片）
- Persona（角色）与 Session（会话）管理
- 记忆系统（手动 + AI 自动 + 语义检索）
- TTS 语音输出
- Token 统计与限额控制
- PostgreSQL 持久化 + 内存缓存提速

项目不是 Web API 服务；HTTP 仅用于健康检查。

---

## 2. 技术栈

| 层 | 技术/库 |
|---|---|
| Bot 框架 | `python-telegram-bot==21.7` |
| 模型客户端 | `openai`（OpenAI Compatible） |
| 数据库 | PostgreSQL + `psycopg2-binary` |
| 缓存 | 进程内缓存（自研 `CacheManager`） |
| 抓取 | `tls_client` + `trafilatura` + Jina Reader |
| 搜索 | Browserless + Ollama Search API |
| TTS | Microsoft 端点（`requests` + `tenacity`） |
| 配置 | `python-dotenv` |
| 部署 | Docker (`python:3.12-slim`) |

运行方式：

- Telegram polling（`application.run_polling`）
- 应用内并发更新处理（`concurrent_updates(True)`）
- 独立后台线程定时同步缓存到数据库

---

## 3. 项目目录与文件职责

```text
gemen/
├── bot.py
├── requirements.txt
├── Dockerfile
├── README.md
│
├── config/
│   ├── settings.py
│   ├── constants.py
│   └── __init__.py
│
├── database/
│   ├── connection.py
│   ├── schema.py
│   └── __init__.py
│
├── cache/
│   ├── manager.py
│   ├── sync.py
│   └── __init__.py
│
├── services/
│   ├── __init__.py
│   ├── user_service.py
│   ├── persona_service.py
│   ├── session_service.py
│   ├── conversation_service.py
│   ├── token_service.py
│   ├── memory_service.py
│   ├── embedding_service.py
│   ├── tts_service.py
│   └── export_service.py
│
├── ai/
│   ├── base.py
│   ├── openai_client.py
│   ├── gemini_client.py
│   └── __init__.py
│
├── tools/
│   ├── registry.py
│   ├── memory.py
│   ├── search.py
│   ├── fetch.py
│   ├── wikipedia.py
│   ├── tts.py
│   └── __init__.py
│
├── handlers/
│   ├── __init__.py
│   ├── common.py
│   ├── callbacks.py
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── basic.py
│   │   ├── settings.py
│   │   ├── persona.py
│   │   ├── chat.py
│   │   ├── memory.py
│   │   └── usage.py
│   └── messages/
│       ├── __init__.py
│       ├── text.py
│       ├── photo.py
│       └── document.py
│
├── utils/
│   ├── __init__.py
│   ├── async_iter.py
│   ├── filters.py
│   ├── formatters.py
│   ├── telegram.py
│   ├── files.py
│   └── template.py
│
└── docs/
    ├── project.md
    ├── openai.md
    ├── gemini.md
    ├── browserless.md
    ├── tool-expansion-plan.md
    ├── feature-ideas.md
    ├── code-review-2026-02-20.md
    └── fix-plan-2026-02-20.md
```

---

## 4. 系统架构分层

```text
Telegram Update
  -> handlers (commands/messages/callbacks)
    -> services (业务语义 API)
      -> cache (内存状态 + dirty 标记)
        -> database (PostgreSQL 持久化)

handlers 同时会调用：
- ai (模型客户端)
- tools (tool calling)
- utils (格式化、文件识别、消息安全发送)
```

关键原则：

- 读优先走内存缓存
- 写先落缓存、后异步持久化
- 每用户隔离设置、会话、token
- 记忆在用户维度共享（跨 persona）

---

## 5. 启动与线程模型

`bot.py` 启动流程：

1. 读取配置并校验 `TELEGRAM_BOT_TOKEN`
2. `init_database()`：
   - `create_tables()` 执行 schema + migration
   - `load_from_database()` 全量加载进缓存
   - 启动 `_sync_loop`（后台 DB 同步线程）
3. 启动健康检查 HTTP 线程
4. 创建 Telegram Application（可选自定义 Telegram API Base）
5. 注册 command/message/callback handler
6. `run_polling()` 进入主循环

线程结构：

- 主线程：Telegram polling + handler 执行
- 后台线程 1：健康检查 HTTP 服务
- 后台线程 2：cache 定时同步到 PostgreSQL

---

## 6. 环境变量与运行配置

### 6.1 必需变量

| 变量 | 说明 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `DATABASE_URL` | PostgreSQL 连接串 |

### 6.2 AI 默认配置

| 变量 | 默认值 |
|---|---|
| `OPENAI_API_KEY` | 空 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | `gpt-4o` |
| `OPENAI_TEMPERATURE` | `0.7` |
| `OPENAI_SYSTEM_PROMPT` | `You are a helpful assistant.` |

### 6.3 记忆/嵌入配置

| 变量 | 默认值 |
|---|---|
| `NVIDIA_API_KEY` | 空 |
| `EMBEDDING_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `EMBEDDING_MODEL` | `baai/bge-m3` |
| `MEMORY_TOP_K` | `10` |
| `MEMORY_SIMILARITY_THRESHOLD` | `0.35` |
| `MEMORY_DEDUP_THRESHOLD` | `0.85` |

### 6.4 Tool/TTS 配置

| 变量 | 默认值 |
|---|---|
| `ENABLED_TOOLS` | `memory,search,fetch,wikipedia,tts` |
| `BROWSERLESS_API_TOKEN` | 空 |
| `OLLAMA_API_KEY` | 空 |
| `JINA_API_KEY` | 空 |
| `TTS_VOICE` | `zh-CN-XiaoxiaoMultilingualNeural` |
| `TTS_STYLE` | `general` |
| `TTS_ENDPOINT` | 空 |
| `TTS_OUTPUT_FORMAT` | `ogg-24khz-16bit-mono-opus` |

### 6.5 其他

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `8080` | 健康检查端口 |
| `TELEGRAM_API_BASE` | 空 | 自定义 Telegram API 地址 |

---

## 7. 常量与限制

`config/constants.py` 中关键限制：

| 常量 | 值 |
|---|---|
| `MAX_MESSAGE_LENGTH` | 4096 |
| `STREAM_UPDATE_INTERVAL` | 1.0s |
| `DB_SYNC_INTERVAL` | 30s |
| `MODELS_PER_PAGE` | 5 |
| `MAX_FILE_SIZE` | 20MB |
| `MAX_TEXT_CONTENT_LENGTH` | 100000 |

并定义了：

- 文本扩展名白名单 `TEXT_EXTENSIONS`
- 图片扩展名白名单 `IMAGE_EXTENSIONS`
- 图片后缀到 MIME 映射 `MIME_TYPE_MAP`
- 会话标题生成 prompt 模板 `TITLE_GENERATION_PROMPT`

---

## 8. 数据库设计（完整）

`database/schema.py` 维护建表与迁移 SQL，主要实体：

### 8.1 `user_settings`

- 用户全局配置
- 字段：`api_key/base_url/model/temperature/token_limit/current_persona/enabled_tools/tts_*`
- 迁移补充字段：`api_presets`、`title_model`

### 8.2 `user_personas`

- 每用户多个 persona
- 唯一约束：`(user_id, name)`
- 当前会话指针：`current_session_id`

### 8.3 `user_sessions`

- 每 persona 多会话
- 字段：`id/user_id/persona_name/title/created_at`

### 8.4 `user_conversations`

- 消息记录
- 关键字段：`session_id`（当前版本按会话组织消息）
- 兼容保留：`persona_name` 仍同步写入

### 8.5 `user_persona_tokens`

- 每 persona token 累积
- 主键：`(user_id, persona_name)`

### 8.6 `user_memories`

- 用户共享记忆
- 字段：`content/source/embedding`

### 8.7 `user_token_usage`（旧表）

- 旧 token 表，仅用于迁移兼容

---

## 9. 缓存层与同步层

### 9.1 CacheManager（`cache/manager.py`）

缓存对象：

- `_settings_cache`
- `_personas_cache`
- `_sessions_cache`
- `_conversations_cache`（key 为 `session_id`）
- `_persona_tokens_cache`
- `_memories_cache`

脏数据跟踪：

- settings/personas/deleted_personas
- conversations/cleared_conversations
- tokens
- new/deleted/cleared memories
- new_sessions/dirty_session_titles/deleted_sessions

线程安全：

- 内部 `threading.Lock` 保护 dirty 状态与 session id 生成

### 9.2 DB 同步（`cache/sync.py`）

- 启动时加载全量数据
- 定时取 dirty 批量写库
- 同步失败时 `restore_dirty()` 回滚标记

### 9.3 会话 ID remap

新 session 在缓存中先用临时 ID，落库后用真实 DB ID 替换。当前已覆盖 remap：

- conversations
- cleared_conversations
- deleted_sessions
- dirty_session_titles

用于避免“已删除会话落库残留”与“标题更新丢失”。

---

## 10. 服务层（`services/`）

服务层是 handler 与 cache 之间的语义接口。

### 10.1 user_service

- `get_user_settings`
- `update_user_setting`
- `get_api_key/get_base_url/get_model/get_temperature`
- `get_enabled_tools`
- `has_api_key`

### 10.2 persona_service

- `get_personas/get_persona`
- `get_current_persona/get_current_persona_name/get_system_prompt`
- `create_persona/delete_persona/switch_persona`
- `update_persona_prompt/update_current_prompt`
- `persona_exists/get_persona_count`

### 10.3 session_service

- `get_sessions/get_current_session/get_current_session_id`
- `create_session/switch_session/delete_session/rename_session`
- `get_session_count/get_session_message_count`
- `generate_session_title`（后台异步标题生成）

### 10.4 conversation_service

包含两套接口：

1. 旧接口（按用户当前 persona/session）
2. 精确接口（按 `session_id`）

关键函数：

- `get_conversation/get_conversation_by_session`
- `add_user_message/add_assistant_message`
- `add_user_message_to_session/add_assistant_message_to_session`
- `clear_conversation/get_message_count/pop_last_exchange`

### 10.5 token_service

- `get_token_usage/add_token_usage/reset_token_usage`
- `get_token_limit/set_token_limit`
- `get_total_tokens_all_personas/get_remaining_tokens/get_usage_percentage`

### 10.6 memory_service + embedding_service

- 记忆 CRUD
- 自动嵌入（可配置）
- 相似度去重
- 基于 query 的相关记忆注入

### 10.7 tts_service

- token 拉取与缓存
- 语音合成
- 音色列表缓存
- endpoint 规范化

### 10.8 export_service

- 导出当前会话为 Markdown（`BytesIO`）

---

## 11. AI 层（`ai/`）

### 11.1 抽象模型

`ai/base.py`：

- `AIClient` 抽象接口
- `StreamChunk`（content/reasoning/usage/finished/tool_calls）
- `ToolCall`（id/name/arguments）

### 11.2 OpenAIClient

`ai/openai_client.py` 提供：

- 流式/非流式 chat completion
- 流式 tool call 片段聚合
- usage 收集
- 部分模型 tool 不兼容时的降级重试
- 模型列表拉取 `list_models()`

### 11.3 gemini_client

- 当前为占位实现（`NotImplementedError`）

---

## 12. Tool 系统（`tools/`）

### 12.1 注册与分发

`tools/registry.py`：

- `BaseTool`
- `ToolRegistry`
- 按 `enabled_tools` 过滤定义与执行

### 12.2 memory tool

函数：`save_memory(content)`

- 调用 `memory_service.add_memory`
- 支持 regex fallback 从模型回复提取记忆标记
- 可把相关记忆注入 system prompt

### 12.3 search tool

函数：`web_search(query, provider, max_results)`

- provider：`browserless` / `ollama` / `all`
- 聚合结果并按 URL 去重

### 12.4 fetch tool（安全加固版）

函数：`url_fetch(url, method, max_length)`

- method：`default` / `jina`
- 仅允许 HTTP(S)
- 拒绝本地与非公网地址
- 重定向逐跳校验
- 支持文本/HTML/JSON 提取

### 12.5 wikipedia tool

函数：`wikipedia_search(query, language)`

- 语言：`en`/`zh`
- 返回前几条摘要结果

### 12.6 tts tool

函数：

- `tts_speak(text, voice_name, style, rate, pitch, output_format)`
- `tts_list_voices(locale, limit)`

机制：

- 合成后写入待发送队列
- 文本 handler 结束时统一出队发送 voice

---

## 13. Handler 层（完整）

### 13.1 commands

#### `basic.py`

- `/start`
- `/help`
- `/clear`

#### `settings.py`

- `/settings`
- `/set ...`

支持项：

- `base_url/api_key/model/temperature/token_limit`
- `voice/style/endpoint`
- `tool <name> <on|off>`
- `provider list/save/load/delete`
- `title_model`

#### `persona.py`

- `/persona`
- `/persona new <name> [prompt]`
- `/persona delete <name>`
- `/persona prompt <text>`
- `/persona <name>`（切换）

#### `chat.py`

- `/chat`（列出会话）
- `/chat new [title]`
- `/chat <index>`
- `/chat rename <title>`
- `/chat delete <index>`

#### `memory.py`

- `/remember`
- `/memories`
- `/forget <num|all>`

#### `usage.py`

- `/usage`
- `/export`

### 13.2 callbacks

- `model:*` 和 `models_page:*`：模型选择/分页
- `help:*`：帮助分区内容切换

### 13.3 common

- `should_respond_in_group`：群聊响应控制
- `collect_media_group_messages`：图片/文件分组聚合

### 13.4 messages/text.py

特点：

- 文本主链路
- 具备 tool call 循环
- 流式更新显示
- 固定请求上下文（persona/session 快照）
- 精确按 session 写入

### 13.5 messages/photo.py

特点：

- 支持单图与多图组（media group）
- 非阻塞流式消费
- token 限额检查

### 13.6 messages/document.py

特点：

- 支持单文件与多文件组（media group）
- 文本/图片混合批次处理
- 非阻塞流式消费
- token 限额检查

---

## 14. 用户可见行为约束

### 14.1 Provider 命令语义

当前必须显式 `load`：

- `/set provider load <name>`

### 14.2 错误提示

用户侧统一：

- `Error. Please retry.`

详细异常仅写日志。

### 14.3 token 限额

限额对文本/图片/文件入口一致生效。

### 14.4 多媒体分组

同一个 Telegram media group 中的多图片或多文件会作为一次请求处理。

---

## 15. 实时响应与流式策略

### 15.1 文本流式更新

- 首个可见 chunk 立即更新
- 后续按 `STREAM_UPDATE_INTERVAL` 节流
- 使用占位光标 `▌`

### 15.2 thinking/reasoning 处理

- 过滤 `<think>` 等标签
- 支持 reasoning 字段识别
- 最终输出剥离思维链内容

### 15.3 消息发送安全

`utils/telegram.py`：

- 优先 HTML 发送
- 失败自动降级纯文本
- 超长消息自动分片

---

## 16. 并发与一致性设计

已实现的关键一致性策略：

1. handler 开始时冻结 `persona_name + session_id`
2. 会话写入使用 `*_to_session(session_id, ...)`
3. token 写入显式 persona 参数
4. session remap 同步补齐 deleted/title 映射

这些策略主要针对并发更新条件下的上下文错位问题。

---

## 17. 安全设计

### 17.1 URL 抓取安全

`fetch` 工具防护点：

- 协议限制（HTTP/HTTPS）
- 禁止 localhost/.local
- DNS 解析后 IP 需为公网地址
- 重定向逐跳校验

### 17.2 群聊触发边界

群聊仅在以下条件响应：

- 用户 @bot
- 用户回复 bot 消息

### 17.3 敏感信息展示

- `/settings` 中 API Key 仅脱敏显示
- 日志记录上下文信息，避免直接回显内部调用细节给用户

---

## 18. 工具函数层（`utils/`）

- `async_iter.py`：把阻塞 iterator 包装为 async 迭代
- `filters.py`：thinking 标签过滤
- `formatters.py`：Markdown -> Telegram HTML + LaTeX 到 Unicode + 消息分片
- `telegram.py`：发送/编辑消息的安全封装
- `files.py`：文件扩展识别 + 文本内容识别与解码
- `template.py`：时间上下文模板

---

## 19. 典型数据流

### 19.1 文本对话

1. Telegram text update
2. `chat()` 做权限与限额检查
3. 构建 messages + tools
4. 流式调用模型
5. 有 tool call 则执行工具并继续
6. 输出最终文本
7. 按 session 落库
8. token 记账

### 19.2 图片/文件对话

1. 聚合同组媒体
2. 下载并组装 payload
3. 流式模型调用
4. 输出与落库

### 19.3 数据持久化

1. cache 标脏
2. 后台线程周期同步
3. 同步失败回滚 dirty，等待重试

---

## 20. 部署与运维

### 20.1 Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
COPY config/ ./config/
COPY database/ ./database/
COPY cache/ ./cache/
COPY services/ ./services/
COPY ai/ ./ai/
COPY handlers/ ./handlers/
COPY tools/ ./tools/
COPY utils/ ./utils/
CMD ["python", "bot.py"]
```

### 20.2 健康检查

- 应用内 HTTP 服务返回 `OK`
- 端口来自 `PORT`（默认 8080）

### 20.3 生产建议

- 使用稳定 PostgreSQL 实例
- 为 bot 进程配置重启策略
- 对 `fetch/search/tts` 第三方依赖配置超时和密钥轮换

---

## 21. 测试与质量现状

当前仓库暂无自动化测试文件。建议补齐：

1. `fetch` URL 安全校验单测
2. media group 聚合行为测试
3. session remap 一致性测试
4. 并发下 session 精确写入测试

---

## 22. 相关文档

- `README.md`：用户使用与部署入口
- `docs/openai.md`：OpenAI 相关说明
- `docs/gemini.md`：Gemini 规划
- `docs/browserless.md`：Browserless 相关
- `docs/tool-expansion-plan.md`：工具扩展规划
- `docs/code-review-2026-02-20.md`：审查记录
- `docs/fix-plan-2026-02-20.md`：修复计划与执行清单

---

## 23. 版本注记（2026-02-20）

本版本已落地的重要修复：

1. `url_fetch` SSRF 风险防护
2. 图片/文件 handler 非阻塞流式处理
3. session 临时 ID remap 完整化
4. 图片/文件入口 token 限额补齐
5. 并发场景 session 写入上下文固定
6. 用户错误信息脱敏
7. provider 命令改为显式 `load`
8. 多图/多文件按 media group 聚合单次处理
