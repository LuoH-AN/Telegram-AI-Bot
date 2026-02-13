# Gemen — Telegram AI Bot 架构文档

## 1. 项目概述

Gemen 是一个功能丰富的 Telegram AI 聊天机器人，基于 `python-telegram-bot` 构建，通过 OpenAI 兼容 API 与大语言模型交互。核心特性包括：流式响应、多 Persona（角色）系统、语义记忆（向量嵌入）、工具调用（搜索/抓取/Wikipedia/TTS）、图片与文件处理、Token 追踪与限额。部署目标为 Hugging Face Spaces（Docker）。

**技术栈：**

| 层级 | 技术 |
|------|------|
| Bot 框架 | `python-telegram-bot` 21.7（长轮询） |
| AI 客户端 | `openai` SDK（兼容 OpenAI/DeepSeek/Anthropic 等） |
| 数据库 | PostgreSQL（`psycopg2-binary`） |
| 向量嵌入 | NVIDIA API / OpenAI 兼容格式（`baai/bge-m3`） |
| 网页抓取 | `tls_client`（TLS 指纹）+ `trafilatura`（正文提取）+ Jina Reader |
| 网页搜索 | Browserless（无头浏览器爬虫）+ Ollama Search API |
| TTS | Azure Cognitive Services 兼容端点 |
| 配置 | `python-dotenv` |
| 容错 | `tenacity`（重试） |
| 部署 | Docker（Python 3.12-slim），健康检查 HTTP 服务器 |

项目**不是** Flask/FastAPI/Django 等 Web 框架应用，唯一的 HTTP 端点是用于容器存活探测的健康检查服务器。

---

## 2. 目录结构

```
gemen/
├── bot.py                          # 入口：启动 bot + 健康检查 HTTP 服务
├── requirements.txt                # Python 依赖
├── Dockerfile                      # 容器定义
├── README.md
│
├── config/                         # 配置层
│   ├── settings.py                 # 环境变量加载、默认设置工厂函数
│   ├── constants.py                # 不可变常量（消息长度、文件类型、同步间隔等）
│   └── __init__.py
│
├── database/                       # 持久化层
│   ├── connection.py               # PostgreSQL 连接管理
│   ├── schema.py                   # 建表 SQL + 迁移 SQL + create_tables()
│   └── __init__.py
│
├── cache/                          # 内存缓存层
│   ├── manager.py                  # CacheManager：5 类缓存 + dirty 跟踪 + 线程锁
│   ├── sync.py                     # 后台同步：加载 → 定时写回 → 失败回滚
│   └── __init__.py
│
├── services/                       # 业务逻辑层（cache 的薄封装）
│   ├── user_service.py             # 用户设置 CRUD
│   ├── persona_service.py          # Persona CRUD + 切换
│   ├── conversation_service.py     # 对话历史管理
│   ├── token_service.py            # Token 用量追踪与限额
│   ├── memory_service.py           # 记忆 CRUD + 向量嵌入 + 语义去重 + prompt 格式化
│   ├── embedding_service.py        # 向量嵌入生成 + 余弦相似度计算
│   ├── tts_service.py              # TTS 语音合成 + 音色列表缓存
│   ├── export_service.py           # 对话导出为 Markdown
│   └── __init__.py
│
├── ai/                             # AI 客户端抽象层
│   ├── base.py                     # ABC: AIClient + 数据类 StreamChunk/ToolCall
│   ├── openai_client.py            # OpenAI 兼容实现（流式/非流式/tool calling）
│   ├── gemini_client.py            # Gemini 占位（未实现）
│   └── __init__.py                 # 工厂函数 get_ai_client() / get_openai_client()
│
├── tools/                          # 可扩展工具系统
│   ├── registry.py                 # BaseTool ABC + ToolRegistry 单例
│   ├── memory.py                   # MemoryTool：记忆保存（tool call + regex fallback + 向量检索注入）
│   ├── search.py                   # SearchTool：Browserless + Ollama 双引擎搜索
│   ├── fetch.py                    # FetchTool：URL 内容抓取（直接请求 / Jina Reader）
│   ├── wikipedia.py                # WikipediaTool：维基百科摘要检索
│   ├── tts.py                      # TTSTool：TTS 语音生成 + 待发送队列
│   └── __init__.py                 # 注册所有 tool，导出公开 API
│
├── handlers/                       # Telegram 更新处理器
│   ├── common.py                   # 群聊响应判断 + 日志上下文
│   ├── callbacks.py                # InlineKeyboard 回调（model 选择/翻页、帮助分类、persona 选择）
│   ├── commands/
│   │   ├── basic.py                # /start, /help, /clear, /retry
│   │   ├── settings.py             # /settings, /set（含 model 列表分页）
│   │   ├── persona.py              # /persona（list/new/delete/prompt/switch）
│   │   ├── memory.py               # /remember, /memories, /forget
│   │   ├── usage.py                # /usage, /export
│   │   └── __init__.py
│   ├── messages/
│   │   ├── text.py                 # 文本消息 → 流式 AI 回复 + tool calling 循环
│   │   ├── photo.py                # 图片消息 → vision 模型
│   │   ├── document.py             # 文件上传 → 文本/图片分流
│   │   └── __init__.py
│   └── __init__.py
│
├── utils/                          # 工具函数
│   ├── telegram.py                 # send_message_safe() / edit_message_safe()（HTML → 纯文本降级）
│   ├── filters.py                  # filter_thinking_content()（过滤 <think> 等标签）
│   ├── formatters.py               # Markdown → Telegram HTML 转换 + 消息分片
│   ├── files.py                    # 文件类型检测 + 解码
│   └── __init__.py
│
└── docs/                           # 文档
```

