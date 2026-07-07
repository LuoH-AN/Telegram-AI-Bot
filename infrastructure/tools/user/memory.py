"""Long-term memory tools (save + list)."""

from __future__ import annotations

import asyncio
from typing import Annotated

from infrastructure.tools.core import ToolContext, ToolResult, tool

MEMORY_INSTRUCTION = (
    "\nMemory tool policy:\n"
    "- Use `save_memory` for stable preferences, personal facts, or ongoing project constraints only.\n"
    "- Do not save secrets, credentials, temporary task details, or sensitive inferences.\n"
    "- Keep each saved memory under one sentence and avoid duplicates.\n"
)

MAX_TOOL_MEMORY_CHARS = 800


@tool(toolset="user", skill="memory", serial=True, instruction=MEMORY_INSTRUCTION, description="Save a durable user preference, personal fact, or project constraint to long-term memory.")
async def save_memory(ctx: ToolContext, content: Annotated[str, "Concise standalone memory. No secrets or transient task details."]) -> ToolResult:
    content = (content or "").strip()
    if not content:
        return ToolResult.error("empty_content", "content is required")
    if len(content) > MAX_TOOL_MEMORY_CHARS:
        content = content[:MAX_TOOL_MEMORY_CHARS].rstrip()

    def _save():
        from domain.services import add_memory
        from infrastructure.cache import sync_to_database

        memory = add_memory(ctx.user_id, content, source="infrastructure.ai")
        sync_to_database()
        return memory

    memory = await asyncio.to_thread(_save)
    return ToolResult.data({"ok": True, "memory": {"id": memory.get("id"), "content": memory.get("content"), "source": memory.get("source")}})


@tool(toolset="user", skill="memory", serial=True, description="List the user's saved long-term memories.")
async def list_memories(ctx: ToolContext, limit: int = 20) -> ToolResult:
    limit = max(1, min(100, int(limit)))

    def _list():
        from domain.services import get_memories
        return get_memories(ctx.user_id)

    all_memories = await asyncio.to_thread(_list)
    offset = max(0, len(all_memories) - limit)
    memories = all_memories[offset:]
    items = [{"index": offset + i, "content": m.get("content", ""), "source": m.get("source", "user")} for i, m in enumerate(memories, 1)]
    return ToolResult.data({"ok": True, "memories": items})
