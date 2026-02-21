"""Chat export service."""

import io
from datetime import datetime

from .conversation_service import ensure_session, get_conversation
from .persona_service import get_current_persona_name
from .session_service import get_current_session_id


def export_to_markdown(user_id: int, persona_name: str = None) -> io.BytesIO | None:
    """Export current session history to markdown format.

    Args:
        user_id: User ID
        persona_name: Optional persona name. If None, uses current persona.

    Returns a BytesIO buffer with the markdown content, or None if no conversation.
    """
    if persona_name is None:
        persona_name = get_current_persona_name(user_id)

    session_id = get_current_session_id(user_id, persona_name)
    if session_id is None:
        session_id = ensure_session(user_id, persona_name)

    conversation = get_conversation(session_id)

    if not conversation:
        return None

    # Build markdown content
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    content = "# AI Chat Export\n"
    content += f"- Date: {now}\n"
    content += f"- Persona: {persona_name}\n"
    content += f"- Session ID: {session_id}\n"
    content += f"- Messages: {len(conversation)}\n\n"
    content += "---\n\n"

    for msg in conversation:
        role_display = "User" if msg["role"] == "user" else "Assistant"
        content += f"**{role_display}:**\n{msg['content']}\n\n---\n\n"

    # Create file in memory
    file_buffer = io.BytesIO(content.encode("utf-8"))
    file_buffer.name = f"chat_{persona_name}_{date_str}.md"

    return file_buffer


def get_export_filename(persona_name: str = "chat") -> str:
    """Get a timestamped export filename."""
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"chat_{persona_name}_{date_str}.md"