---

## 3. 分层架构

```
┌───────────────────────────────────────────────────────┐
│                  Telegram (长轮询)                      │
└────────────────────────┬──────────────────────────────┘
                         │ Update
┌────────────────────────▼──────────────────────────────┐
│              bot.py (入口 + Handler 注册)                │
│  CommandHandler × 12 · MessageHandler × 3 · Callback × 2│
└────────────────────────┬──────────────────────────────┘
                         │
┌────────────────────────▼──────────────────────────────┐
│               handlers/ (请求处理层)                     │
│  commands/  messages/  callbacks.py  common.py          │
└──┬─────────┬──────────┬──────────┬────────────────────┘
   │         │          │          │
   │   ┌─────▼────┐  ┌──▼───┐  ┌──▼──────┐
   │   │ tools/   │  │ ai/  │  │ utils/  │
   │   │ Registry │  │Client│  │ 格式化  │
   │   └─────┬────┘  └──┬───┘  └─────────┘
   │         │          │
   ├─────────┴──────────┘
   │
┌──▼──────────────────────────────────────────────────┐
│               services/ (业务逻辑层)                   │
└──────────────────────────┬──────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────┐
│           cache/ (内存缓存 + dirty 跟踪)               │
│     CacheManager 单例 · threading.Lock 保护            │
└──────────────────────────┬──────────────────────────┘
                           │ 后台线程 (每 30s)
┌──────────────────────────▼──────────────────────────┐
│           database/ (PostgreSQL 持久化)                │
└─────────────────────────────────────────────────────┘
```

---

## 4. 启动流程 (bot.py)

```
main()
  ├─ 校验 TELEGRAM_BOT_TOKEN
  ├─ init_database()                     # cache/sync.py
  │    ├─ create_tables(conn)            # 建表 + 迁移
  │    ├─ load_from_database()           # 加载全部数据到内存缓存
  │    └─ 启动后台同步线程 _sync_loop    # daemon thread, 每 30s 写回
  ├─ 启动健康检查 HTTP 服务 (daemon thread)
  │    └─ HTTPServer(0.0.0.0:PORT)       # GET/HEAD → 200 OK
  ├─ 构建 Application
  │    ├─ .concurrent_updates(True)      # 并发处理更新
  │    └─ 可选自定义 Telegram API base URL
  ├─ 注册 Handler
  │    ├─ CommandHandler × 12
  │    ├─ CallbackQueryHandler × 2 (model 选择 + help 分类)
  │    └─ MessageHandler × 3 (text / photo / document)
  ├─ 注册 error_handler
  └─ application.run_polling()
```

---

## 5. 环境变量

### 必需

| 变量 | 说明 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API Token |
| `DATABASE_URL` | PostgreSQL 连接字符串 |

### AI / API 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | 空 | 全局默认 API Key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 全局默认 API Base URL |
| `OPENAI_MODEL` | `gpt-4o` | 全局默认模型 |
| `OPENAI_TEMPERATURE` | `0.7` | 全局默认 Temperature |
| `OPENAI_SYSTEM_PROMPT` | `You are a helpful assistant.` | 默认系统提示词 |

### 嵌入 / 记忆

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NVIDIA_API_KEY` | 空 | 嵌入 API Key（启用向量检索） |
| `EMBEDDING_BASE_URL` | `https://integrate.api.nvidia.com/v1` | 嵌入 API 地址 |
| `EMBEDDING_MODEL` | `baai/bge-m3` | 嵌入模型 |
| `MEMORY_TOP_K` | `10` | 向量检索返回最大条数 |
| `MEMORY_SIMILARITY_THRESHOLD` | `0.35` | 检索最低相似度 |
| `MEMORY_DEDUP_THRESHOLD` | `0.85` | 去重相似度（超过视为重复并替换） |

