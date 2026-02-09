# Gemen - Telegram AI Bot 项目文档

## 1. 项目概述

Gemen 是一个基于 `python-telegram-bot` 的 Telegram AI 聊天机器人。它通过 OpenAI 兼容 API 与大语言模型交互，支持多 Persona（角色）、记忆系统、流式响应、图片/文件处理、Token 追踪等功能。部署目标为 Hugging Face Spaces。

**技术栈：**
- Python + `python-telegram-bot` (Telegram Bot API)
- `openai` SDK (OpenAI 兼容 API 客户端)
- `psycopg2` (PostgreSQL 数据库)
- `python-dotenv` (环境变量)
- 标准库 `http.server` (健康检查 HTTP 服务)

**不是** Flask/FastAPI/Django 等 Web 框架项目，唯一的 HTTP 端点是健康检查服务器。

---

## 2. 目录结构

```
gemen/
├── bot.py                          # 入口文件：启动 bot + 健康检查 HTTP 服务
├── config/
│   ├── __init__.py                 # 导出所有配置
│   ├── settings.py                 # 环境变量、默认设置、默认 Persona/Token 结构
│   └── constants.py                # 常量：消息长度限制、流式间隔、文件类型等
├── handlers/
│   ├── __init__.py                 # 导出所有 handler
│   ├── common.py                   # 群聊响应判断 should_respond_in_group()
│   ├── callbacks.py                # InlineKeyboard 回调：model 选择/翻页
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── basic.py                # /start, /help, /clear
│   │   ├── settings.py             # /settings, /set + model 列表分页
│   │   ├── persona.py              # /persona (list/new/delete/prompt/switch)
│   │   ├── memory.py               # /remember, /memories, /forget
│   │   └── usage.py                # /usage, /export
│   └── messages/
│       ├── __init__.py
│       ├── text.py                 # 文本消息 → 流式 AI 回复 + tool calling
│       ├── photo.py                # 图片消息 → vision 模型处理
│       └── document.py             # 文件上传 → 文本/图片分流处理
├── tools/
│   ├── __init__.py                 # 注册所有 tool，导出公开 API
│   ├── registry.py                 # BaseTool 抽象基类 + ToolRegistry 注册中心
│   ├── memory.py                   # MemoryTool：记忆保存（定义、执行、指令、prompt 注入、regex fallback）
│   ├── search.py                   # SearchTool：DuckDuckGo 网页搜索
│   └── fetch.py                    # FetchTool：URL 内容抓取（TLS 指纹模拟）
├── services/
│   ├── __init__.py                 # 统一导出所有 service 函数
│   ├── user_service.py             # 用户设置 CRUD (薄封装 cache)
│   ├── persona_service.py          # Persona CRUD + 切换
│   ├── conversation_service.py     # 对话历史 CRUD
│   ├── token_service.py            # Token 用量追踪、限额
│   ├── memory_service.py           # 记忆系统：CRUD + 向量嵌入 + 语义去重 + prompt 格式化
│   ├── embedding_service.py        # 向量嵌入服务：NVIDIA API (bge-m3) + 余弦相似度
│   └── export_service.py           # 导出对话为 Markdown 文件
├── ai/
│   ├── __init__.py                 # 工厂函数 get_ai_client() / get_openai_client()
│   ├── base.py                     # 抽象基类 AIClient + 数据类 StreamChunk/ToolCall
│   ├── openai_client.py            # OpenAI 兼容客户端（流式/非流式/tool calling）
│   └── gemini_client.py            # Gemini 客户端（占位，未实现）
├── database/
│   ├── __init__.py                 # 导出 get_connection / get_dict_cursor
│   ├── connection.py               # psycopg2 连接 PostgreSQL
│   └── schema.py                   # 建表 SQL + 迁移 SQL + create_tables()
├── cache/
│   ├── __init__.py                 # 导出 cache 实例 / init_database()
│   ├── manager.py                  # CacheManager：内存缓存 + dirty 跟踪
│   └── sync.py                     # 数据库同步：加载、定时写回、init_database()
├── utils/
│   ├── __init__.py                 # 导出所有工具函数
│   ├── filters.py                  # filter_thinking_content() 过滤思维链标签
│   ├── telegram.py                 # send_message_safe() / edit_message_safe()
│   ├── formatters.py               # Markdown → Telegram HTML 转换 + 消息分片
│   └── files.py                    # 文件类型检测 + 解码
└── docs/                           # 文档目录
```

