"""Sessions API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cache import cache
from services import (
    get_sessions,
    get_personas,
    get_conversation,
    get_session_message_count,
    create_session,
    clear_conversation,
    reset_token_usage,
)
from services.session_service import delete_session
from services.state_sync_service import refresh_user_state_from_db
from services.log_service import record_web_action
from web.auth import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    persona: str | None = None
    title: str | None = None
    switch_to_new: bool = True


class SessionRename(BaseModel):
    title: str


class SessionClearBody(BaseModel):
    reset_usage: bool = False


def _require_persona(user_id: int, persona: str) -> str:
    name = (persona or "").strip()
    personas = get_personas(user_id)
    if name not in personas:
        raise HTTPException(status_code=404, detail="Persona not found")
    return name


def _require_owned_session(user_id: int, session_id: int) -> dict:
    refresh_user_state_from_db(user_id)
    session = cache.get_session_by_id(session_id)
    if session is None or session.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _session_to_payload(session: dict, current_session_id: int | None) -> dict:
    return {
        "id": session["id"],
        "title": session.get("title") or "New Chat",
        "created_at": session.get("created_at", ""),
        "message_count": get_session_message_count(session["id"]),
        "persona": session.get("persona_name", "default"),
        "is_current": session["id"] == current_session_id,
    }


@router.get("")
async def list_sessions(
    persona: str = Query(..., description="Persona name"),
    user_id: int = Depends(get_current_user),
):
    """Return sessions for a given persona."""
    persona_name = _require_persona(user_id, persona)
    sessions = get_sessions(user_id, persona_name)
    current_id = cache.get_current_session_id(user_id, persona_name)
    result = [_session_to_payload(s, current_id) for s in sessions]
    return {
        "persona": persona_name,
        "current_session_id": current_id,
        "sessions": result,
    }


@router.post("")
async def create_session_route(
    body: SessionCreate,
    user_id: int = Depends(get_current_user),
):
    """Create a new session for persona (default: current persona)."""
    refresh_user_state_from_db(user_id)
    persona_name = (body.persona or "").strip() or cache.get_current_persona_name(user_id)
    _require_persona(user_id, persona_name)
    title = (body.title or "").strip() or None
    previous_id = cache.get_current_session_id(user_id, persona_name)

    session = create_session(user_id, persona_name, title)
    if not body.switch_to_new:
        # Restore previously selected session if requested.
        if previous_id and previous_id != session["id"]:
            cache.set_current_session_id(user_id, persona_name, previous_id)
    current_after = cache.get_current_session_id(user_id, persona_name)

    record_web_action(
        user_id,
        "session.create",
        {"persona": persona_name, "session_id": session["id"]},
        persona_name=persona_name,
    )
    return {"ok": True, "session": _session_to_payload(session, current_after)}


@router.post("/{session_id}/switch")
async def switch_session_route(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    """Switch current session to the given session ID."""
    session = _require_owned_session(user_id, session_id)
    persona_name = session.get("persona_name", "default")
    cache.set_current_session_id(user_id, persona_name, session_id)

    record_web_action(
        user_id,
        "session.switch",
        {"persona": persona_name, "session_id": session_id},
        persona_name=persona_name,
    )
    return {"ok": True}


@router.put("/{session_id}/title")
async def rename_session_route(
    session_id: int,
    body: SessionRename,
    user_id: int = Depends(get_current_user),
):
    """Rename a session title by ID."""
    session = _require_owned_session(user_id, session_id)
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    cache.update_session_title(session_id, title)
    persona_name = session.get("persona_name", "default")
    record_web_action(
        user_id,
        "session.rename",
        {"persona": persona_name, "session_id": session_id, "title": title},
        persona_name=persona_name,
    )
    return {"ok": True}


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    """Return messages for a session."""
    _require_owned_session(user_id, session_id)
    messages = get_conversation(session_id)
    return {
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ]
    }


@router.get("/{session_id}/export")
async def export_session_route(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    """Export a specific session to markdown."""
    session = _require_owned_session(user_id, session_id)
    persona_name = session.get("persona_name", "default")
    messages = get_conversation(session_id)
    if not messages:
        raise HTTPException(status_code=400, detail="No conversation history in this session")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = session.get("title") or "New Chat"

    content = "# AI Chat Export\n"
    content += f"- Date: {now}\n"
    content += f"- Persona: {persona_name}\n"
    content += f"- Session ID: {session_id}\n"
    content += f"- Session Title: {title}\n"
    content += f"- Messages: {len(messages)}\n\n---\n\n"
    for msg in messages:
        role_display = "User" if msg["role"] == "user" else "Assistant"
        content += f"**{role_display}:**\n{msg['content']}\n\n---\n\n"

    filename = f"chat_{persona_name}_{session_id}_{date_str}.md"
    record_web_action(
        user_id,
        "session.export",
        {"persona": persona_name, "session_id": session_id},
        persona_name=persona_name,
    )
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{session_id}/clear")
async def clear_session_route(
    session_id: int,
    body: SessionClearBody,
    user_id: int = Depends(get_current_user),
):
    """Clear one session's conversation. Optional: reset token usage for its persona."""
    session = _require_owned_session(user_id, session_id)
    persona_name = session.get("persona_name", "default")
    clear_conversation(session_id)
    if body.reset_usage:
        reset_token_usage(user_id, persona_name)

    record_web_action(
        user_id,
        "session.clear",
        {"persona": persona_name, "session_id": session_id, "reset_usage": body.reset_usage},
        persona_name=persona_name,
    )
    return {"ok": True, "reset_usage": body.reset_usage}


@router.delete("/{session_id}")
async def delete_session_route(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    """Delete a session by ID."""
    session = _require_owned_session(user_id, session_id)
    persona_name = session.get("persona_name", "default")

    sessions = get_sessions(user_id, persona_name)
    index = None
    for i, s in enumerate(sessions):
        if s["id"] == session_id:
            index = i + 1
            break
    if index is None:
        raise HTTPException(status_code=404, detail="Session not found")

    ok = delete_session(user_id, index, persona_name)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to delete session")

    record_web_action(
        user_id,
        "session.delete",
        {"persona": persona_name, "session_id": session_id},
        persona_name=persona_name,
    )
    return {"ok": True}
