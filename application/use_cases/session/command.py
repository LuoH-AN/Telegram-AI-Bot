"""Chat session command dispatcher."""

from domain.services import get_current_persona_name
from shared.utils.subcommands import SubContext, Subcommands

from .create import create_session_text
from .delete import delete_session_text
from .list import build_session_list_text
from .rename import rename_session_text
from .switch import switch_session_text

_chat = Subcommands("chat", help_intro="💬 **Session management.**")


@_chat.subcommand("list", help="list your sessions", default=True)
async def _list(subctx: SubContext) -> str:
    return build_session_list_text(subctx.user_id, subctx.persona_name, command_prefix=subctx.command_prefix)


@_chat.subcommand("switch", usage="switch <number>", help="switch to a session")
async def _switch(subctx: SubContext) -> str:
    if not subctx.rest:
        return f"**Usage:** `{subctx.command_prefix}chat switch <number>`"
    return switch_session_text(subctx.user_id, subctx.persona_name, subctx.rest[0], command_prefix=subctx.command_prefix)


@_chat.subcommand("new", usage="new [title]", help="create a session")
async def _new(subctx: SubContext) -> str:
    return create_session_text(subctx.user_id, subctx.persona_name, subctx.args)


@_chat.subcommand("rename", usage="rename [number] [title]", help="rename (AI-title if omitted)")
async def _rename(subctx: SubContext) -> str:
    return await rename_session_text(subctx.user_id, subctx.persona_name, subctx.args, command_prefix=subctx.command_prefix)


@_chat.subcommand("delete", usage="delete <number>", help="delete a session")
async def _delete(subctx: SubContext) -> str:
    return delete_session_text(subctx.user_id, subctx.persona_name, subctx.args, command_prefix=subctx.command_prefix)


async def run_chat_command(
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    persona_name = get_current_persona_name(user_id)
    # Bare number is a documented switch shortcut; everything else must be a verb.
    if args and args[0].lstrip("+-").isdigit():
        args = ["switch", args[0]]
    return await _chat.dispatch(
        args,
        user_id=user_id,
        command_prefix=command_prefix,
        persona_name=persona_name,
    )
