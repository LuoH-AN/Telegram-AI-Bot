"""/usage and /export commands."""

from __future__ import annotations

from telegram.constants import ParseMode

from domain.services import export_to_markdown, get_current_persona_name, reset_token_usage
from domain.services.platform import build_usage_text
from shared.utils.format import markdown_to_telegram_html
from shared.utils.platform import build_usage_reset_message

from .registry import CommandContext, command


@command("usage", usage="usage [reset]", help="view usage", category="Settings")
async def usage_command(ctx: CommandContext) -> str:
    persona_name = get_current_persona_name(ctx.user_id)
    if ctx.subcommand == "reset":
        reset_token_usage(ctx.user_id, persona_name)
        return build_usage_reset_message(persona_name)
    return build_usage_text(ctx.user_id)


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