### 工具 / TTS

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENABLED_TOOLS` | `memory,search,fetch,wikipedia,tts` | 默认启用的工具 |
| `BROWSERLESS_API_TOKEN` | 空 | Browserless API Token |
| `OLLAMA_API_KEY` | 空 | Ollama Search API Key |
| `JINA_API_KEY` | 空 | Jina Reader API Key |
| `TTS_VOICE` | `zh-CN-XiaoxiaoMultilingualNeural` | 默认 TTS 音色 |
| `TTS_STYLE` | `general` | 默认 TTS 风格 |
| `TTS_ENDPOINT` | 空 | TTS 端点主机/区域 |
| `TTS_OUTPUT_FORMAT` | `ogg-24khz-16bit-mono-opus` | TTS 输出格式 |

### 基础设施

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `8080` | 健康检查 HTTP 端口 |
| `TELEGRAM_API_BASE` | 空 | 自定义 Telegram API 地址 |

---

## 6. 应用常量 (config/constants.py)

| 常量 | 值 | 说明 |
|------|----|------|
| `MAX_MESSAGE_LENGTH` | 4096 | Telegram 单条消息字符上限 |
| `STREAM_UPDATE_INTERVAL` | 1.0s | 流式输出刷新间隔 |
| `DB_SYNC_INTERVAL` | 30s | 后台数据库同步间隔 |
| `MODELS_PER_PAGE` | 5 | model 列表每页显示数 |
| `MAX_FILE_SIZE` | 20MB | 文件上传大小限制 |
| `MAX_TEXT_CONTENT_LENGTH` | 100,000 | 文本文件最大处理字符数 |
| `TEXT_EXTENSIONS` | 60+ 种扩展名 | 可识别的文本/代码文件类型 |
| `IMAGE_EXTENSIONS` | jpg/png/gif/webp/bmp | 可识别的图片文件类型 |

---

## 7. 数据库设计

PostgreSQL，5 张表 + 1 张旧表（用于迁移）。

### user_settings — 用户全局设置

```sql
user_id         BIGINT PRIMARY KEY
api_key         TEXT
base_url        TEXT
model           TEXT
temperature     REAL
token_limit     BIGINT DEFAULT 0
current_persona TEXT DEFAULT 'default'
enabled_tools   TEXT
tts_voice       TEXT
tts_style       TEXT
tts_endpoint    TEXT
```

### user_personas — 角色定义

```sql
id              SERIAL PRIMARY KEY
user_id         BIGINT NOT NULL
name            TEXT NOT NULL
system_prompt   TEXT NOT NULL
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
UNIQUE(user_id, name)
```

索引: `idx_personas_user_id ON user_personas(user_id)`

### user_conversations — 对话历史（按 persona 隔离）

```sql
id              SERIAL PRIMARY KEY
user_id         BIGINT NOT NULL
persona_name    TEXT NOT NULL DEFAULT 'default'
role            TEXT NOT NULL          -- 'user' | 'assistant'
content         TEXT NOT NULL
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

索引: `idx_conversations_user_persona ON user_conversations(user_id, persona_name)`

### user_persona_tokens — 每 persona 的 Token 用量

```sql
user_id             BIGINT NOT NULL
persona_name        TEXT NOT NULL
prompt_tokens       BIGINT DEFAULT 0
completion_tokens   BIGINT DEFAULT 0
total_tokens        BIGINT DEFAULT 0
PRIMARY KEY (user_id, persona_name)
```

### user_memories — 记忆（跨 persona 共享）

```sql
id              SERIAL PRIMARY KEY
user_id         BIGINT NOT NULL
content         TEXT NOT NULL
source          TEXT NOT NULL DEFAULT 'user'   -- 'user' | 'ai'
embedding       TEXT                           -- 向量嵌入 JSON '[0.1, 0.2, ...]'
created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

索引: `idx_memories_user_id ON user_memories(user_id)`

> 嵌入向量以 JSON 文本存储在 `TEXT` 列，无需 pgvector 扩展。

### user_token_usage — 旧表（仅供迁移）

启动时将旧表中的 `token_limit` 和 token 用量迁移到 `user_settings` 和 `user_persona_tokens`。

---

## 8. 缓存架构 (cache/)

### 设计原则

**内存优先、异步持久化。** 所有读写操作走内存缓存，通过 dirty flag 跟踪变更，后台线程定时批量写回 PostgreSQL。

### CacheManager (cache/manager.py)

**缓存结构：**

```python
_settings_cache:        dict[user_id, settings_dict]
_personas_cache:        dict[user_id, dict[persona_name, persona_dict]]
_conversations_cache:   dict[(user_id, persona_name), list[message]]
_persona_tokens_cache:  dict[(user_id, persona_name), usage_dict]
_memories_cache:        dict[user_id, list[memory_dict]]
```

**Dirty 标记（共 9 类）：**

```python
_dirty_settings:         set[user_id]              # 设置变更
_dirty_personas:         set[(user_id, persona)]    # persona 变更
_deleted_personas:       set[(user_id, persona)]    # persona 删除
_dirty_conversations:    set[(user_id, persona)]    # 对话新增
_cleared_conversations:  set[(user_id, persona)]    # 对话清空
_dirty_tokens:           set[(user_id, persona)]    # token 变更
_new_memories:           list[memory_dict]           # 新增记忆
_deleted_memory_ids:     list[int]                   # 删除的记忆 ID
_cleared_memories:       set[user_id]               # 记忆全清
```

所有 dirty 操作在 `threading.Lock` 保护下执行。

### 同步逻辑 (cache/sync.py)

```
init_database()
  ├─ create_tables()        # 建表 + 执行迁移 SQL
  ├─ load_from_database()   # DB → 内存缓存（含旧表迁移）
  └─ 启动 _sync_loop        # daemon thread

