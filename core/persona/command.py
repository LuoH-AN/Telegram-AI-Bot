"""Persona command dispatcher."""

from .create import create_persona_text
from .delete import delete_persona_text
from .list import build_persona_list_text
from .switch import switch_persona_text
from .prompt import update_persona_prompt_text


def run_persona_command(
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    if not args:
        return build_persona_list_text(user_id, command_prefix=command_prefix)

    subcmd = args[0].lower()
    if subcmd == "new":
        return create_persona_text(user_id, args, command_prefix=command_prefix)
    if subcmd == "delete":
        return delete_persona_text(user_id, args, command_prefix=command_prefix)
    if subcmd == "prompt":
        return update_persona_prompt_text(user_id, args, command_prefix=command_prefix)
    return switch_persona_text(user_id, args[0], command_prefix=command_prefix)
