"""Sessions API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query

from services import (
    get_sessions,
    get_personas,
    get_conversation,
    get_session_message_count,
)
from services.session_service import delete_session
from cache import cache
from web.auth import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(
    persona: str = Query(..., description="Persona name"),
    user_id: int = Depends(get_current_user),
):
    """Return sessions for a given persona."""
    personas = get_personas(user_id)
    if persona not in personas:
        raise HTTPException(status_code=404, detail="Persona not found")
    sessions = get_sessions(user_id, persona)
    result = []
    for s in sessions:
        result.append({
            "id": s["id"],
            "title": s.get("title", "Untitled"),
            "created_at": s.get("created_at", ""),
            "message_count": get_session_message_count(s["id"]),
        })
    return {"sessions": result}


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    """Return messages for a session."""
    # Verify the session belongs to this user
    session = cache.get_session_by_id(session_id)
    if session is None or session.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = get_conversation(session_id)
    return {
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ]
    }


@router.delete("/{session_id}")
async def delete_session_route(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    """Delete a session by ID."""
    session = cache.get_session_by_id(session_id)
    if session is None or session.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    persona_name = session.get("persona_name", "default")
    # Find the 1-based index
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
    return {"ok": True}
