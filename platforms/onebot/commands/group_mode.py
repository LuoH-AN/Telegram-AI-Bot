"""Group mode command handler for OneBot/QQ."""

from __future__ import annotations

from ..group_config import get_group_mode, set_group_mode


async def groupmode_command(ctx) -> None:
    if not ctx.is_group:
        await ctx.reply_text("This command can only be used in group chats.")
        return

    if not ctx.is_admin:
        await ctx.reply_text("Only bot admins can change group mode.")
        return

    group_id = int(ctx.group_id)
    current = get_group_mode(group_id)
    mode_label = "共享模式" if current == "shared" else "独立模式"

    text_parts = ctx.raw_event.get("message", [])
    if isinstance(text_parts, list):
        raw_text = "".join(
            seg.get("data", {}).get("text", "")
            for seg in text_parts
            if seg.get("type") == "text"
        )
    else:
        raw_text = str(text_parts)

    prefix = ctx.runtime.command_prefix
    cmd_body = raw_text[len(prefix):].strip() if raw_text.startswith(prefix) else raw_text
    _, _, rest = cmd_body.partition(" ")
    args = rest.strip().lower() if rest else ""

    if not args:
        await ctx.reply_text(f"Current group mode: {mode_label}\n\nUsage:\n{prefix}groupmode shared\n{prefix}groupmode individual")
        return

    if args == "shared":
        if current == "shared":
            await ctx.reply_text("Already in shared mode.")
            return
        set_group_mode(group_id, "shared")
        await ctx.reply_text("Group mode switched to: 共享模式 (Shared)\nAll members now share the same conversation context.")
    elif args == "individual":
        if current == "individual":
            await ctx.reply_text("Already in individual mode.")
            return
        set_group_mode(group_id, "individual")
        await ctx.reply_text("Group mode switched to: 独立模式 (Individual)\nEach member now has their own conversation context.")
    else:
        await ctx.reply_text(f"Unknown mode: {args}\nValid modes: shared, individual")
