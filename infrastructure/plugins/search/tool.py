"""Search skill tool integration (Tavily backend with key rotation)."""

from __future__ import annotations

from ..core.base import BaseTool
from .constants import DEFAULT_TIMEOUT, DEFAULT_TOP_K, MAX_TOP_K
from .helpers import as_int, as_json
from .keys import KEY_POOL
from .query import search_once


class SearchTool(BaseTool):
    @property
    def name(self) -> str:
        return "search"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Web search via Tavily API. Actions: search/status.",
                    "parameters": self._parameters(),
                },
            }
        ]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "status"],
                    "description": "Action to execute",
                },
                "query": {"type": "string", "description": "Search query for action=search"},
                "top_k": {
                    "type": "integer",
                    "description": f"Max results (default: {DEFAULT_TOP_K}, max: {MAX_TOP_K})",
                },
                "timeout": {"type": "integer", "description": "HTTP timeout seconds (default: 20)"},
            },
            "required": ["action"],
        }

    def get_instruction(self) -> str:
        return (
            "\nSearch skill policy:\n"
            "- Prefer tool `search` action='search' for any web lookup.\n"
            "- Backend is Tavily; configure TAVILY_API_KEYS (comma-separated) for key rotation.\n"
        )

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        del user_id, tool_name
        action = str(arguments.get("action") or "").strip().lower()
        timeout = as_int(arguments.get("timeout"), default=DEFAULT_TIMEOUT, minimum=3, maximum=120)

        if action == "status":
            return as_json({"ok": True, "backend": "tavily", "keys": KEY_POOL.snapshot()})

        if action == "search":
            query = str(arguments.get("query") or "").strip()
            if not query:
                return "Error: action=search requires non-empty query."
            top_k = as_int(arguments.get("top_k"), default=DEFAULT_TOP_K, minimum=1, maximum=MAX_TOP_K)
            return as_json(search_once(query=query, top_k=top_k, timeout_seconds=timeout))

        return "Error: invalid action. Use one of: search/status."
