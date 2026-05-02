"""Session content routes: messages/export."""

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse

from services import get_conversation
from services.log import record_web_action
from web.auth import get_current_user

from .utils import build_markdown_export, require_owned_session
from .route import router


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    await require_owned_session(user_id, session_id)
    return {
        "messages": [
            {"role": message["role"], "content": message["content"]}
            for message in get_conversation(session_id)
        ]
    }


@router.get("/{session_id}/export")
async def export_session_route(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    session = await require_owned_session(user_id, session_id)
    persona_name = session.get("persona_name", "default")
    messages = get_conversation(session_id)
    if not messages:
        raise HTTPException(status_code=400, detail="No conversation history in this session")

    content, filename = build_markdown_export(
        persona_name,
        session_id,
        session.get("title") or "New Chat",
        messages,
    )
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
