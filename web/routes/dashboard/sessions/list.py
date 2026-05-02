"""List/create session routes."""

from fastapi import Depends, Query

from cache import cache
from services import create_session, get_sessions
from services.log import record_web_action
from services.refresh import ensure_user_state
from web.auth import get_current_user

from .utils import require_persona, session_to_payload
from .schema import SessionCreate
from .route import router


@router.get("")
async def list_sessions(
    persona: str = Query(..., description="Persona name"),
    user_id: int = Depends(get_current_user),
):
    persona_name = require_persona(user_id, persona)
    sessions = get_sessions(user_id, persona_name)
    current_id = cache.get_current_session_id(user_id, persona_name)
    return {
        "persona": persona_name,
        "current_session_id": current_id,
        "sessions": [session_to_payload(session, current_id) for session in sessions],
    }


@router.post("")
async def create_session_route(
    body: SessionCreate,
    user_id: int = Depends(get_current_user),
):
    await ensure_user_state(user_id)
    persona_name = (body.persona or "").strip() or cache.get_current_persona_name(user_id)
    require_persona(user_id, persona_name)
    previous_id = cache.get_current_session_id(user_id, persona_name)
    session = create_session(user_id, persona_name, (body.title or "").strip() or None)
    if not body.switch_to_new and previous_id and previous_id != session["id"]:
        cache.set_current_session_id(user_id, persona_name, previous_id)

    current_after = cache.get_current_session_id(user_id, persona_name)
    record_web_action(
        user_id,
        "session.create",
        {"persona": persona_name, "session_id": session["id"]},
        persona_name=persona_name,
    )
    return {"ok": True, "session": session_to_payload(session, current_after)}
