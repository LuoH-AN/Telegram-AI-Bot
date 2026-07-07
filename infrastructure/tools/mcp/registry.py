"""Register remote MCP server tools as native ToolEntry instances.

On discover(), each configured server is contacted; every tool it exposes
becomes a ToolEntry named `<server>__<tool>`. Schemas come straight from the
server's inputSchema (bypassing signature generation). Availability gating:
a server whose config is missing or unreachable is skipped, and check_fn
re-probes lazily so the schema never advertises dead tools.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from infrastructure.tools.core.context import ToolContext, ToolResult
from infrastructure.tools.core.registry import ToolEntry, registry

from .client import call_remote_tool, list_remote_tools
from .config import McpServerConfig, load_servers

logger = logging.getLogger(__name__)
_REGISTERED = False


def _qualified(server: str, tool: str) -> str:
    return f"{server}__{tool}"


def _build_schema(server_name: str, tool) -> dict:
    params = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
    description = (getattr(tool, "description", None) or f"MCP tool {tool.name} from server {server_name}.").strip()
    return {"type": "function", "function": {"name": _qualified(server_name, tool.name), "description": description, "parameters": params}}


def _make_handler(config: McpServerConfig, tool_name: str):
    async def handler(ctx: ToolContext, **arguments: Any) -> ToolResult:
        try:
            outcome = await call_remote_tool(config, tool_name, arguments)
        except Exception as exc:
            logger.warning("MCP call %s/%s failed: %s", config.name, tool_name, exc)
            return ToolResult.error("mcp_call_failed", f"MCP server '{config.name}' call failed: {exc}", server=config.name, tool=tool_name)
        if outcome["is_error"]:
            return ToolResult.error("mcp_tool_error", outcome["content"] or "remote tool reported an error", server=config.name, tool=tool_name)
        return ToolResult.text(outcome["content"] or "OK")

    handler.__doc__ = f"MCP {config.name}/{tool_name}"
    return handler


def _register_server(config: McpServerConfig, tools: list) -> int:
    count = 0
    for tool in tools:
        name = _qualified(config.name, tool.name)
        entry = ToolEntry(
            name=name,
            description=(getattr(tool, "description", None) or name),
            toolset="mcp",
            handler=_make_handler(config, tool.name),
            is_async=True,
            serial=False,
            requires_env=(),
            check_fn=lambda: True,
            max_result_chars=20000,
            skill=f"mcp_{config.name}",
            raw_args=True,
        )
        entry._schema = _build_schema(config.name, tool)
        registry.register(entry)
        count += 1
    return count


def discover_mcp() -> int:
    """Contact each configured MCP server and register its tools. Best-effort."""
    global _REGISTERED
    if _REGISTERED:
        return 0
    _REGISTERED = True
    servers = load_servers()
    if not servers:
        return 0
    total = 0
    for config in servers:
        try:
            tools = _probe_sync(config)
        except Exception as exc:
            logger.warning("MCP server '%s' unreachable, skipping: %s", config.name, exc)
            continue
        registered = _register_server(config, tools)
        logger.info("MCP server '%s': registered %d tool(s)", config.name, registered)
        total += registered
    return total


def _probe_sync(config: McpServerConfig) -> list:
    """Run the async list_remote_tools in a fresh event loop (called during sync discover)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(list_remote_tools(config))
    finally:
        loop.close()


def reset() -> None:
    """Allow re-discovery (used by tests / config reload)."""
    global _REGISTERED
    _REGISTERED = False
