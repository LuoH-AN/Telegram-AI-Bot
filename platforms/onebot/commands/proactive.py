"""Admin command to configure proactive reply per QQ group."""

from __future__ import annotations

import time

from ..proactive import (
    clear_mute,
    get_proactive_config,
    set_mute_until,
    update_proactive_config,
)


def _extract_args(ctx) -> list[str]:
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
    body = raw_text[len(prefix):].strip() if raw_text.startswith(prefix) else raw_text
    _, _, rest = body.partition(" ")
    return rest.split() if rest.strip() else []


def _format_status(cfg, prefix: str) -> str:
    state = "on" if cfg.enabled else "off"
    mute_left = max(0, int(cfg.mute_until - time.time())) if cfg.mute_until else 0
    mute_line = f"muted: {mute_left // 60}m{mute_left % 60}s remaining" if mute_left else "muted: no"
    kw = ", ".join(cfg.keywords) if cfg.keywords else "(none)"
    bl = ", ".join(cfg.blacklist) if cfg.blacklist else "(none)"
    return (
        f"Proactive reply: {state}\n"
        f"Probability: {cfg.probability:.2f}\n"
        f"{mute_line}\n"
        f"Keywords: {kw}\n"
        f"Blacklist: {bl}\n\n"
        f"Usage:\n"
        f"{prefix}proactive on|off\n"
        f"{prefix}proactive prob <0-1>\n"
        f"{prefix}proactive keywords <comma,list>\n"
        f"{prefix}proactive blacklist <comma,list>\n"
        f"{prefix}proactive mute <minutes>\n"
        f"{prefix}proactive unmute"
    )


def _parse_csv(rest: list[str]) -> list[str]:
    joined = " ".join(rest).strip()
    return [item.strip() for item in joined.split(",") if item.strip()]


async def proactive_command(ctx) -> None:
    if not ctx.is_group:
        await ctx.reply_text("This command can only be used in group chats.")
        return
    if not ctx.is_admin:
        await ctx.reply_text("Only bot admins can configure proactive reply.")
        return

    group_id = int(ctx.group_id)
    prefix = ctx.runtime.command_prefix
    args = _extract_args(ctx)
    cfg = get_proactive_config(group_id)

    if not args:
        await ctx.reply_text(_format_status(cfg, prefix))
        return

    sub = args[0].lower()
    rest = args[1:]

    if sub in {"on", "enable"}:
        update_proactive_config(group_id, enabled=True)
        await ctx.reply_text("Proactive reply enabled for this group.")
    elif sub in {"off", "disable"}:
        update_proactive_config(group_id, enabled=False)
        await ctx.reply_text("Proactive reply disabled for this group.")
    elif sub in {"prob", "probability"} and rest:
        try:
            prob = float(rest[0])
        except ValueError:
            await ctx.reply_text("Probability must be a number between 0 and 1.")
            return
        cfg = update_proactive_config(group_id, probability=prob)
        await ctx.reply_text(f"Probability set to {cfg.probability:.2f}.")
    elif sub == "keywords":
        update_proactive_config(group_id, keywords=_parse_csv(rest))
        await ctx.reply_text("Keyword list updated.")
    elif sub == "blacklist":
        update_proactive_config(group_id, blacklist=_parse_csv(rest))
        await ctx.reply_text("Blacklist updated.")
    elif sub == "mute":
        minutes = int(rest[0]) if rest and rest[0].isdigit() else 5
        until = set_mute_until(group_id, minutes)
        await ctx.reply_text(f"Muted for {minutes} minute(s) (until epoch {until}).")
    elif sub == "unmute":
        clear_mute(group_id)
        await ctx.reply_text("Mute cleared.")
    else:
        await ctx.reply_text(_format_status(cfg, prefix))
