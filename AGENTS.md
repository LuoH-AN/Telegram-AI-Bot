# AGENTS.md

This file provides guidance to AI coding agents (Codex CLI, Claude Code, etc.) when working with code in this repository.

## Project Overview

Gemen is a multi-platform AI chatbot (Telegram / Discord / WeChat, Python 3.12) supporting multi-persona conversations, streaming responses, a small built-in tool layer, and a web dashboard. It uses OpenAI-compatible APIs with an abstraction layer for future Gemini/local LLM support.

The README and UI are in Chinese (zh-CN). Maintain this convention for user-facing strings.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the unified launcher
python main.py

# Docker build and run
docker build -t gemen .
docker run -e TELEGRAM_BOT_TOKEN=<token> -e DATABASE_URL=<url> gemen
```

There is no test suite, linter, or formatter configured yet.

## Required Environment Variables

- `TELEGRAM_BOT_TOKEN` — Telegram bot token
- `DATABASE_URL` — PostgreSQL connection string

See `.env.example` and `config/settings.py` for optional variables.

## Architecture

**Entry point:** `main.py` — unified launcher that starts the selected platform runtimes and the FastAPI web server.

### Layers

- **handlers/** — Telegram command and message handlers. `handlers/messages/text.py` contains the core chat loop.
- **ai/** — AI client abstraction. `base.py` defines the interface; `openai_client.py` implements streaming with tool call support.
- **tools/** — Minimal AI tool layer. `registry.py` handles registration and dispatch for the currently enabled tools.
- **services/** — Business logic (conversation, memory, persona, session, token tracking, user settings, embedding, TTS, logging, export).
- **cache/** — In-memory cache (`manager.py`) with dirty-flag tracking. `sync.py` runs a background thread that flushes changes to PostgreSQL every 30 seconds.
- **database/** — PostgreSQL connection management and schema definitions.
- **web/** — FastAPI dashboard with JWT auth. Routes in `web/routes/`.
- **static/** — Single-page dashboard frontend (vanilla HTML/CSS/JS).

### Key Data Flow

1. User message -> handler (text/photo/document)
2. System prompt enriched with relevant memories (semantic search via NVIDIA embeddings)
3. OpenAI-compatible streaming call with tool definitions
4. Tool calls dispatched through registry
5. Response streamed back, split at 4096 chars for Telegram limits
6. Cache marked dirty -> background sync writes to PostgreSQL

### Key Patterns

- **Multi-persona:** Each user can create personas with different system prompts, independent sessions and token counters.
- **Session management:** Each persona has multiple chat sessions with independent conversation history.
- **Memory system:** User-wide, supports semantic deduplication via cosine similarity (threshold 0.85).
- **Tool lazy retry:** If a model doesn't support tools, request is retried without tool definitions.
- **Group chat:** Bot responds only to @mentions or direct replies.
- **Streaming:** Uses generator pattern (`Iterator[StreamChunk]`). Messages are edited in-place as chunks arrive.

## Refactoring Skills

This project has Python refactoring skills installed in `.agents/skills/`. Available skills:

| Skill | Purpose |
|-------|---------|
| `py-refactor` | Orchestrate comprehensive refactoring across all tools |
| `py-security` | Detect & fix security vulnerabilities (SQL injection, hardcoded secrets, etc.) |
| `py-complexity` | Reduce cyclomatic/cognitive complexity |
| `py-code-health` | Remove dead code & duplication |
| `py-modernize` | Upgrade tooling & syntax to modern Python |
| `py-quality-setup` | Configure linters (ruff) & type checkers (mypy, basedpyright) |
| `py-git-hooks` | Set up pre-commit hooks for automated quality checks |
| `py-test-quality` | Improve test coverage & test effectiveness |

### Refactoring Priority Order

1. **Critical**: Security vulnerabilities (`py-security`)
2. **High**: Code duplication, untested code (`py-code-health`, `py-test-quality`)
3. **Medium**: Complexity reduction, dead code removal (`py-complexity`)
4. **Low**: Syntax modernization, style improvements (`py-modernize`)

### Collaboration Protocol

When working alongside other AI coding agents (Claude Code or Codex):

- **Always commit after completing a refactoring phase** so the other agent can pick up changes.
- **Use conventional commit messages**: `refactor:`, `fix:`, `chore:`, `feat:`.
- **Run `git pull` before starting work** to get the latest changes from the other agent.
- **Do not modify files the other agent is actively working on.** Check git status first.
- **Share findings via reports**: Write analysis reports to `reports/` directory (e.g., `reports/security.txt`, `reports/complexity.txt`).
- **Follow the same quality standards**: Both agents should use the same linting/type checking tools defined in pyproject.toml.

## 额外约束

- **非代码性文本只能写入文件**：凡是面向用户的非代码文本（说明、结论、清单、分析、日志解读等），必须写入工作区文件并提示用户打开查看，禁止在终端输出展示。
- **固定输出文件**：默认写入 `reports/agent_output.txt`。除非用户明确指定其他文件路径，否则所有非代码性文本都写入该文件。
