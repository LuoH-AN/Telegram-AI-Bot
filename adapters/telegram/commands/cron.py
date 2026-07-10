"""Button-driven scheduled-task command."""

from __future__ import annotations

from telegram.constants import ChatType

from adapters.telegram.rich_text import reply_rich_text
from adapters.telegram.ux.locale import language, pick
from adapters.telegram.ux.panels import cron_panel
from domain.services.cron.trigger import run_cron_task

from .registry import CommandContext, command


@command("cron", usage="cron [run <name>]", help="manage scheduled tasks", category="Automation")
async def cron_command(ctx: CommandContext) -> str:
    lang = language(ctx.update, ctx.context)
    if ctx.update.effective_chat.type != ChatType.PRIVATE:
        return pick(lang, "请在私聊中管理定时任务。", "Manage scheduled tasks in a private chat.")
    if len(ctx.args) >= 2 and ctx.args[0].lower() == "run":
        return run_cron_task(ctx.user_id, " ".join(ctx.args[1:]), lang=lang)
    text, keyboard = cron_panel(ctx.user_id, lang)
    await reply_rich_text(ctx.message, text, reply_markup=keyboard)
    return ""
