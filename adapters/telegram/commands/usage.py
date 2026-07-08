"""/usage and /export commands."""

from __future__ import annotations

from telegram.constants import ParseMode

from domain.services import export_to_markdown, get_current_persona_name, reset_token_usage
from domain.services.platform import build_usage_text
from shared.utils.format import markdown_to_telegram_html
from shared.utils.platform import build_usage_reset_message
from shared.utils.subcommands import SubContext, Subcommands

from .registry import CommandContext, command

_usage = Subcommands("usage", help_intro="📊 **Token usage.**")


@_usage.subcommand("show", help="show token usage", default=True)
async def _show(subctx: SubContext) -> str:
    return build_usage_text(subctx.user_id)


@_usage.subcommand("reset", help="reset token usage")
async def _reset(subctx: SubContext) -> str:
    persona_name = get_current_persona_name(subctx.user_id)
    reset_token_usage(subctx.user_id, persona_name)
    return build_usage_reset_message(persona_name)


@command("usage", usage="usage [show|reset]", help="view usage", category="Settings")
async def usage_command(ctx: CommandContext) -> str:
    return await _usage.dispatch(ctx.args, user_id=ctx.user_id, command_prefix="/")


@command("export", help="export conversation", category="Chat")
async def export_command(ctx: CommandContext) -> str:
    persona_name = get_current_persona_name(ctx.user_id)
    file_buffer = export_to_markdown(ctx.user_id, persona_name)
    if file_buffer is None:
        return f"No conversation history to export in current session (persona: '{persona_name}')."
    filename = getattr(file_buffer, "name", None) or f"chat_export_{persona_name}.md"
    try:
        file_buffer.seek(0)
    except Exception:
        pass
    caption = markdown_to_telegram_html(f"Chat history export (Persona: {persona_name})") or None
    await ctx.message.reply_document(document=file_buffer, filename=filename, caption=caption, parse_mode=ParseMode.HTML)
    return ""