---

## 3. 启动流程 (bot.py)

```
main()
  ├── 校验 TELEGRAM_BOT_TOKEN
  ├── init_database()                    # cache/sync.py
  │     ├── create_tables(conn)          # 建表 + 迁移
  │     ├── load_from_database()         # 加载全部数据到内存缓存
  │     └── 启动后台同步线程 _sync_loop   # 每 30s 写回 dirty 数据
  ├── 启动健康检查 HTTP 服务 (daemon thread)
  │     └── HTTPServer(0.0.0.0:PORT)     # GET/HEAD → 200 OK
  ├── 构建 Application (python-telegram-bot)
  │     └── 可选自定义 Telegram API base URL
  ├── 注册所有 Handler
  │     ├── CommandHandler × 11
  │     ├── CallbackQueryHandler × 1 (model 选择)
  │     └── MessageHandler × 3 (text/photo/document)
  └── application.run_polling()          # 长轮询接收 Telegram 更新
```

---

## 4. 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `TELEGRAM_BOT_TOKEN` | 是 | - | Telegram Bot API Token |
| `DATABASE_URL` | 是 | - | PostgreSQL 连接字符串 |
| `PORT` | 否 | `8080` | 健康检查 HTTP 端口 |
| `TELEGRAM_API_BASE` | 否 | 空 (用 Telegram 官方) | 自定义 Telegram API 地址 |
| `OPENAI_API_KEY` | 否 | 空 | 全局默认 API Key |
| `OPENAI_BASE_URL` | 否 | `https://api.openai.com/v1` | 全局默认 API Base URL |
| `OPENAI_MODEL` | 否 | `gpt-4o` | 全局默认模型 |
| `OPENAI_TEMPERATURE` | 否 | `0.7` | 全局默认 Temperature |
| `OPENAI_SYSTEM_PROMPT` | 否 | `You are a helpful assistant.` | 默认系统提示词 |
| `NVIDIA_API_KEY` | 否 | 空 | NVIDIA Embedding API Key（启用记忆向量检索） |
| `EMBEDDING_BASE_URL` | 否 | `https://integrate.api.nvidia.com/v1` | Embedding API 地址（OpenAI 兼容格式） |
| `EMBEDDING_MODEL` | 否 | `baai/bge-m3` | Embedding 模型名 |
| `MEMORY_TOP_K` | 否 | `10` | 向量检索返回的最大记忆条数 |
| `MEMORY_SIMILARITY_THRESHOLD` | 否 | `0.35` | 向量检索最低相似度阈值 |
| `MEMORY_DEDUP_THRESHOLD` | 否 | `0.85` | 记忆去重相似度阈值（超过则视为重复并替换） |

---

## 5. 应用常量 (config/constants.py)

| 常量 | 值 | 说明 |
|------|----|------|
| `MAX_MESSAGE_LENGTH` | 4096 | Telegram 单条消息字符上限 |
| `STREAM_UPDATE_INTERVAL` | 1.0s | 流式输出刷新间隔 |
| `DB_SYNC_INTERVAL` | 30s | 后台数据库同步间隔 |
| `MODELS_PER_PAGE` | 5 | model 列表每页显示数 |
| `MAX_FILE_SIZE` | 20MB | 文件上传大小限制 |
| `MAX_TEXT_CONTENT_LENGTH` | 100000 | 文本文件最大处理字符数 |
| `TEXT_EXTENSIONS` | 大量代码/文本扩展名 | 可识别的文本文件类型 |
| `IMAGE_EXTENSIONS` | jpg/png/gif/webp/bmp | 可识别的图片文件类型 |

---

## 6. 数据库设计

使用 PostgreSQL，5 张表：

### user_settings
用户全局设置（每用户一行）。
```sql
user_id       BIGINT PRIMARY KEY
api_key       TEXT
base_url      TEXT
model         TEXT
temperature   REAL
token_limit   BIGINT DEFAULT 0
current_persona TEXT DEFAULT 'default'
```

### user_personas
角色定义（每用户可有多个角色）。
```sql
id            SERIAL PRIMARY KEY
user_id       BIGINT NOT NULL
name          TEXT NOT NULL
system_prompt TEXT NOT NULL
created_at    TIMESTAMP
UNIQUE(user_id, name)
```
索引: `idx_personas_user_id ON user_personas(user_id)`

