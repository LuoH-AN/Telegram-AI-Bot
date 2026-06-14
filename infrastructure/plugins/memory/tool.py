"""Long-term memory tool."""

from __future__ import annotations

import json

from domain.services import add_memory, get_memories
from infrastructure.cache import sync_to_database

from ..core.base import BaseTool

MAX_TOOL_MEMORY_CHARS = 800


class MemoryTool(BaseTool):
    @property
    def name(self) -> str:
        return "memory"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "save_memory",
                    "description": "Save a durable user preference, personal fact, or project constraint to long-term memory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Concise standalone memory to save. Do not include secrets or transient task details.",
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_memories",
                    "description": "List the user's saved long-term memories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of memories to return, newest last. Default 20.",
                            },
                        },
                    },
                },
            },
        ]

    def get_instruction(self) -> str:
        return (
            "\nMemory tool policy:\n"
            "- Use `save_memory` for stable preferences, personal facts, or ongoing project constraints only.\n"
            "- Do not save secrets, credentials, temporary task details, or sensitive inferences.\n"
            "- Keep each saved memory under one sentence and avoid duplicates.\n"
        )

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        if tool_name == "save_memory":
            return self._save(user_id, arguments)
        if tool_name == "list_memories":
            return self._list(user_id, arguments)
        return f"Error: unknown memory tool '{tool_name}'."

    def _save(self, user_id: int, arguments: dict) -> str:
        content = str(arguments.get("content") or "").strip()
        if not content:
            return "Error: content is required."
        if len(content) > MAX_TOOL_MEMORY_CHARS:
            content = content[:MAX_TOOL_MEMORY_CHARS].rstrip()
        memory = add_memory(user_id, content, source="infrastructure.ai")
        sync_to_database()
        return json.dumps(
            {
                "ok": True,
                "memory": {
                    "id": memory.get("id"),
                    "content": memory.get("content"),
                    "source": memory.get("source"),
                },
            },
            ensure_ascii=False,
        )

    def _list(self, user_id: int, arguments: dict) -> str:
        raw_limit = arguments.get("limit", 20)
        try:
            limit = max(1, min(100, int(raw_limit)))
        except (TypeError, ValueError):
            limit = 20
        all_memories = get_memories(user_id)
        offset = max(0, len(all_memories) - limit)
        memories = all_memories[offset:]
        items = [
            {
                "index": offset + index,
                "content": memory.get("content", ""),
                "source": memory.get("source", "user"),
            }
            for index, memory in enumerate(memories, 1)
        ]
        return json.dumps({"ok": True, "memories": items}, ensure_ascii=False)
