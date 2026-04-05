"""Session rename use case."""

from services import rename_session


def rename_session_text(
    user_id: int,
    persona_name: str,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    if len(args) < 2:
        return f"Usage: {command_prefix}chat rename <title>"

    title = " ".join(args[1:])
    if rename_session(user_id, title, persona_name):
        return f"Session renamed to: {title}"
    return "No current session to rename."