### user_conversations
对话历史，按 persona 隔离。
```sql
id            SERIAL PRIMARY KEY
user_id       BIGINT NOT NULL
persona_name  TEXT NOT NULL DEFAULT 'default'
role          TEXT NOT NULL          -- 'user' | 'assistant'
content       TEXT NOT NULL
created_at    TIMESTAMP
```
索引: `idx_conversations_user_persona ON user_conversations(user_id, persona_name)`

### user_persona_tokens
每个 persona 的 token 用量。
```sql
user_id           BIGINT NOT NULL
persona_name      TEXT NOT NULL
prompt_tokens     BIGINT DEFAULT 0
completion_tokens BIGINT DEFAULT 0
total_tokens      BIGINT DEFAULT 0
PRIMARY KEY (user_id, persona_name)
```

### user_token_usage (旧表，仅供迁移)
```sql
user_id           BIGINT PRIMARY KEY
prompt_tokens     BIGINT DEFAULT 0
completion_tokens BIGINT DEFAULT 0
total_tokens      BIGINT DEFAULT 0
token_limit       BIGINT DEFAULT 0
```

### user_memories
用户记忆（跨 persona 共享），支持向量嵌入。
```sql
id            SERIAL PRIMARY KEY
user_id       BIGINT NOT NULL
content       TEXT NOT NULL
source        TEXT NOT NULL DEFAULT 'user'   -- 'user' | 'ai'
embedding     TEXT                           -- 向量嵌入 JSON（如 '[0.1, 0.2, ...]'）
created_at    TIMESTAMP
```
索引: `idx_memories_user_id ON user_memories(user_id)`

---

## 7. 缓存架构 (cache/)

### CacheManager (cache/manager.py)

**核心设计：内存缓存 + dirty flag + 定时批量同步。**

所有读写操作都走内存缓存，不直接访问数据库。通过 dirty flag 跟踪变更，由后台线程定时写回。

**缓存结构：**
```python
_settings_cache:       dict[user_id, settings_dict]
_personas_cache:       dict[user_id, dict[persona_name, persona_dict]]
_conversations_cache:  dict[(user_id, persona_name), list[message]]
_persona_tokens_cache: dict[(user_id, persona_name), usage_dict]
_memories_cache:       dict[user_id, list[memory_dict]]
```

**Dirty 跟踪：**
```python
_dirty_settings:          set[user_id]
_dirty_personas:          set[(user_id, persona_name)]
_deleted_personas:        set[(user_id, persona_name)]
_dirty_conversations:     set[(user_id, persona_name)]
_cleared_conversations:   set[(user_id, persona_name)]
_dirty_tokens:            set[(user_id, persona_name)]
_new_memories:            list[memory_dict]
_deleted_memory_ids:      list[int]
_cleared_memories:        set[user_id]
```

所有 dirty 操作使用 `threading.Lock` 保护。

### 同步逻辑 (cache/sync.py)

- `init_database()`: 建表 → 从 DB 加载到缓存 → 启动后台同步线程
- `load_from_database()`: 加载 settings/personas/conversations/tokens/memories，含旧表迁移
- `sync_to_database()`: 原子取出 dirty flags → 逐项写回 → 失败时 restore_dirty
- `_sync_loop()`: 每 `DB_SYNC_INTERVAL`(30s) 调用一次 sync_to_database

---

## 8. AI 客户端 (ai/)

### 抽象基类 AIClient (ai/base.py)

```python
class AIClient(ABC):
    def chat_completion(messages, model, temperature, stream, tools) -> Iterator[StreamChunk]
    def list_models() -> list[str]

@dataclass
class StreamChunk:
    content: str | None
    usage: dict | None
    finished: bool
    tool_calls: list[ToolCall]

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string
```

### OpenAIClient (ai/openai_client.py)

使用 `openai` SDK，支持：
- 流式和非流式响应
- Tool calling（工具调用）
  - 流式模式下跨 chunk 聚合 tool_call_chunks
  - 如果 tools 不被支持，自动重试（去掉 tools 参数）
- `list_models()` 获取可用模型列表

### GeminiClient (ai/gemini_client.py)

占位实现，所有方法抛出 `NotImplementedError`。

