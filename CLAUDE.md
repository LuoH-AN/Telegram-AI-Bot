# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Gemen is a Telegram AI chatbot (Python 3.12) supporting multi-persona conversations, streaming responses, tool use (search, fetch, TTS, memory, Wikipedia), and a web dashboard. It uses OpenAI-compatible APIs with an abstraction layer for future Gemini/local LLM support.

The README and UI are in Chinese (zh-CN). Maintain this convention for user-facing strings.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot (starts Telegram polling + FastAPI web server)
python bot.py

# Docker build and run
docker build -t gemen .
docker run -e TELEGRAM_BOT_TOKEN=<token> -e DATABASE_URL=<url> gemen
```

There is no test suite, linter, or formatter configured.

## Required Environment Variables

- `TELEGRAM_BOT_TOKEN` — Telegram bot token
- `DATABASE_URL` — PostgreSQL connection string

See `.env.example` and `config/settings.py` for optional variables (API keys, model defaults, TTS settings, etc.).

## Architecture

**Entry point:** `bot.py` — initializes the database, starts the FastAPI web server in a daemon thread, then runs Telegram polling.

### Layers

- **handlers/** — Telegram command and message handlers. `handlers/messages/text.py` contains the core chat loop (streaming, tool dispatch, message splitting).
- **ai/** — AI client abstraction. `base.py` defines the interface; `openai_client.py` implements streaming with tool call support. `gemini_client.py` is stubbed.
- **tools/** — Plugin system via `BaseTool` abstract class. `registry.py` handles registration and dispatch. Tools define OpenAI function schemas, execute calls, and can enrich system prompts or post-process responses.
- **services/** — Business logic (conversation, memory, persona, session, token tracking, user settings, embedding, TTS, logging, export). Services operate on the cache layer.
- **cache/** — In-memory cache (`manager.py`) with dirty-flag tracking. `sync.py` runs a background thread that flushes changes to PostgreSQL every 30 seconds.
- **database/** — PostgreSQL connection management and schema definitions (7 tables: `user_settings`, `user_personas`, `user_sessions`, `user_conversations`, `user_persona_tokens`, `user_memories`, `user_logs`).
- **web/** — FastAPI dashboard. JWT auth (24h tokens). Routes in `web/routes/` for settings, personas, logs, usage, providers, sessions.
- **static/** — Single-page dashboard frontend (vanilla HTML/CSS/JS, dark/light theme). Design spec in `docs/frontend_design_spec.md`.

### Key Data Flow

1. User message → handler (text/photo/document)
2. System prompt enriched with relevant memories (semantic search via NVIDIA embeddings if available, otherwise all memories)
3. OpenAI-compatible streaming call with tool definitions
4. Tool calls dispatched through registry (search, fetch, memory save, TTS, Wikipedia)
5. Response streamed back, split at 4096 chars for Telegram limits
6. Thinking content (e.g., DeepSeek R1 `<think>` blocks) filtered out
7. Cache marked dirty → background sync writes to PostgreSQL

### Key Patterns

- **Multi-persona:** Each user can create personas with different system prompts. Personas have independent sessions and token counters. Default persona auto-created.
- **Session management:** Each persona has multiple chat sessions. Sessions track conversation history independently.
- **Memory system:** User-wide (shared across personas). Supports semantic deduplication via cosine similarity (threshold 0.85). Source tracked as user vs AI-generated.
- **Tool lazy retry:** If a model doesn't support tools, the request is retried without tool definitions.
- **Group chat:** Bot responds only to @mentions or direct replies.
- **Streaming:** Uses generator pattern (`Iterator[StreamChunk]`). Messages are edited in-place as chunks arrive.
- **IDs:** User IDs are Telegram BigInt. Session IDs are auto-incrementing integers managed in-memory.

## Python Refactoring Skills

8 Python refactoring skills are installed in `~/.claude/skills/`. Use them by name:

| Skill | Purpose |
|-------|---------|
| `py-refactor` | Orchestrate comprehensive refactoring across all tools |
| `py-security` | Detect & fix security vulnerabilities |
| `py-complexity` | Reduce cyclomatic/cognitive complexity |
| `py-code-health` | Remove dead code & duplication |
| `py-modernize` | Upgrade tooling & syntax |
| `py-quality-setup` | Configure linters & type checkers |
| `py-git-hooks` | Set up pre-commit hooks |
| `py-test-quality` | Improve test coverage & effectiveness |

Priority: security > test coverage > code health > complexity > modernization.

## Codex Collaboration

This project is also worked on by Codex CLI. Both tools share the same refactoring skills (`.agents/skills/`) and project instructions (`AGENTS.md`).

When working alongside Codex:
- Commit after completing a refactoring phase so Codex can pick up changes.
- Use conventional commit messages: `refactor:`, `fix:`, `chore:`, `feat:`.
- Run `git pull` before starting work.
- Write analysis reports to `reports/` directory.
- Follow the same quality standards defined in pyproject.toml.
