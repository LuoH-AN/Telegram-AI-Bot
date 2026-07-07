"""Web search tool (Tavily backend with key rotation)."""

from __future__ import annotations

import asyncio
from typing import Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from .tavily import search_once, status_snapshot

SEARCH_DESCRIPTION = "Web search via Tavily API. action=search runs a query; action=status reports key-pool health."

SEARCH_INSTRUCTION = (
    "\nSearch tool policy:\n"
    "- Prefer the `search` tool for any web lookup.\n"
    "- Backend is Tavily; configure TAVILY_API_KEYS (comma-separated) for key rotation.\n"
)


def _dynamic_description() -> dict:
    if status_snapshot()["configured"] == 0:
        return {"description": SEARCH_DESCRIPTION + "\n\nNOTE: backend is currently unconfigured (set TAVILY_API_KEYS)."}
    return {}


@tool(toolset="web", skill="search", max_result_chars=12000, dynamic_schema=_dynamic_description, instruction=SEARCH_INSTRUCTION, description=SEARCH_DESCRIPTION)
async def search(ctx: ToolContext, action: Literal["search", "status"], query: str = "", top_k: int = 8, timeout: int = 20) -> ToolResult:
    if action == "status":
        return ToolResult.data({"ok": True, "backend": "tavily", "keys": status_snapshot()})
    query = (query or "").strip()
    if not query:
        return ToolResult.error("empty_query", "query is required for action=search")
    top_k = max(1, min(20, int(top_k)))
    timeout = max(3, min(120, int(timeout)))
    result = await asyncio.to_thread(search_once, query=query, top_k=top_k, timeout_seconds=timeout)
    return ToolResult.data(result)