_sync_loop (每 30s):
  ├─ cache.get_and_clear_dirty()   # 原子取出 dirty flags
  ├─ sync_to_database()            # 逐项写回 PostgreSQL
  │   ├─ UPSERT settings
  │   ├─ DELETE 已删 personas + 关联 conversations/tokens
  │   ├─ UPSERT personas
  │   ├─ DELETE 已清空 conversations
  │   ├─ INSERT 增量 conversations（只写缓存中比 DB 多出的部分）
  │   ├─ UPSERT token usage
  │   ├─ DELETE 已清空 / 已删 memories
  │   └─ INSERT 新 memories（RETURNING id 回写缓存）
  └─ 失败 → cache.restore_dirty()  # 回滚 dirty flags
```

---

## 9. AI 客户端 (ai/)

### 抽象基类

```python
class AIClient(ABC):
    def chat_completion(messages, model, temperature, stream, tools) -> Iterator[StreamChunk]
    def list_models() -> list[str]

@dataclass
class StreamChunk:
    content: str | None       # 文本内容
    reasoning: str | None     # 推理/思考内容（DeepSeek R1 等）
    usage: dict | None        # {prompt_tokens, completion_tokens}
    finished: bool            # 流结束标志
    tool_calls: list[ToolCall]

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON 字符串
```

### OpenAIClient (ai/openai_client.py)

基于 `openai` SDK，兼容所有 OpenAI 接口的 API 提供商：

- **流式响应**：逐 chunk 产出内容、推理、用量和工具调用
- **工具调用聚合**：流式模式下跨 chunk 收集 `tool_call_chunks`（按 index 拼接 id/name/arguments），流结束时编译为完整 `ToolCall` 列表
- **推理内容捕获**：读取 `delta.reasoning_content` 或 `delta.reasoning` 字段（兼容 DeepSeek R1 等模型）
- **工具不兼容自动降级**：首次调用失败且错误信息含 "tool"/"function" 时，自动去掉 `tools` 参数重试
- **非流式支持**：用于 `list_models()` 以及特殊场景

### 工厂函数

- `get_ai_client(user_id)` → 根据用户设置创建 OpenAIClient
- `get_openai_client(user_id)` → 直接创建 OpenAIClient

---

## 10. Handler 详解

### 10.1 命令 Handler

| 命令 | 文件 | 功能 |
|------|------|------|
| `/start` | `commands/basic.py` | 新用户引导设置 API Key；老用户简短问候 |
| `/help` | `commands/basic.py` | 概要 + InlineKeyboard 分类（Personas/Settings/Memory/Advanced） |
| `/clear` | `commands/basic.py` | 清除当前 persona 对话 + 重置 token 用量 |
| `/retry` | `commands/basic.py` | 移除上一轮 assistant 回复后重新调用 chat |
| `/persona` | `commands/persona.py` | 子命令路由（见下） |
| `/settings` | `commands/settings.py` | 显示当前配置（API key 脱敏） |
| `/set` | `commands/settings.py` | 修改配置项（含 model 列表分页） |
| `/remember` | `commands/memory.py` | 手动添加记忆 |
| `/memories` | `commands/memory.py` | 列出所有记忆（👤 用户 / 🤖 AI 来源标记） |
| `/forget` | `commands/memory.py` | 删除记忆（按编号或全部） |
| `/usage` | `commands/usage.py` | 显示 token 用量（当前 persona + 全局汇总） |
| `/export` | `commands/usage.py` | 导出当前 persona 对话为 Markdown 文件 |

**`/persona` 子命令：**

```
/persona                      → 列出所有 persona（标记当前项，显示消息数/token 数）
/persona <name>               → 切换到指定 persona（不存在时提示创建）
/persona new <name> [prompt]  → 创建新 persona 并切换
/persona delete <name>        → 删除 persona（不能删 default）
/persona prompt <text>        → 设置当前 persona 的 system prompt
/persona prompt               → 查看当前 prompt
```

**`/set` 可配置项：**

```
/set base_url <url>           → API 地址
/set api_key <key>            → API Key（设置后自动调用 list_models 验证）
/set model                    → 浏览模型列表（InlineKeyboard 分页）
/set model <name>             → 直接设置模型名
/set temperature <0.0-2.0>    → 温度
/set token_limit <number>     → 全局 token 限额（0 = 无限）
/set voice <voice_name>       → TTS 音色
/set style <style_name>       → TTS 风格
/set endpoint <region|host>   → TTS 区域/主机
/set tool <name> <on|off>     → 开关工具
```

### 10.2 消息 Handler

#### 文本消息 (messages/text.py → chat())

完整流程：

```
1.  群聊检查 should_respond_in_group()
2.  去掉 @bot mention
3.  检查 API key 是否已设置
4.  检查 token 限额（get_remaining_tokens()）
5.  发送 ChatAction.TYPING 指示器
6.  发送占位消息 "…"
7.  构建 system prompt:
    a. persona prompt
    b. tools.enrich_system_prompt() → MemoryTool 注入向量检索到的相关记忆
    c. tools.get_tool_instructions() → 各 tool 的 fallback 说明
