"""Session switch use case."""

from services import get_session_message_count, get_sessions, switch_session
from utils.platform_parity import build_chat_unknown_subcommand_message


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
        return build_chat_unknown_subcommand_message(command_prefix)

    if not switch_session(user_id, index, persona_name):
        total = len(get_sessions(user_id, persona_name))
        return f"Invalid session number. Valid range: 1-{total}"

    sessions = get_sessions(user_id, persona_name)
    session = sessions[index - 1]
    display_title = session.get("title") or "New Chat"
    msg_count = get_session_message_count(session["id"])
    return f"Switched to session #{index}: {display_title}\nMessages: {msg_count}"

