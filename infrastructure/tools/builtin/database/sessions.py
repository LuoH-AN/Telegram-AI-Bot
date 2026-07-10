"""user_sessions tool — manage the calling user's chat sessions."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

from ._shared import commit, dumps, get_cache


def _run(user_id: int, action: str, persona: str, session_id: int | None, title: str) -> ToolResult:
    cache = get_cache()
    persona = (persona or "").strip() or None

    def owned_session():
        session = cache.get_session_by_id(session_id) if session_id else None
        if not session or session.get("user_id") != user_id:
            return None
        return session

    if action == "list":
        pname = persona or cache.get_current_persona_name(user_id)
        sessions = cache.get_sessions(user_id, pname)
        current = cache.get_current_session_id(user_id, pname)
        lines = [f"Sessions for '{pname}' ({len(sessions)}):"]
        lines += [f"  [{s['id']}] {s.get('title') or '(no title)'}{' *' if s['id'] == current else ''}" for s in sessions]
        return ToolResult.text("\n".join(lines))
    if action == "get":
        if session_id:
            session = owned_session()
            return ToolResult.text(dumps(session)) if session else ToolResult.error("not_found", f"Session {session_id} not found")
        pname = persona or cache.get_current_persona_name(user_id)
        return ToolResult.text(dumps(cache.get_sessions(user_id, pname)))
    if action == "rename":
        if not session_id:
            return ToolResult.error("missing_id", "session_id required")
        if not owned_session():
            return ToolResult.error("not_found", f"Session {session_id} not found")
        cache.update_session_title(session_id, title)
        commit()
        return ToolResult.text(f"Renamed session {session_id} to '{title or '(cleared)'}'")
    if action in ("delete", "switch"):
        session = owned_session()
        if not session:
            return ToolResult.error("not_found", f"Session {session_id or '?'} not found")
        if action == "delete":
            cache.delete_session(session_id, user_id, session["persona_name"])
            commit()
            return ToolResult.text(f"Deleted session {session_id}")
        cache.set_current_session_id(user_id, session["persona_name"], session_id)
        commit()
        return ToolResult.text(f"Switched to session {session_id} ({session['persona_name']})")
    return ToolResult.error("invalid_action", "action must be list, get, rename, delete, or switch.")


@tool(toolset="admin", description="Manage the calling user's chat sessions: list, get, rename, delete, switch. list/get take optional persona; the rest take session_id.")
async def user_sessions(
    ctx: ToolContext,
    action: Literal["list", "get", "rename", "delete", "switch"],
    persona: Annotated[str, "Persona name (for list/get). Defaults to current."] = "",
    session_id: Annotated[int, "Session id (for get/rename/delete/switch)."] = 0,
    title: Annotated[str, "New title (for rename). Empty clears it."] = "",
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run, ctx.user_id, action, persona, int(session_id) or None, title)
    except Exception as exc:
        return ToolResult.error("operation_failed", f"user_sessions failed: {exc}")
