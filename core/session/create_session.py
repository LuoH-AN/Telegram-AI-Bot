"""Session creation use case."""

from services import create_session, get_sessions


def create_session_text(user_id: int, persona_name: str, args: list[str]) -> str:
    title = " ".join(args[1:]) if len(args) > 1 else None
    create_session(user_id, persona_name, title)
    display_title = title or "New Chat"
    count = len(get_sessions(user_id, persona_name))
    return (
        f"Created new session: {display_title}\n"
        f"Switched to session #{count}"
    )

