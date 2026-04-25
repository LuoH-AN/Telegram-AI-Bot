"""Shared helpers for sessions routes."""

from datetime import datetime

from fastapi import HTTPException

from cache import cache
from services import get_personas, get_session_message_count
from services.refresh import ensure_user_state


def require_persona(user_id: int, persona: str) -> str:
    name = (persona or "").strip()
    if name not in get_personas(user_id):
        raise HTTPException(status_code=404, detail="Persona not found")
    return name


def require_owned_session(user_id: int, session_id: int) -> dict:
    ensure_user_state(user_id)
    session = cache.get_session_by_id(session_id)
    if session is None or session.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def session_to_payload(session: dict, current_session_id: int | None) -> dict:
    return {
        "id": session["id"],
        "title": session.get("title") or "New Chat",
        "created_at": session.get("created_at", ""),
        "message_count": get_session_message_count(session["id"]),
        "persona": session.get("persona_name", "default"),
        "is_current": session["id"] == current_session_id,
    }


def build_markdown_export(
    persona_name: str,
    session_id: int,
    title: str,
    messages: list[dict],
) -> tuple[str, str]:
    now = datetime.now()
    content = (
        "# AI Chat Export\n"
        f"- Date: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- Persona: {persona_name}\n"
        f"- Session ID: {session_id}\n"
        f"- Session Title: {title}\n"
        f"- Messages: {len(messages)}\n\n---\n\n"
    )
    for message in messages:
        role = "User" if message["role"] == "user" else "Assistant"
        content += f"**{role}:**\n{message['content']}\n\n---\n\n"
    filename = f"chat_{persona_name}_{session_id}_{now.strftime('%Y%m%d_%H%M%S')}.md"
    return content, filename

