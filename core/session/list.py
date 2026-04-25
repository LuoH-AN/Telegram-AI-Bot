"""Render session list text."""

from services import get_current_session_id, get_session_message_count, get_sessions
from utils.platform import build_chat_commands_message, build_chat_no_sessions_message


def build_session_list_text(
    user_id: int,
    persona_name: str,
    *,
    command_prefix: str,
) -> str:
    sessions = get_sessions(user_id, persona_name)
    current_id = get_current_session_id(user_id, persona_name)
    if not sessions:
        return build_chat_no_sessions_message(persona_name, command_prefix)

    lines = [f"Sessions (persona: {persona_name})\n"]
    for index, session in enumerate(sessions, 1):
        marker = "> " if session["id"] == current_id else "  "
        title = session.get("title") or "New Chat"
        msg_count = get_session_message_count(session["id"])
        lines.append(f"{marker}{index}. {title} ({msg_count} msgs)")

    lines.append("")
    lines.append(build_chat_commands_message(command_prefix))
    return "\n".join(lines)

