"""Session mutation routes: switch/rename/clear/delete."""

from fastapi import Depends, HTTPException

from cache import cache
from services import clear_conversation, get_sessions, reset_token_usage
from services.log import record_web_action
from services.session import delete_session
from web.auth import get_current_user

from .helpers import require_owned_session
from .models import SessionClearBody, SessionRename
from .router import router


@router.post("/{session_id}/switch")
async def switch_session_route(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    session = require_owned_session(user_id, session_id)
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
    session = require_owned_session(user_id, session_id)
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


@router.post("/{session_id}/clear")
async def clear_session_route(
    session_id: int,
    body: SessionClearBody,
    user_id: int = Depends(get_current_user),
):
    session = require_owned_session(user_id, session_id)
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
    session = require_owned_session(user_id, session_id)
    persona_name = session.get("persona_name", "default")
    sessions = get_sessions(user_id, persona_name)
    index = next((i + 1 for i, current in enumerate(sessions) if current["id"] == session_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not delete_session(user_id, index, persona_name):
        raise HTTPException(status_code=400, detail="Failed to delete session")
    record_web_action(
        user_id,
        "session.delete",
        {"persona": persona_name, "session_id": session_id},
        persona_name=persona_name,
    )
    return {"ok": True}