### 工厂函数 (ai/__init__.py)

- `get_ai_client(user_id)`: 根据用户设置创建 AI 客户端（当前只返回 OpenAIClient）
- `get_openai_client(user_id)`: 直接创建 OpenAIClient

---

## 9. Handler 详解

### 9.1 命令 Handler

| 命令 | 文件 | 函数 | 功能 |
|------|------|------|------|
| `/start` | `commands/basic.py` | `start()` | 根据用户状态显示不同欢迎语（新用户引导设置 key，老用户简短问候） |
| `/help` | `commands/basic.py` | `help_command()` | 简短概要 + InlineKeyboard 分类按钮（Personas/Settings/Memory/Advanced） |
| `/clear` | `commands/basic.py` | `clear()` | 清除当前 persona 对话 + 重置 token |
| `/retry` | `commands/basic.py` | `retry_command()` | 重试上一条消息（移除上一轮 assistant 回复后重新调用 chat） |
| `/persona` | `commands/persona.py` | `persona_command()` | 子命令路由（见下） |
| `/settings` | `commands/settings.py` | `settings_command()` | 显示当前配置（API key 脱敏） |
| `/set` | `commands/settings.py` | `set_command()` | 修改配置项（api_key 设置后自动验证） |
| `/remember` | `commands/memory.py` | `remember_command()` | 手动添加记忆 |
| `/memories` | `commands/memory.py` | `memories_command()` | 列出所有记忆 |
| `/forget` | `commands/memory.py` | `forget_command()` | 删除记忆（按编号或全部） |
| `/usage` | `commands/usage.py` | `usage_command()` | 显示 token 用量（当前 persona + 全局） |
| `/export` | `commands/usage.py` | `export_command()` | 导出当前 persona 对话为 Markdown 文件 |

### /persona 子命令

```
/persona              → 列出所有 persona（标记当前项，显示消息数/token 数）
/persona <name>       → 切换到指定 persona（不存在时提示创建）
/persona new <name> [prompt] → 创建新 persona 并切换
/persona delete <name>       → 删除 persona（不能删 default）
/persona prompt <text>       → 设置当前 persona 的 system prompt
/persona prompt              → 查看当前 persona 的 prompt
```

### /set 可配置项

```
/set base_url <url>          → OpenAI 兼容 API 地址
/set api_key <key>           → API Key（设置后自动调用 list_models 验证）
/set model                   → 浏览模型列表（InlineKeyboard 分页）
/set model <name>            → 直接设置模型名
/set temperature <0.0-2.0>   → 温度
/set token_limit <number>    → 全局 token 限额（0 = 无限）
```

### 9.2 消息 Handler

#### 文本消息 (messages/text.py → chat())

完整流程：
1. 群聊检查 `should_respond_in_group()`
2. 去掉 `@bot` mention
3. 检查是否已设置 API key
4. 检查 token 限额（`get_remaining_tokens()`，不足时拒绝）
5. 发送 `ChatAction.TYPING` 指示器
6. 发送占位消息 `…`（单字符省略号）
7. 构建 system prompt = persona prompt + tools 注入（记忆等） + tool 指令
8. 构建 messages = [system] + conversation_history + [user_message]
9. 获取 tool 定义（通过 `tools.get_all_tools()`）
10. 调用 AI API（流式 + tools）
11. 流式阶段：首个可见 chunk 立即更新（跳过节流间隔）；检测思考状态显示 "Thinking..."；后续按 STREAM_UPDATE_INTERVAL 节流更新（带 `▌` 光标）
12. Tool call 阶段：显示工具执行状态（🔍 Searching... / 🌐 Fetching... 等），30s 超时保护
13. 过滤 thinking 标签（`filter_thinking_content(streaming=False)`）
14. 后处理响应（通过 `tools.post_process_response()`，如 regex fallback 记忆提取）
15. 超长消息：删除占位 → 分片发送；正常：编辑占位消息
16. 保存对话到缓存 + 保存 `last_message` 到 `context.user_data`（供 /retry 使用）
17. 记录 token 用量

#### 图片消息 (messages/photo.py → handle_photo())

1. 下载图片 → base64 编码
2. 构建 vision 消息（caption 可选）
3. 流式调用 AI → 更新消息
4. 保存对话 (`[Image]` + caption)

#### 文件上传 (messages/document.py → handle_document())

