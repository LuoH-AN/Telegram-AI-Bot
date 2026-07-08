"""Session switch use case."""

from domain.services import get_session_message_count, get_sessions, switch_session


def switch_session_text(
    user_id: int,
    persona_name: str,
    subcmd: str,
    *,
    command_prefix: str,
) -> str:
    try:
        index = int(subcmd)
    except ValueError:
        return f"❌ Invalid session number. Use `{command_prefix}chat switch <number>`."

    if not switch_session(user_id, index, persona_name):
        total = len(get_sessions(user_id, persona_name))
        return f"❌ Invalid session number. Valid range: `1-{total}`"

    sessions = get_sessions(user_id, persona_name)
    session = sessions[index - 1]
    display_title = session.get("title") or "New Chat"
    msg_count = get_session_message_count(session["id"])
    return f"✅ **Switched to session #{index}:** {display_title}\n**Messages:** {msg_count}"