8.  构建 messages = [system] + conversation_history + [user_message]
9.  获取 tool 定义 → tools.get_all_tools()
10. 进入 tool call 循环 (最多 MAX_TOOL_ROUNDS=3 轮 + 1):
    a. _stream_response() 流式获取 AI 回复
       - 首个可见 chunk 立即更新（跳过节流）
       - 后续按 STREAM_UPDATE_INTERVAL (1s) 节流，带 "▌" 光标
       - 检测思考状态：reasoning 字段或 <think> 标签 → 显示 "Thinking..."
    b. 累加 token 用量
    c. 如果无 tool_calls → break
    d. 显示工具执行状态（🔍 Searching... / 🌐 Fetching... 等）
    e. 执行 tool calls（30s 超时保护）
    f. 构建 assistant + tool result messages 追加到 messages
11. 出队并发送 TTS 待发送语音消息
12. 过滤 thinking 标签 → 后处理（regex fallback 记忆提取等）
13. 超长消息：删除占位 → 分片发送；正常：编辑占位消息
14. 保存对话到缓存 + 保存 last_message（供 /retry）
15. 记录 token 用量
```

#### 图片消息 (messages/photo.py)

下载图片 → base64 编码 → 构建 vision 消息 → 流式 AI 回复 → 保存对话 (`[Image]` + caption)

#### 文件上传 (messages/document.py)

检查大小 (≤20MB) → 判断类型 → 图片走 vision 处理 → 文本/代码截断后包裹为 `[File: name]\n```content```\ncaption` → 流式 AI 回复 → 保存对话

### 10.3 Callback Handler (callbacks.py)

| 回调模式 | 处理 |
|---------|------|
| `model:<name>` | 设置模型 |
| `models_page:<n>` | model 列表翻页 |
| `models_noop` | 忽略（页码显示按钮） |
| `help:personas` | 显示 Persona 帮助 |
| `help:settings` | 显示 Settings 帮助 |
| `help:memory` | 显示 Memory 帮助 |
| `help:advanced` | 显示高级功能帮助 |

### 10.4 群聊判断 (common.py)

私聊始终响应。群聊仅在以下情况响应：
- 回复 bot 的消息
- `@bot` mention（消息文本 / caption / entities）

---

## 11. Service 层

薄封装层，所有函数直接操作 `cache` 单例，为 handler 提供语义化 API。

| 模块 | 核心函数 |
|------|---------|
| `user_service` | `get_user_settings`, `update_user_setting`, `get_api_key`, `get_base_url`, `get_model`, `get_temperature`, `has_api_key` |
| `persona_service` | `get_personas`, `get_current_persona`, `get_system_prompt`, `switch_persona`（不存在自动创建）, `create_persona`, `delete_persona`, `update_persona_prompt` |
| `conversation_service` | `get_conversation`, `add_user_message`, `add_assistant_message`, `clear_conversation`, `get_message_count` |
| `token_service` | `get_token_usage`, `add_token_usage`, `get_remaining_tokens`, `get_usage_percentage`, `reset_token_usage`, `get_total_tokens_all_personas` |
| `memory_service` | `get_memories`, `add_memory`（自动嵌入 + 语义去重）, `delete_memory`, `clear_memories`, `format_memories_for_prompt(query=...)` |
| `embedding_service` | `get_embedding`, `get_embeddings_batch`, `cosine_similarity`, `is_available` |
| `tts_service` | `synthesize_voice`, `get_voice_list`, `normalize_tts_endpoint`, `guess_audio_extension` |
| `export_service` | `export_to_markdown()` → BytesIO |

---

## 12. 工具系统 (tools/)

### 架构设计

Handler 层只与 ToolRegistry 单例交互，tool 的增删不需要修改任何 handler 代码。

```python
# BaseTool 生命周期钩子
class BaseTool(ABC):
    name: str                                           # 标识名（用于 enabled_tools 过滤）
    definitions() -> list[dict]                         # OpenAI function-calling 格式定义
    execute(user_id, tool_name, arguments) -> str|None  # 执行，返回结果（None = fire-and-forget）
    get_instruction() -> str                            # 追加到 system prompt 的说明
    enrich_system_prompt(user_id, prompt, **kw) -> str  # 预处理注入上下文
    post_process(user_id, text) -> str                  # 后处理 AI 回复
