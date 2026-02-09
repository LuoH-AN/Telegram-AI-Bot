"""Chat export service."""

import io
from datetime import datetime

from .conversation_service import get_conversation
from .persona_service import get_current_persona_name


def export_to_markdown(user_id: int, persona_name: str = None) -> io.BytesIO | None:
    """Export conversation history to markdown format.

    Args:
        user_id: User ID
        persona_name: Optional persona name. If None, uses current persona.

    Returns a BytesIO buffer with the markdown content, or None if no conversation.
    """
    if persona_name is None:
        persona_name = get_current_persona_name(user_id)

    conversation = get_conversation(user_id, persona_name)

    if not conversation:
        return None

    # Build markdown content
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    content = "# AI Chat Export\n"
    content += f"- Date: {now}\n"
    content += f"- Persona: {persona_name}\n"
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
