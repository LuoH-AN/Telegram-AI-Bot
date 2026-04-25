"""Chat session command dispatcher."""

from services import get_current_persona_name

from .create import create_session_text
from .delete import delete_session_text
from .list import build_session_list_text
from .rename import rename_session_text
from .switch import switch_session_text


def run_chat_command(
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    persona_name = get_current_persona_name(user_id)
    if not args:
        return build_session_list_text(
            user_id,
            persona_name,
            command_prefix=command_prefix,
        )

    subcmd = args[0].lower()
    if subcmd == "new":
        return create_session_text(user_id, persona_name, args)
    if subcmd == "rename":
        return rename_session_text(
            user_id,
            persona_name,
            args,
            command_prefix=command_prefix,
        )
    if subcmd == "delete":
        return delete_session_text(
            user_id,
            persona_name,
            args,
            command_prefix=command_prefix,
        )
    return switch_session_text(
        user_id,
        persona_name,
        subcmd,
        command_prefix=command_prefix,
    )