```

```python
# ToolRegistry 公开 API
registry.get_definitions(enabled_tools)       # 合并 tool 定义
registry.process_tool_calls(user_id, calls)   # 分发 tool call 到对应 tool
registry.get_instructions(enabled_tools)      # 合并 tool 指令
registry.enrich_system_prompt(user_id, prompt)# 依次调用 tool 的 prompt 注入
registry.post_process(user_id, text)          # 依次调用 tool 的后处理
```

所有公开 API 支持 `enabled_tools` 参数过滤，基于用户设置中的 `enabled_tools` 字符串（逗号分隔）。

### 已注册 Tool

#### MemoryTool (`memory.py`)

| 功能 | 说明 |
|------|------|
| tool call | `save_memory(content)` → 调用 `memory_service.add_memory()`（自动嵌入 + 去重） |
| enrich | 以用户消息为 query 做向量相似度检索，将 top-K 相关记忆注入 system prompt |
| post_process | regex fallback 提取 `[MEMORY: ...]`、`[记忆: ...]`、`<memory>...</memory>` |
| instruction | 记忆使用提示 + fallback 格式说明 |

#### SearchTool (`search.py`)

| 功能 | 说明 |
|------|------|
| tool call | `web_search(query, provider, max_results)` |
| provider | `browserless`（Browserless `/scrape` 爬取 DuckDuckGo）/ `ollama`（Ollama `/api/web_search`）/ `all`（两者同时） |
| 结果 | title + URL + snippet，按 URL 去重，最多 10 条 |
| 依赖 | `BROWSERLESS_API_TOKEN` 和/或 `OLLAMA_API_KEY` |

#### FetchTool (`fetch.py`)

| 功能 | 说明 |
|------|------|
| tool call | `url_fetch(url, method, max_length)` |
| default 模式 | `tls_client`（Chrome 124 指纹）+ `trafilatura` 正文提取；支持 HTML/JSON/text |
| jina 模式 | Jina Reader API，适合 JS 重页面，返回 clean Markdown |
| 截断 | 默认 5000 字符上限 |
| 依赖 | `JINA_API_KEY`（jina 模式） |

#### WikipediaTool (`wikipedia.py`)

| 功能 | 说明 |
|------|------|
| tool call | `wikipedia_search(query, auto_suggest)` |
| 结果 | Wikipedia 文章摘要 |

#### TTSTool (`tts.py`)

| 功能 | 说明 |
|------|------|
| tool call | `tts_speak(text, voice_name, style, rate, pitch, output_format)` |
| tool call | `tts_list_voices(locale, limit)` |
| 执行 | 调用 `tts_service.synthesize_voice()` 合成音频 → 放入 `_PENDING_JOBS` 队列 |
| 发送 | `handlers/messages/text.py` 在同轮对话结束后调用 `drain_pending_tts_jobs()` 出队 → `reply_voice` 发送 |
| 音色优先级 | 用户 `/set voice` 设定 > AI 请求的 `voice_name` > 环境变量默认值 |
| 限制 | 单次最多 2000 字符 |

### 扩展新 Tool

```python
# 1. tools/my_tool.py
class MyTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_tool"
    def definitions(self) -> list[dict]: ...
    def execute(self, user_id, tool_name, arguments) -> str | None: ...

