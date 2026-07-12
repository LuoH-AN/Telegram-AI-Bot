"""user_conversations tool — read/clear/rewrite the calling user's message history."""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Annotated, Any, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import commit, dumps, get_cache, run_tool

_BACKUP_ROOT = Path("/data/telegram_ai_bot/backups/conversations") if Path("/data").is_dir() else Path("runtime/backups/conversations")


def _normalize_messages(messages: Any) -> tuple[list[dict] | None, ToolResult | None]:
    if not isinstance(messages, list):
        return None, ToolResult.error("bad_messages", "messages must be a list of {role, content}")
    if len(messages) > 1000:
        return None, ToolResult.error("too_many_messages", "replace supports at most 1000 messages")
    normalized = []
    for msg in messages:
        if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
            return None, ToolResult.error("bad_messages", "each message needs role and content")
        role = msg["role"]
        content = msg["content"]
        reasoning = msg.get("reasoning_content")
        if role not in {"user", "assistant"}:
            return None, ToolResult.error("bad_role", "conversation roles must be user or assistant")
        if not isinstance(content, str) or len(content) > 200000:
            return None, ToolResult.error("bad_content", "message content must be a string up to 200000 characters")
        if reasoning is not None and not isinstance(reasoning, str):
            return None, ToolResult.error("bad_reasoning", "reasoning_content must be a string")
        entry = {"role": role, "content": content}
        if reasoning:
            entry["reasoning_content"] = reasoning[:200000]
        normalized.append(entry)
    return normalized, None


def _write_backup(user_id: int, session_id: int, messages: list[dict]) -> str:
    backup_id = f"{int(time.time())}-{secrets.token_hex(4)}"
    directory = _BACKUP_ROOT / str(user_id) / str(session_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{backup_id}.json"
    payload = {"user_id": user_id, "session_id": session_id, "messages": messages}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)
    return backup_id


def _read_backup(user_id: int, session_id: int, backup_id: str) -> list[dict]:
    if not backup_id or any(char not in "0123456789abcdef-" for char in backup_id.lower()):
        raise ValueError("invalid backup_id")
    path = _BACKUP_ROOT / str(user_id) / str(session_id) / f"{backup_id}.json"
    payload = json.loads(path.read_text("utf-8"))
    if payload.get("user_id") != user_id or payload.get("session_id") != session_id:
        raise ValueError("backup ownership mismatch")
    normalized, error = _normalize_messages(payload.get("messages"))
    if error:
        raise ValueError("backup contains invalid messages")
    return normalized


def _replace(cache, session_id: int, messages: list[dict]) -> None:
    cache.clear_conversation_by_session(session_id)
    for msg in messages:
        cache.add_message_to_session(session_id, msg["role"], msg["content"], msg.get("reasoning_content"))


def _run(
    user_id: int,
    action: str,
    session_id: int | None,
    messages: Any,
    expected_message_count: int,
    backup_id: str,
) -> ToolResult:
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
        if expected_message_count != len(conv):
            return ToolResult.error("count_mismatch", f"expected_message_count must equal {len(conv)}")
        saved = _write_backup(user_id, session_id, conv)
        cache.clear_conversation_by_session(session_id)
        commit()
        return ToolResult.text(f"Cleared session {session_id} ({len(conv)} messages removed); backup_id={saved}")
    if action == "replace":
        if expected_message_count != len(conv):
            return ToolResult.error("count_mismatch", f"expected_message_count must equal {len(conv)}")
        normalized, error = _normalize_messages(messages)
        if error:
            return error
        saved = _write_backup(user_id, session_id, conv)
        _replace(cache, session_id, normalized)
        commit()
        return ToolResult.text(f"Replaced session {session_id} with {len(normalized)} messages; backup_id={saved}")
    if action == "restore":
        if expected_message_count != len(conv):
            return ToolResult.error("count_mismatch", f"expected_message_count must equal {len(conv)}")
        try:
            restored = _read_backup(user_id, session_id, backup_id)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return ToolResult.error("bad_backup", str(exc))
        saved = _write_backup(user_id, session_id, conv)
        _replace(cache, session_id, restored)
        commit()
        return ToolResult.text(f"Restored {len(restored)} messages from {backup_id}; previous state backup_id={saved}")
    return ToolResult.error("invalid_action", "action must be list, get, clear, replace, or restore.")


@tool(toolset="admin", side_effects=True, description="Read or edit the calling user's message history: list, get, clear, or replace a session. replace overwrites the whole session with messages=[{role, content, ...?}].")
async def user_conversations(
    ctx: ToolContext,
    action: Literal["list", "get", "clear", "replace", "restore"],
    session_id: Annotated[int, "Session id. Defaults to the current session."] = 0,
    messages: Annotated[list[Any], "New message list [{role, content}] for replace."] = None,
    expected_message_count: Annotated[int, "Required current message count for clear/replace/restore."] = -1,
    backup_id: Annotated[str, "Backup id returned by an earlier clear/replace/restore."] = "",
) -> ToolResult:
    return await run_tool(
        "user_conversations",
        _run,
        ctx.user_id,
        action,
        int(session_id) or None,
        messages,
        int(expected_message_count),
        backup_id,
    )
