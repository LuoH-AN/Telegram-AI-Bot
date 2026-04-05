"""Session deletion use case."""

from services import delete_chat_session, get_sessions


def delete_session_text(
    user_id: int,
    persona_name: str,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    if len(args) < 2:
        return f"Usage: {command_prefix}chat delete <number>"

    try:
        index = int(args[1])
    except ValueError:
        return "Please provide a valid session number."

    sessions = get_sessions(user_id, persona_name)
    if index < 1 or index > len(sessions):
        return f"Invalid session number. Valid range: 1-{len(sessions)}"

    display_title = sessions[index - 1].get("title") or "New Chat"
    if delete_chat_session(user_id, index, persona_name):
        return f"Deleted session: {display_title}"
    return "Failed to delete session."