# 2. tools/__init__.py 加一行
from .my_tool import MyTool
registry.register(MyTool())
```

用户通过 `/set tool my_tool on` 启用。Handler 层零修改。

---

## 13. 工具函数 (utils/)

### filters.py — filter_thinking_content(text, streaming=False)

过滤 AI 回复中的思维链标签：`<think>`、`<thinking>`、`<reasoning>`、`[thinking]`。

- `streaming=True`：过滤后为空时返回空，触发 "Thinking..." 指示器
- `streaming=False`（默认）：过滤后为空时兜底只移除标签保留内容，避免最终回复为空
- 处理流式中未闭合的标签（从开标签到文本末尾）

### telegram.py

- `send_message_safe(message, text)`: 发送消息，HTML → 纯文本降级，超长自动分片
- `edit_message_safe(message, text)`: 编辑消息，HTML → 纯文本降级，处理 RetryAfter 和 "not modified"

### formatters.py

- `markdown_to_telegram_html(text)`: Markdown → Telegram HTML
  - 保护代码块/行内代码 → 转换标题/加粗/斜体/链接/列表/分隔线 → HTML 转义非代码文本
- `split_message(text, max_length)`: 按段落 → 行 → 强制拆分

### files.py

- `get_file_extension` / `is_text_file` / `is_image_file`：按扩展名判断
- `is_likely_text(data)`：按内容探测（UTF-8 解码 + 可打印字符 >90%）
- `decode_file_content(file_bytes)`：UTF-8 → Latin-1 降级解码

---

## 14. 数据流

### 用户发送文本消息

```
Telegram → run_polling() → MessageHandler → chat()
  ├─ cache.get_settings()                          # 读缓存：设置
  ├─ cache.get_conversation()                      # 读缓存：对话历史
  ├─ get_system_prompt()                           # 当前 persona 的 prompt
  ├─ tools.enrich_system_prompt(query=msg)
  │    └─ MemoryTool.enrich_system_prompt()
  │         ├─ embedding_service.get_embedding(query)     # 嵌入用户提问
  │         ├─ cosine_similarity × N                      # 向量相似度排序
  │         └─ 格式化 top-K 记忆注入 system prompt
  ├─ tools.get_tool_instructions()                 # 各 tool 的 fallback 说明
  ├─ client.chat_completion(stream=True, tools=...)
  │    ├─ 实时编辑 Telegram 消息（1s 间隔 + 光标）
  │    ├─ 收集 tool_calls
  │    └─ 返回 (full_response, usage, tool_calls)
  ├─ [如果有 tool_calls]:
  │    ├─ tools.process_tool_calls()               # 分发执行
  │    │    ├─ save_memory → add_memory()
  │    │    │    ├─ get_embedding(content)          # 嵌入记忆
  │    │    │    ├─ 语义去重（>0.85 → 替换旧记忆）
  │    │    │    └─ cache.add_memory()
  │    │    ├─ web_search → browserless/ollama
  │    │    ├─ url_fetch → tls_client/jina
  │    │    ├─ tts_speak → synthesize → 入队
  │    │    └─ ...
  │    ├─ messages += [assistant_msg, tool_results]
  │    └─ 再次 chat_completion（最多 3 轮）
  ├─ drain_pending_voice_jobs() → reply_voice      # TTS 语音发送
  ├─ filter_thinking_content()                     # 过滤思维链
  ├─ tools.post_process_response()                 # 后处理（regex 记忆提取等）
  ├─ cache.add_message() × 2                       # 写缓存：对话
  └─ cache.add_token_usage()                       # 写缓存：token
```

### 缓存同步

```
后台线程 (每 30s)
  → cache.get_and_clear_dirty()     # 原子取出 dirty flags
  → sync_to_database()              # 批量写入 PostgreSQL (UPSERT/INSERT/DELETE)
  → 失败 → cache.restore_dirty()   # 回滚 dirty flags，下次重试
```

---

## 15. 用户数据模型

```
user_id: 123456
├── Settings（全局）
│   ├── api_key: "sk-xxx"
│   ├── base_url: "https://api.openai.com/v1"
│   ├── model: "gpt-4o"
│   ├── temperature: 0.7
│   ├── token_limit: 0                    # 0 = 无限
│   ├── current_persona: "default"
│   ├── enabled_tools: "memory,search,fetch,wikipedia,tts"
│   ├── tts_voice / tts_style / tts_endpoint
│   └── ...
│
├── Personas
│   ├── "default"
│   │   ├── name: "default"
│   │   └── system_prompt: "You are a helpful assistant."
│   └── "code"
│       ├── name: "code"
│       └── system_prompt: "You are an expert Python developer."
│
├── Conversations（per persona）
│   ├── (123456, "default"): [
│   │   {"role": "user", "content": "Hello"},
│   │   {"role": "assistant", "content": "Hi!"}
│   │]
│   └── (123456, "code"): [...]
│
├── Token Usage（per persona）
│   ├── (123456, "default"): {prompt: 100, completion: 50, total: 150}
│   └── (123456, "code"): {prompt: 0, completion: 0, total: 0}
│
└── Memories（跨 persona 共享）
    ├── {id: 1, content: "喜欢 Python", source: "user", embedding: [...]}
    ├── {id: 2, content: "偏好简洁回复", source: "ai", embedding: [...]}
    └── {id: 3, content: "做 Web 项目", source: "user", embedding: null}
