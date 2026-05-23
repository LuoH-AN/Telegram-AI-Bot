"""Session rename use case."""

from services import (
    generate_title_for_session,
    get_sessions,
    rename_session,
)


def _parse_index(token: str, total: int) -> int | None:
    try:
        value = int(token)
    except ValueError:
        return None
    if value < 1 or value > total:
        return None
    return value


async def _ai_title(user_id: int, session_id: int) -> str | None:
    title = await generate_title_for_session(user_id, session_id)
    return title.strip() if title else None


async def rename_session_text(
    user_id: int,
    persona_name: str,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    sessions = get_sessions(user_id, persona_name)
    if not sessions:
        return "❌ No session to rename."

    rest = args[1:]
    index: int | None = None
    title: str | None = None

    if rest:
        parsed = _parse_index(rest[0], len(sessions))
        if parsed is not None:
            index = parsed
            if len(rest) > 1:
                title = " ".join(rest[1:]).strip() or None
        else:
            title = " ".join(rest).strip() or None

    target_id = sessions[index - 1]["id"] if index else None
    label = f"#{index}" if index else "current session"

    if title is None:
        if target_id is None:
            from services import get_current_session_id

            target_id = get_current_session_id(user_id, persona_name)
            if target_id is None:
                return "❌ No current session to rename."
        title = await _ai_title(user_id, target_id)
        if not title:
            hint = f"{index} " if index else ""
            return (
                "❌ Could not generate a title — the session may be empty.\n"
                f"Try `{command_prefix}chat rename {hint}<title>`"
            )

    if rename_session(user_id, title, persona_name, session_index=index):
        return f"✅ **Renamed {label} to:** {title}"
    return "❌ Failed to rename session."
