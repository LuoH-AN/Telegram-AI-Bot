"""/start, /help, /clear commands."""

from __future__ import annotations

from domain.services import (
    clear_conversation,
    ensure_session,
    get_current_persona_name,
    has_api_key,
    reset_token_usage,
)
from shared.utils.platform import (
    build_help_message,
    build_start_message_missing_api,
    build_start_message_returning,
)

from .registry import CommandContext, all_commands, command


@command("start", help="show welcome message")
async def start_command(ctx: CommandContext) -> str:
    if not has_api_key(ctx.user_id):
        return build_start_message_missing_api("/")
    return build_start_message_returning(get_current_persona_name(ctx.user_id), "/")


@command("help", help="show this help", refresh_state=False)
async def help_command(ctx: CommandContext) -> str:
    commands = [(c.display_usage, c.help) for c in all_commands()]
    return build_help_message("/", commands)


@command("clear", help="clear conversation")
async def clear_command(ctx: CommandContext) -> str:
    persona_name = get_current_persona_name(ctx.user_id)
    clear_conversation(ensure_session(ctx.user_id, persona_name))
    reset_token_usage(ctx.user_id)
    return f"Conversation cleared and usage reset for persona '{persona_name}'."
