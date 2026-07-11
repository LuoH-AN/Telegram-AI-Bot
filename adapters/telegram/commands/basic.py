"""/start, /help, /clear commands."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType

from adapters.telegram.rich_text import reply_rich_text
from adapters.telegram.ux.locale import language, pick
from adapters.telegram.ux.panels import help_panel, main_panel
from domain.services import (
    clear_conversation,
    ensure_session,
    get_current_persona_name,
    reset_token_usage,
)
from shared.utils.platform import (
    build_help_message,
)

from .registry import CATEGORY_TITLES, CommandContext, command, grouped_commands


@command("start", help="show welcome message", category="Chat")
async def start_command(ctx: CommandContext) -> str:
    lang = language(ctx.update, ctx.context)
    if ctx.update.effective_chat.type != ChatType.PRIVATE:
        username = ctx.context.bot.username
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(pick(lang, "🔒 在私聊中打开", "🔒 Open private chat"), url=f"https://t.me/{username}?start=setup")
        ]])
        await reply_rich_text(ctx.message, pick(lang, "为保护 API Key 和个人设置，请在私聊中完成配置。", "For API-key and settings privacy, finish setup in a private chat."), reply_markup=keyboard)
        return ""
    text, keyboard = main_panel(ctx.user_id, lang)
    await reply_rich_text(ctx.message, text, reply_markup=keyboard)
    return ""


@command("help", help="show this help", category="Chat", refresh_state=False)
async def help_command(ctx: CommandContext) -> str:
    if ctx.update.effective_chat.type == ChatType.PRIVATE:
        text, keyboard = help_panel(ctx.user_id, language(ctx.update, ctx.context))
        await reply_rich_text(ctx.message, text, reply_markup=keyboard)
        return ""
    groups = [(CATEGORY_TITLES.get(cat, cat), [(c.display_usage, c.help) for c in cmds]) for cat, cmds in grouped_commands(ctx.user_id)]
    return build_help_message("/", groups)


@command("cancel", help="cancel the current input flow", category="Chat", refresh_state=False)
async def cancel_command(ctx: CommandContext) -> str:
    lang = language(ctx.update, ctx.context)
    pending = ctx.context.user_data.pop("ux_pending", None)
    ctx.context.user_data.pop("cron_draft", None)
    if pending:
        return pick(lang, "✅ 已取消当前输入操作。你的下一条消息会正常发送给 AI。", "✅ Input cancelled. Your next message will be sent to the AI normally.")
    return pick(lang, "当前没有等待输入的操作。", "There is no active input flow to cancel.")


@command("clear", help="clear conversation", category="Chat")
async def clear_command(ctx: CommandContext) -> str:
    persona_name = get_current_persona_name(ctx.user_id)
    clear_conversation(ensure_session(ctx.user_id, persona_name))
    reset_token_usage(ctx.user_id)
    return f"Conversation cleared and usage reset for persona '{persona_name}'."