1. 检查文件大小 (≤ 20MB)
2. 判断文件类型：
   - 图片文件 → `_process_image_file()`（同 photo 处理，支持 MIME 类型映射）
   - 文本/代码文件（按扩展名或内容探测） → `_process_text_file()`
   - 其他 → 返回不支持提示
3. 文本处理：解码 → 截断(10万字符) → 构建 `[File: name]\n```content```\ncaption`
4. 流式 AI 回复 → 保存对话

### 9.3 Callback Handler (callbacks.py)

处理 InlineKeyboard 回调：

**model_callback():**
- `model:<name>` → 设置模型
- `models_page:<n>` → model 列表翻页
- `models_noop` → 忽略（页码按钮）

**help_callback():**
- `help:personas` → 显示 Persona 命令帮助
- `help:settings` → 显示 Settings 命令帮助
- `help:memory` → 显示 Memory 命令帮助
- `help:advanced` → 显示高级功能帮助

### 9.4 群聊判断 (common.py → should_respond_in_group())

私聊：始终响应。群聊仅在以下情况响应：
- 回复 bot 的消息
- `@bot` mention（消息文本 / caption / entities）

---

## 10. Service 层

Service 层是 handler 和 cache 之间的薄封装层，所有 service 函数直接操作 `cache` 单例。

### user_service.py
`get_user_settings`, `update_user_setting`, `get_api_key`, `get_base_url`, `get_model`, `get_temperature`, `has_api_key`

### persona_service.py
`get_personas`, `get_persona`, `get_current_persona`, `get_current_persona_name`, `get_system_prompt`, `switch_persona`（不存在自动创建）, `create_persona`, `delete_persona`, `update_persona_prompt`, `update_current_prompt`, `persona_exists`, `get_persona_count`

### conversation_service.py
`get_conversation`, `add_message`, `add_user_message`, `add_assistant_message`, `clear_conversation`, `get_message_count`

### token_service.py
`get_token_usage`, `add_token_usage`, `get_token_limit`, `set_token_limit`, `reset_token_usage`, `get_total_tokens_all_personas`, `get_remaining_tokens`, `get_usage_percentage`

### memory_service.py
CRUD + prompt 格式化 + 向量嵌入集成：
- `get_memories`, `add_memory`（自动嵌入 + 语义去重）, `delete_memory`(1-based index), `clear_memories`, `get_memory_count`
- `format_memories_for_prompt(user_id, query=None)` → 当提供 query 且 embedding 可用时，执行向量相似度检索（top-K + 阈值过滤）；否则返回全部记忆

> Tool 相关逻辑（定义、执行、指令、regex 提取）已迁移至 `tools/memory.py`。

### embedding_service.py
向量嵌入服务，通过 OpenAI 兼容 API（NVIDIA / bge-m3）生成文本向量：
- `get_embedding(text)` → 单条文本嵌入
- `get_embeddings_batch(texts)` → 批量嵌入
- `cosine_similarity(a, b)` → 余弦相似度计算
- `is_available()` → 检查是否配置了 `NVIDIA_API_KEY`
- 未配置 API Key 时所有函数安全降级（返回 None），不影响原有功能

### export_service.py
`export_to_markdown()` → 将对话导出为 Markdown 格式的 BytesIO 文件

---

## 11. Tool 系统 (tools/)

可扩展的 tool 框架。handler 层只与 registry 交互，添加新 tool 无需修改 handler。

### 架构

```
tools/
├── __init__.py      # 注册 tool 实例，导出公开 API
├── registry.py      # BaseTool 基类 + ToolRegistry
├── memory.py        # MemoryTool：记忆保存
├── search.py        # SearchTool：DuckDuckGo 网页搜索
└── fetch.py         # FetchTool：URL 内容抓取（TLS 指纹模拟）
```

### BaseTool 抽象基类 (registry.py)

每个 tool 继承 `BaseTool`，实现以下方法：

| 方法 | 必须实现 | 说明 |
|------|---------|------|
| `definitions()` | 是 | 返回 OpenAI function-calling 格式的 tool 定义列表 |
| `execute(user_id, tool_name, arguments)` | 是 | 执行 tool call，返回结果文本 |
| `get_instruction()` | 否 | 追加到 system prompt 的使用说明（默认空） |
| `enrich_system_prompt(user_id, prompt)` | 否 | 往 system prompt 注入上下文（默认不修改） |
| `post_process(user_id, text)` | 否 | 对 AI 回复做后处理（默认不修改） |

