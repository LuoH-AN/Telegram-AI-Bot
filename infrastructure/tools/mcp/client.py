"""MCP client connections: establish a session per server, list and call tools.

Transport-aware: streamable-http (3-tuple, needs an httpx client for headers),
sse / stdio (2-tuple). Each call opens a fresh session — MCP servers are
request-scoped for us; long-lived pooling is a future optimization.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from .config import McpServerConfig

logger = logging.getLogger(__name__)


async def _enter_http(stack: AsyncExitStack, config: McpServerConfig):
    import httpx

    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    http_client = await stack.enter_async_context(httpx.AsyncClient(headers=config.headers or None))
    read, write, _get_sid = await stack.enter_async_context(streamable_http_client(config.url, http_client=http_client))
    return await stack.enter_async_context(ClientSession(read, write))


async def _enter_sse(stack: AsyncExitStack, config: McpServerConfig):
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client

    read, write = await stack.enter_async_context(sse_client(config.url, headers=config.headers or None))
    return await stack.enter_async_context(ClientSession(read, write))


async def _enter_stdio(stack: AsyncExitStack, config: McpServerConfig):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=config.command, args=config.args, env=config.env or None)
    read, write = await stack.enter_async_context(stdio_client(params))
    return await stack.enter_async_context(ClientSession(read, write))


_OPENERS = {"http": _enter_http, "sse": _enter_sse, "stdio": _enter_stdio}


async def _with_session(config: McpServerConfig):
    """Open + initialize a session inside an AsyncExitStack. Caller closes the stack."""
    opener = _OPENERS.get(config.transport)
    if opener is None:
        raise ValueError(f"unknown MCP transport: {config.transport}")
    stack = AsyncExitStack()
    await stack.__aenter__()
    try:
        session = await opener(stack, config)
        await session.initialize()
        return stack, session
    except Exception:
        await stack.aclose()
        raise


async def list_remote_tools(config: McpServerConfig) -> list:
    """Connect to a server, return its raw Tool list. Raises on failure."""
    stack, session = await _with_session(config)
    try:
        result = await session.list_tools()
        return list(result.tools or [])
    finally:
        await stack.aclose()


async def call_remote_tool(config: McpServerConfig, tool_name: str, arguments: dict[str, Any]) -> dict:
    """Call a remote tool. Returns {'ok', 'content', 'is_error'}."""
    stack, session = await _with_session(config)
    try:
        result = await session.call_tool(tool_name, arguments or {})
    finally:
        await stack.aclose()
    texts = [b.text for b in (result.content or []) if getattr(b, "text", None) is not None]
    return {"ok": not result.isError, "content": "\n".join(texts), "is_error": bool(result.isError)}
