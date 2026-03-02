"""Shared helpers for token estimation and tool-call handling."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

_SLOW_WEB_TOOL_NAMES = {
    "page_screenshot",
    "page_content",
    "crawl4ai_fetch",
    "browser_start_session",
    "browser_list_sessions",
    "browser_close_session",
    "browser_goto",
    "browser_click",
    "browser_type",
    "browser_press",
    "browser_wait_for",
    "browser_get_state",
}


class ToolCallLike(Protocol):
    """Structural type for tool call objects from different AI clients."""

    name: str
    arguments: str
    id: str | None


def estimate_tokens_str(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK."""
    if not text:
        return 0
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff" or "\u3000" <= char <= "\u30ff")
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4))


def estimate_tokens(messages: Sequence[Mapping[str, object]]) -> int:
    """Estimate total prompt tokens from a list of chat messages."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        total += estimate_tokens_str(str(content)) + 4
    return total


def tool_dedup_key(tool_call: ToolCallLike) -> str:
    """Extract dedup key from a tool call (name + primary argument)."""
    try:
        args = json.loads(tool_call.arguments)
    except Exception:
        return f"{tool_call.name}:{tool_call.arguments}"

    if tool_call.name.startswith("browser_"):
        # Stateful browser actions may legitimately repeat with same args.
        return f"{tool_call.name}:{tool_call.id}"
    if tool_call.name == "url_fetch":
        return f"url_fetch:{args.get('url', '')}"
    if tool_call.name == "crawl4ai_fetch":
        return f"crawl4ai_fetch:{args.get('url', '')}"
    if tool_call.name == "web_search":
        return f"web_search:{args.get('query', '')}"
    return f"{tool_call.name}:{tool_call.arguments}"


def effective_tool_timeout(tool_calls: Sequence[ToolCallLike], *, default_timeout: int) -> int:
    """Compute timeout for awaiting tool processing from observed tool calls."""
    timeout = default_timeout
    for tool_call in tool_calls:
        if tool_call.name == "shell_exec":
            try:
                args = json.loads(tool_call.arguments)
                requested = int(args.get("timeout", 0))
                if requested > timeout:
                    timeout = min(requested + 5, 125)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        elif tool_call.name == "crawl4ai_fetch":
            timeout = max(timeout, 60)
            try:
                args = json.loads(tool_call.arguments)
                requested_ms = int(args.get("timeout_ms", 60000))
                requested_sec = max(5, min(requested_ms, 180000)) // 1000
                timeout = max(timeout, min(requested_sec + 15, 210))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        elif tool_call.name.startswith("browser_"):
            timeout = max(timeout, 90)
            try:
                args = json.loads(tool_call.arguments)
                requested_ms = 0
                if tool_call.name == "browser_wait_for":
                    requested_ms = int(args.get("timeout_ms", 10000)) + int(args.get("wait_ms", 0))
                else:
                    requested_ms = int(args.get("timeout_ms", 10000))
                requested_wait = float(args.get("wait", 0))
                requested_sec = int(max(0, min(requested_ms, 180000)) / 1000 + max(0.0, min(requested_wait, 30.0)))
                timeout = max(timeout, min(requested_sec + 15, 210))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        elif tool_call.name in _SLOW_WEB_TOOL_NAMES:
            timeout = max(timeout, 60)
    return timeout