### ToolRegistry (registry.py)

单例 `registry`，提供：
- `register(tool)` → 注册 tool 实例
- `get_definitions()` → 合并所有 tool 的定义
- `process_tool_calls(user_id, tool_calls)` → 根据 tool_call.name 分发到对应 tool
- `get_instructions()` → 合并所有 tool 的指令
- `enrich_system_prompt(user_id, prompt, **kwargs)` → 依次调用所有 tool 的 prompt 注入（支持传递 `query` 等上下文）
- `post_process(user_id, text)` → 依次调用所有 tool 的后处理

### MemoryTool (memory.py)

从 `memory_service` 迁移的记忆 tool，集成向量检索：
- `definitions()` → `save_memory` tool JSON schema
- `execute()` → 解析 tool call 参数，调用 `memory_service.add_memory()`（自动嵌入 + 去重）
- `get_instruction()` → 记忆使用提示（含 `[MEMORY: ...]` fallback 格式说明）
- `enrich_system_prompt(query=...)` → 调用 `format_memories_for_prompt(query)` 注入相关记忆（向量检索或全部）
- `post_process()` → regex fallback 提取 `[MEMORY: ...]`、`[记忆: ...]`、`<memory>...</memory>`

### 公开 API (\_\_init\_\_.py)

```python
from tools import (
    get_all_tools,          # registry.get_definitions
    process_tool_calls,     # registry.process_tool_calls
    get_tool_instructions,  # registry.get_instructions
    enrich_system_prompt,   # registry.enrich_system_prompt
    post_process_response,  # registry.post_process
)
```

### 扩展新 tool

添加新 tool 只需两步，handler 层零修改：

```python
# 1. tools/search.py — 新建文件，继承 BaseTool
class SearchTool(BaseTool):
    def definitions(self): ...
    def execute(self, user_id, tool_name, arguments): ...

# 2. tools/__init__.py — 加一行注册
from .search import SearchTool
registry.register(SearchTool())
```

---

## 12. 工具函数 (utils/)

### filters.py → filter_thinking_content(text, streaming=False)
过滤 AI 回复中的思维链内容，支持：
- `<think>...</think>`、`<thinking>...</thinking>`、`<reasoning>...</reasoning>`、`[thinking]...[/thinking]`
- 处理流式中未闭合的标签（从开标签到文本末尾）
- `streaming=True`（流式阶段）：过滤后为空时直接返回空，让调用方显示 "Thinking..." 指示器
- `streaming=False`（最终响应，默认）：过滤后为空时兜底只移除标签保留内容，避免最终回复为空

### telegram.py
- `send_message_safe(message, text)`: 发送消息，先尝试 HTML 格式，失败降级纯文本。超长自动分片。
- `edit_message_safe(message, text)`: 编辑消息，HTML → 纯文本降级，处理 RetryAfter 和 "not modified" 异常。

### formatters.py
- `markdown_to_telegram_html(text)`: Markdown → Telegram HTML 转换
  - 先提取代码块/行内代码保护
  - 转换: `#` → `<b>`, `---` → `──────────`, `-/*` → `•`, `**` → `<b>`, `*` → `<i>`, `` ` `` → `<code>`, `~~~` → `<s>`, `[text](url)` → `<a>`
  - HTML 转义非代码文本
- `split_message(text, max_length)`: 按段落 → 行 → 强制拆分

### files.py
- `get_file_extension(file_name)`: 提取扩展名（小写，带点）
- `is_text_file(file_name)`: 按扩展名判断是否文本
- `is_image_file(file_name)`: 按扩展名判断是否图片
- `is_likely_text(data)`: 按内容探测（UTF-8 解码 + 可打印字符比例 > 90%）
- `decode_file_content(file_bytes)`: 尝试 UTF-8 → Latin-1 解码

---

## 13. 健康检查 HTTP 服务 (bot.py)

部署在 Hugging Face Spaces 时用于存活探测。

```python
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):   # GET → 200 OK, body "OK"
    def do_HEAD(self):  # HEAD → 200 OK, no body
    def log_message():  # 抑制日志
