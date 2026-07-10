"""user_conversations tool — read/clear/rewrite the calling user's message history."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import commit, dumps, get_cache


def _run(user_id: int, action: str, session_id: int | None, messages: Any) -> ToolResult:
    cache = get_cache()
    if not session_id:
        session_id = cache.get_current_session_id(user_id)
    if not session_id:
        return ToolResult.error("no_session", "No session. Provide session_id.")
    session = cache.get_session_by_id(session_id)
    if not session or session.get("user_id") != user_id:
        return ToolResult.error("not_found", f"Session {session_id} not found")
    conv = cache.get_conversation_by_session(session_id)
    if action == "list":
        lines = [f"Session {session_id} ({len(conv)} messages):"]
        for msg in conv:
            content = msg.get("content") or ""
            preview = content[:80]
            lines.append(f"  [{msg.get('role', '?')}] {preview}{'...' if len(content) > 80 else ''}")
        return ToolResult.text("\n".join(lines))
    if action == "get":
        return ToolResult.text(dumps(conv))
    if action == "clear":
        cache.clear_conversation_by_session(session_id)
        commit()
        return ToolResult.text(f"Cleared session {session_id} ({len(conv)} messages removed)")
    if action == "replace":
        if not isinstance(messages, list):
            return ToolResult.error("bad_messages", "messages must be a list of {role, content}")
        normalized = []
        for msg in messages:
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                return ToolResult.error("bad_messages", "each message needs role and content")
            entry = {"role": msg["role"], "content": msg["content"]}
            if msg.get("reasoning_content"):
                entry["reasoning_content"] = msg["reasoning_content"]
            normalized.append(entry)
        cache.clear_conversation_by_session(session_id)
        for msg in normalized:
            cache.add_message_to_session(session_id, msg["role"], msg["content"], msg.get("reasoning_content"))
        commit()
        return ToolResult.text(f"Replaced session {session_id} with {len(normalized)} messages")
    return ToolResult.error("invalid_action", "action must be list, get, clear, or replace.")


@tool(toolset="admin", description="Read or edit the calling user's message history: list, get, clear, or replace a session. replace overwrites the whole session with messages=[{role, content, ...?}].")
async def user_conversations(
    ctx: ToolContext,
    action: Literal["list", "get", "clear", "replace"],
    session_id: Annotated[int, "Session id. Defaults to the current session."] = 0,
    messages: Annotated[list[Any], "New message list [{role, content}] for replace."] = None,
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run, ctx.user_id, action, int(session_id) or None, messages)
    except Exception as exc:
        return ToolResult.error("operation_failed", f"user_conversations failed: {exc}")
