"""Long-term memory tools (save + list)."""

from __future__ import annotations

import asyncio
import re
from typing import Annotated, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

MEMORY_INSTRUCTION = (
    "\nMemory tool policy:\n"
    "- Use `save_memory` for stable preferences, personal facts, or ongoing project constraints only.\n"
    "- Do not save secrets, credentials, temporary task details, or sensitive inferences.\n"
    "- Keep each saved memory under one sentence and avoid duplicates.\n"
)

MAX_TOOL_MEMORY_CHARS = 800
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _contains_secret(content: str) -> bool:
    return any(pattern.search(content) for pattern in _SECRET_PATTERNS)


@tool(toolset="user", skill="memory", serial=True, side_effects=True, instruction=MEMORY_INSTRUCTION, description="Save a durable user preference, personal fact, or project constraint to long-term memory.")
async def save_memory(ctx: ToolContext, content: Annotated[str, "Concise standalone memory. No secrets or transient task details."]) -> ToolResult:
    content = (content or "").strip()
    if not content:
        return ToolResult.error("empty_content", "content is required")
    if _contains_secret(content):
        return ToolResult.error("secret_detected", "memory appears to contain a credential or private key and was not saved")
    if len(content) > MAX_TOOL_MEMORY_CHARS:
        return ToolResult.error("content_too_long", f"memory must be {MAX_TOOL_MEMORY_CHARS} characters or fewer")

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


@tool(toolset="user", skill="memory", serial=True, side_effects=True, description="Update, delete, or clear the calling user's long-term memories. clear requires expected_count to match the current count.")
async def manage_memory(
    ctx: ToolContext,
    action: Literal["update", "delete", "clear"],
    index: Annotated[int, "One-based memory index for update/delete."] = 0,
    content: Annotated[str, "Replacement memory content for update."] = "",
    expected_count: Annotated[int, "Required current memory count for clear."] = -1,
) -> ToolResult:
    def _manage():
        from domain.services import clear_memories, delete_memory, get_memories, update_memory
        from infrastructure.cache import sync_to_database

        memories = get_memories(ctx.user_id)
        if action == "clear":
            if expected_count != len(memories):
                return ToolResult.error(
                    "count_mismatch",
                    f"expected_count must match the current count ({len(memories)})",
                )
            removed = clear_memories(ctx.user_id)
            sync_to_database()
            return ToolResult.text(f"Cleared {removed} memories")
        if index < 1:
            return ToolResult.error("bad_index", "index must be one-based")
        if action == "delete":
            if not delete_memory(ctx.user_id, index):
                return ToolResult.error("not_found", f"memory index {index} not found")
            sync_to_database()
            return ToolResult.text(f"Deleted memory {index}")
        replacement = (content or "").strip()
        if not replacement or len(replacement) > MAX_TOOL_MEMORY_CHARS:
            return ToolResult.error("bad_content", f"content must be 1-{MAX_TOOL_MEMORY_CHARS} characters")
        if _contains_secret(replacement):
            return ToolResult.error("secret_detected", "replacement appears to contain a credential")
        if not update_memory(ctx.user_id, index, replacement):
            return ToolResult.error("not_found", f"memory index {index} not found")
        sync_to_database()
        return ToolResult.text(f"Updated memory {index}")

    return await asyncio.to_thread(_manage)