```

- 监听: `0.0.0.0:{PORT}`（默认 8080）
- 在 daemon 线程中运行，不阻塞 bot 主线程

---

## 14. 数据流图

### 用户发消息

```
Telegram → run_polling() → MessageHandler
  → chat() / handle_photo() / handle_document()
    → cache.get_*()                         # 读缓存：设置、对话、记忆
    → tools.enrich_system_prompt(query=msg)  # tool 注入 system prompt
    │   └── MemoryTool.enrich_system_prompt
    │         ├── embedding_service.get_embedding(query)   # 嵌入用户提问
    │         ├── cosine_similarity 检索相关记忆 (top-K)    # 向量相似度排序
    │         └── 注入相关记忆到 system prompt
    → client.chat_completion()               # 流式 API 调用
    → 实时编辑 Telegram 消息                  # 1s 间隔节流
    → tools.process_tool_calls               # 分发 AI tool call
    │   └── save_memory → add_memory()
    │         ├── embedding_service.get_embedding(content)  # 嵌入记忆内容
    │         ├── 语义去重（similarity > 0.85 → 替换旧记忆）
    │         └── cache.add_memory(embedding=vec)
    → tools.post_process_response            # 后处理（regex fallback 等）
    → cache.add_message()                    # 写缓存：对话
    → cache.add_token_usage()                # 写缓存：token
```

### 缓存同步

```
后台线程 (每 30s)
  → cache.get_and_clear_dirty()  # 原子取出 dirty flags
  → sync_to_database()           # 批量写入 PostgreSQL
  → 失败 → cache.restore_dirty() # 回滚 dirty flags
```

---

## 15. 关键设计决策

1. **内存优先架构**：所有数据优先读写内存缓存，后台定时同步到 DB。优点是响应快，缺点是最多可能丢失 30s 数据。

2. **Persona 隔离**：每个 persona 有独立的 system_prompt、对话历史、token 统计。切换 persona 时不影响其他 persona 的数据。

3. **记忆跨 persona 共享**：记忆存储在用户级别，所有 persona 共享同一套记忆。

4. **Token 限额全局生效**：token_limit 是用户级别的，所有 persona 的 token 总和受此限制。

5. **双重记忆提取**：优先使用 tool calling（`save_memory`），fallback 用 regex 从文本中提取记忆标签。两者均由 `MemoryTool` 统一管理。

6. **记忆向量嵌入**：通过 NVIDIA API（OpenAI 兼容格式，模型 `baai/bge-m3`）对记忆内容和用户提问生成向量嵌入。存储时自动嵌入并语义去重（相似度 > 0.85 视为重复，替换旧记忆）；检索时以用户消息为 query 做余弦相似度排序，返回 top-K 相关记忆注入 prompt。未配置 `NVIDIA_API_KEY` 时安全降级为原有行为（返回全部记忆，不嵌入）。嵌入向量以 JSON 文本存储在 PostgreSQL，无需 pgvector 扩展。

6. **可扩展 Tool 框架**：所有 tool 通过 `tools/registry.py` 统一注册和分发，handler 层只与 registry 交互。添加新 tool 只需新建 .py 文件 + 注册一行，handler 零修改。

6. **流式响应**：AI 回复实时推送到 Telegram，用 `▌` 模拟光标，每 1s 更新一次避免 rate limit。思考阶段显示 "Thinking..." 指示器。

7. **HTML 降级**：Telegram 消息先用 HTML 格式发送，HTML 解析失败则降级为纯文本。

8. **思维链过滤**：自动过滤 `<think>`/`<thinking>`/`<reasoning>` 等标签内容，支持流式中的未闭合标签。流式阶段使用 `streaming=True` 模式，确保思考中返回空以触发 "Thinking..." 指示器；最终响应使用默认模式，兜底保留内容避免空回复。同时支持 DeepSeek R1 等模型的独立 `reasoning_content` 字段。

9. **群聊选择性响应**：群聊中仅在被回复或 @mention 时响应，避免打扰。

---

## 16. 部署 (Hugging Face Spaces)

- 健康检查端口通过 `PORT` 环境变量配置
- HF Spaces 会通过 HEAD/GET 请求探测服务是否存活
- 需要配置的 Secrets: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`
- 可选 Secrets: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` 等（用户也可通过 `/set` 自行配置）
- 可选 Secrets: `NVIDIA_API_KEY`（启用记忆向量检索），`EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`
