"""Search skill tool integration."""

from __future__ import annotations

from ..core.base import BaseTool
from .constants import DEFAULT_PORT, DEFAULT_TIMEOUT, REPO_DIR, STATE_LOCK
from .helpers import as_int, as_json, as_port
from .install import ensure_binary, ensure_repo
from .query import search_once
from .server import ensure_started, status_payload, stop_server


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
                    "description": (
                        "Use integrated web search skill. "
                        "Supports install/start/status/stop/search actions."
                    ),
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
                    "enum": ["search", "status", "install", "start", "stop"],
                    "description": "Action to execute",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for action=search",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results to return (default: 8, max: 20)",
                },
                "port": {
                    "type": "integer",
                    "description": "Local search HTTP port (default: 18080)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "HTTP timeout seconds (default: 20)",
                },
            },
            "required": ["action"],
        }

    def get_instruction(self) -> str:
        return (
            "\nSearch skill policy:\n"
            "- For web queries, prefer tool `search` action='search' instead of manual terminal cloning/running.\n"
            "- Do not call terminal to manage search service unless search tool returns an explicit failure requiring manual intervention.\n"
        )

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        del user_id, tool_name
        action = str(arguments.get("action") or "").strip().lower()
        port = as_port(arguments.get("port"), default=DEFAULT_PORT)
        timeout = as_int(arguments.get("timeout"), default=DEFAULT_TIMEOUT, minimum=3, maximum=120)

        if action == "status":
            return as_json(status_payload(port=port))
        if action == "install":
            with STATE_LOCK:
                repo = ensure_repo()
                binary = ensure_binary()
            payload = status_payload(port=port)
            payload.update({"ok": True, "repo_dir": str(repo), "binary": str(binary), "message": "Search service installed."})
            return as_json(payload)
        if action == "start":
            with STATE_LOCK:
                repo = ensure_repo()
                binary = ensure_binary()
                started = ensure_started(
                    port=port,
                    binary_path=binary,
                    timeout_seconds=timeout,
                    cwd_path=(REPO_DIR if REPO_DIR.exists() else repo),
                )
            payload = status_payload(port=port)
            payload.update(
                {
                    "ok": bool(started.get("ok")),
                    "repo_dir": str(repo),
                    "binary": str(binary),
                    "message": str(started.get("message") or ""),
                }
            )
            if "log_file" in started:
                payload["log_file"] = started["log_file"]
            return as_json(payload)
        if action == "stop":
            result = stop_server()
            payload = status_payload(port=port)
            payload.update({"ok": bool(result.get("ok")), "message": str(result.get("message") or "")})
            return as_json(payload)
        if action == "search":
            query = str(arguments.get("query") or "").strip()
            if not query:
                return "Error: action=search requires non-empty query."
            top_k = as_int(arguments.get("top_k"), default=8, minimum=1, maximum=20)
            with STATE_LOCK:
                repo = ensure_repo()
                binary = ensure_binary()
                started = ensure_started(
                    port=port,
                    binary_path=binary,
                    timeout_seconds=timeout,
                    cwd_path=(REPO_DIR if REPO_DIR.exists() else repo),
                )
            if not started.get("ok"):
                return as_json({"ok": False, "message": started.get("message") or "Failed to start search service."})
            return as_json(search_once(query=query, port=port, timeout_seconds=timeout, top_k=top_k))

        return "Error: invalid action. Use one of: search/status/install/start/stop."