```

---

## 16. 核心算法

### 记忆语义去重

```python
# 添加记忆时：
embedding = get_embedding(content)
for existing in memories:
    if existing.embedding and cosine_similarity(embedding, existing.embedding) > 0.85:
        delete_old_memory(existing)   # 替换旧记忆
        break
save_new_memory(content, embedding)
```

### 记忆相关性检索

```python
# 构建 system prompt 时：
query_embedding = get_embedding(user_message)
scored = [(cosine_similarity(query_embedding, m.embedding), m) for m in memories if m.embedding]
scored.sort(reverse=True)
relevant = [m for score, m in scored[:TOP_K] if score >= SIMILARITY_THRESHOLD]
# 无嵌入的 legacy 记忆始终包含
```

### 流式 Tool Call 聚合

```python
# 流式 chunk 中跨步收集 tool_call 片段：
tool_call_chunks: dict[int, dict] = {}  # index → {id, name, arguments}
for chunk in stream:
    for delta in chunk.tool_calls:
        idx = delta.index
        tool_call_chunks.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if delta.id: tool_call_chunks[idx]["id"] = delta.id
        if delta.function.name: tool_call_chunks[idx]["name"] = delta.function.name
        if delta.function.arguments: tool_call_chunks[idx]["arguments"] += delta.function.arguments
    if finished:
        # 编译为 ToolCall 列表
```

### Dirty 跟踪与异步同步

```python
# 缓存写入时：
cache.update_settings(user_id, "model", "gpt-4-turbo")
# → _dirty_settings.add(user_id)  # Lock 保护

# 后台线程每 30s：
dirty = cache.get_and_clear_dirty()   # 原子取出并清空
sync_to_database(dirty)               # 写 DB
# 失败 → cache.restore_dirty(dirty)  # 重放 dirty flags
```

---

## 17. 关键设计决策

1. **内存优先架构**：所有数据读写走内存缓存，后台 30s 定时同步到 PostgreSQL。响应快，代价是最多丢失 30s 数据。

2. **Persona 隔离**：每个 persona 有独立的 system_prompt、对话历史、token 统计。切换 persona 不影响其他 persona 的数据。

3. **记忆跨 persona 共享**：记忆存储在用户级别，所有 persona 共享同一套记忆。

4. **Token 限额全局生效**：`token_limit` 是用户级别设置，所有 persona 的 token 总和受此限制。

5. **双重记忆提取**：优先使用 tool calling（`save_memory`），fallback 用 regex 从 AI 回复文本中提取 `[MEMORY: ...]` 等标签。

6. **向量嵌入降级**：未配置 `NVIDIA_API_KEY` 时安全降级为返回全部记忆、不嵌入。嵌入以 JSON 文本存于 PostgreSQL `TEXT` 列，无需 pgvector。

7. **可扩展 Tool 框架**：所有 tool 通过 registry 统一注册与分发。添加新 tool 只需新建文件 + 注册一行，handler 零修改。

8. **流式响应**：实时推送 AI 回复到 Telegram，`▌` 光标，1s 节流间隔。思考阶段显示 "Thinking..."。

9. **HTML 降级**：Telegram 消息先用 HTML 格式，解析失败降级为纯文本。

10. **思维链过滤**：自动过滤 `<think>` / `<thinking>` / `<reasoning>` 标签。流式阶段返回空以触发指示器；最终阶段兜底保留内容避免空回复。支持 DeepSeek R1 的独立 `reasoning_content` 字段。

11. **群聊选择性响应**：仅在被回复或 @mention 时响应，避免打扰。

12. **并发更新**：`Application.builder().concurrent_updates(True)` 允许同时处理多个 Telegram 更新。

13. **TTS 侧信道发送**：TTS 工具生成的音频不直接发送，而是放入 per-user 待发送队列，由主消息处理流程在文本回复后统一出队发送。

---

## 18. 部署 (Hugging Face Spaces)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py config/ database/ cache/ services/ ai/ handlers/ tools/ utils/ ./
EXPOSE 7860
CMD ["python", "bot.py"]
```

- 健康检查：`GET/HEAD` → `200 OK`（端口由 `PORT` 环境变量控制）
- HF Spaces 通过 HTTP 探测服务存活
- 必需 Secrets：`TELEGRAM_BOT_TOKEN`、`DATABASE_URL`
- 可选 Secrets：`OPENAI_API_KEY`、`NVIDIA_API_KEY`、`BROWSERLESS_API_TOKEN`、`JINA_API_KEY`、`OLLAMA_API_KEY` 等
- 用户也可通过 `/set` 命令自行配置 API Key 和模型
