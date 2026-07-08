"""Persona command dispatcher."""

from shared.utils.subcommands import SubContext, Subcommands

from .create import create_persona_text
from .delete import delete_persona_text
from .list import build_persona_list_text
from .prompt import update_persona_prompt_text
from .switch import switch_persona_text

_persona = Subcommands("persona", help_intro="🎭 **Persona management.**")


@_persona.subcommand("list", help="list your personas", default=True)
async def _list(subctx: SubContext) -> str:
    return build_persona_list_text(subctx.user_id, command_prefix=subctx.command_prefix)


@_persona.subcommand("switch", usage="switch <name>", help="switch to a persona")
async def _switch(subctx: SubContext) -> str:
    name = subctx.rest_text
    if not name:
        return f"**Usage:** `{subctx.command_prefix}persona switch <name>`"
    return switch_persona_text(subctx.user_id, name, command_prefix=subctx.command_prefix)


@_persona.subcommand("new", usage="new <name> [system prompt]", help="create a persona")
async def _new(subctx: SubContext) -> str:
    return create_persona_text(subctx.user_id, subctx.args, command_prefix=subctx.command_prefix)


@_persona.subcommand("delete", usage="delete <name>", help="delete a persona")
async def _delete(subctx: SubContext) -> str:
    return delete_persona_text(subctx.user_id, subctx.args, command_prefix=subctx.command_prefix)


@_persona.subcommand("prompt", "edit", usage="prompt [new prompt]", help="view/set the system prompt")
async def _prompt(subctx: SubContext) -> str:
    return update_persona_prompt_text(subctx.user_id, subctx.args, command_prefix=subctx.command_prefix)


async def run_persona_command(
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    return await _persona.dispatch(
        args,
        user_id=user_id,
        command_prefix=command_prefix,
    )
