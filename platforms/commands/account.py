"""Usage/export command handlers."""

from __future__ import annotations

from pathlib import Path

from services import export_to_markdown, get_current_persona_name, reset_token_usage
from services.platform import build_usage_text
from utils.platform import build_usage_reset_message


async def usage_command(ctx, *, args: list[str]) -> None:
    user_id = ctx.local_user_id
    persona_name = get_current_persona_name(user_id)
    if args and args[0].lower() == "reset":
        reset_token_usage(user_id, persona_name)
        await ctx.reply_text(build_usage_reset_message(persona_name))
        return
    await ctx.reply_text(build_usage_text(user_id))


async def export_command(ctx) -> None:
    user_id = ctx.local_user_id
    persona_name = get_current_persona_name(user_id)
    file_buffer = export_to_markdown(user_id, persona_name)
    if file_buffer is None:
        await ctx.reply_text(f"No conversation history to export in current session (persona: '{persona_name}').")
        return
    filename = getattr(file_buffer, "name", None) or f"chat_export_{persona_name}.md"
    caption = f"Chat history export (Persona: {persona_name})"
    try:
        file_buffer.seek(0)
    except Exception:
        pass
    if hasattr(ctx, "reply_document_buffer"):
        await ctx.reply_document_buffer(file_buffer, filename=filename, caption=caption)
        return
    export_dir = Path(getattr(ctx, "export_dir", "runtime/exports"))
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / filename
    path.write_bytes(file_buffer.getvalue())
    try:
        await ctx.reply_file(path, caption=caption)
    except Exception:
        await ctx.reply_text(path.read_text("utf-8"))
