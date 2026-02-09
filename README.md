---
title: Gemen
emoji: 💻
colorFrom: red
colorTo: indigo
sdk: docker
pinned: false
---

# Telegram AI Bot

一个支持 OpenAI API 的 Telegram 聊天机器人，支持流式输出、上下文对话、图片/文件分析、自定义配置。

## 功能特点

- **流式输出**：实时显示 AI 回复，带打字光标效果
- **上下文对话**：保持对话历史，支持多轮对话
- **智能记忆**：用户可手动添加记忆，AI 也能自动学习记忆
- **图片分析**：发送图片使用视觉模型分析
- **文件处理**：支持代码、文本、图片文件的上传分析
- **自定义配置**：支持修改 API 地址、模型、温度等参数
- **模型浏览**：交互式模型列表，分页选择
- **Token 统计**：跟踪使用量，支持设置限额
- **聊天导出**：导出对话历史为 Markdown 文件
- **群聊支持**：通过 @提及 或回复触发响应
- **过滤 thinking**：自动过滤模型的思考过程内容
- **长消息分段**：超过 4096 字符自动分多条发送
- **Markdown 支持**：默认 Markdown 格式，失败自动降级为纯文本
- **多用户隔离**：每个用户独立的设置和对话历史
- **数据持久化**：PostgreSQL 存储，内存缓存加速

## 命令列表

| 命令 | 说明 |
|------|------|
| `/start` | 开始使用，显示帮助信息 |
| `/help` | 显示帮助信息 |
| `/clear` | 清除对话历史 |
| `/settings` | 查看当前配置 |
| `/set <key> <value>` | 修改配置 |
| `/set model` | 浏览可用模型列表 |
| `/remember <text>` | 添加一条记忆 |
| `/memories` | 查看所有记忆 |
| `/forget <num\|all>` | 删除记忆 |
| `/usage` | 查看 Token 使用统计 |
| `/usage reset` | 重置 Token 统计 |
| `/export` | 导出聊天记录 |

## 记忆系统

记忆功能让 AI 能够记住关于你的重要信息，实现跨会话的个性化体验。

### 手动添加记忆
```
/remember 我喜欢简洁的回答
/remember 我是一名 Python 开发者
/remember 我的项目使用 FastAPI 框架
```

### 查看和管理记忆
```
/memories          # 列出所有记忆
/forget 1          # 删除第 1 条记忆
/forget all        # 清空所有记忆
```

### AI 自动记忆
AI 在对话过程中会自动识别重要信息并保存为记忆，例如：
- 你的偏好设置（语言、风格）
- 你的技术栈和项目背景
- 重要的上下文信息

记忆列表中会标记来源：👤 用户添加，🤖 AI 自动添加

## 配置项

通过 `/set` 命令可以修改以下配置：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `base_url` | API 地址 | `/set base_url https://api.openai.com/v1` |
| `api_key` | API 密钥 | `/set api_key sk-xxx` |
| `model` | 模型名称（或不带值浏览列表） | `/set model gpt-4o` |
| `prompt` | 系统提示词 | `/set prompt 你是一个有帮助的助手` |
| `temperature` | 温度 (0-2) | `/set temperature 0.7` |
| `token_limit` | Token 用量限额 | `/set token_limit 100000` |

## 项目结构

```
gemen/
├── bot.py                  # 入口文件
├── config/                 # 配置模块
│   ├── settings.py         # 环境变量、默认设置
│   └── constants.py        # 常量定义
├── database/               # 数据库层
│   ├── connection.py       # 连接管理
│   └── schema.py           # 表结构定义
├── cache/                  # 缓存层
│   ├── manager.py          # 内存缓存管理
│   └── sync.py             # 后台同步逻辑
├── services/               # 业务逻辑层
│   ├── user_service.py     # 用户设置管理
│   ├── conversation_service.py  # 对话管理
│   ├── token_service.py    # Token 使用跟踪
│   ├── memory_service.py   # 记忆系统
│   └── export_service.py   # 聊天导出
├── ai/                     # AI 客户端抽象层
│   ├── base.py             # 抽象基类
│   ├── openai_client.py    # OpenAI 实现
│   └── gemini_client.py    # Gemini 预留
├── handlers/               # Telegram 处理器
│   ├── commands/           # 命令处理
│   │   ├── basic.py        # /start, /help, /clear
│   │   ├── settings.py     # /settings, /set
│   │   ├── usage.py        # /usage, /export
│   │   └── memory.py       # /remember, /memories, /forget
│   ├── messages/           # 消息处理
│   │   ├── text.py         # 文本消息
│   │   ├── photo.py        # 图片处理
│   │   └── document.py     # 文件处理
│   └── callbacks.py        # 回调处理
└── utils/                  # 工具函数
    ├── telegram.py         # Telegram 工具
    ├── filters.py          # 内容过滤
    └── files.py            # 文件类型检测
```

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | 是 | Telegram Bot Token |
| `DATABASE_URL` | 是 | PostgreSQL 连接字符串 |
| `OPENAI_API_KEY` | 否 | 默认 API 密钥 |
| `OPENAI_BASE_URL` | 否 | 默认 API 地址 |
| `OPENAI_MODEL` | 否 | 默认模型 |
| `OPENAI_TEMPERATURE` | 否 | 默认温度 |
| `OPENAI_SYSTEM_PROMPT` | 否 | 默认系统提示词 |
| `TELEGRAM_API_BASE` | 否 | 自定义 Telegram API 地址 |
| `PORT` | 否 | 健康检查端口 (默认 8080) |

## 部署

### Docker

```bash
docker build -t gemen .
docker run -d \
  -e TELEGRAM_BOT_TOKEN=your_token \
  -e DATABASE_URL=postgresql://... \
  -e OPENAI_API_KEY=sk-xxx \
  gemen
```

### HuggingFace Spaces

1. 创建 Docker 类型的 Space
2. 在 Settings > Variables 中添加环境变量
3. 推送代码到 Space 仓库
