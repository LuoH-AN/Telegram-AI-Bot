"""Callback query handlers."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from adapters.telegram.rich_text import edit_query_rich_text
from domain.services import get_user_settings, update_user_setting
from adapters.telegram.commands.settings import _build_model_keyboard
from adapters.telegram.handlers.common import get_log_context
from adapters.telegram.ux.locale import language, pick
from domain.services.refresh import ensure_user_state
from infrastructure.cache import sync_to_database
from shared.utils.platform import (
    build_advanced_help_section,
    build_memory_help_section,
    build_persona_help_section,
    build_settings_help_section,
)

logger = logging.getLogger(__name__)

HELP_SECTIONS = {
    "help:personas": build_persona_help_section("/"),
    "help:settings": build_settings_help_section("/"),
    "help:memory": build_memory_help_section("/"),
    "help:advanced": build_advanced_help_section("/"),
}


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle help section callbacks."""
    query = update.callback_query
    await query.answer()

    text = HELP_SECTIONS.get(query.data)
    if text:
        await edit_query_rich_text(query, text)


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle model selection and pagination callbacks."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data
    await ensure_user_state(user_id)

    if data == "models_noop":
        return

    if data.startswith("models_page:"):
        page = int(data.split(":")[1])
        logger.info("%s model page %d", get_log_context(update), page)
        models = context.user_data.get("models", [])
        if not models:
            await edit_query_rich_text(query, "Session expired. Use /set model again.")
            return

        settings = get_user_settings(user_id)
        lang = language(update, context)
        keyboard = _build_model_keyboard(models, page, settings["model"], lang=lang)
        await query.edit_message_reply_markup(reply_markup=keyboard)

    elif data.startswith("model:"):
        if data.startswith("model:index:"):
            models = context.user_data.get("models", [])
            try:
                model = models[int(data.rsplit(":", 1)[1])]
            except (IndexError, TypeError, ValueError):
                await edit_query_rich_text(
                    query,
                    pick(language(update, context), "模型列表已过期，请重新打开模型选择器。", "The model list expired. Open the model picker again."),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            pick(language(update, context), "🤖 重新选择", "🤖 Choose again"),
                            callback_data="ux:settings:model",
                        )
                    ]]),
                )
                return
        else:
            model = data.split(":", 1)[1]
        update_user_setting(user_id, "model", model)
        await asyncio.to_thread(sync_to_database)
        logger.info("%s set model = %s (callback)", get_log_context(update), model)
        from infrastructure.ai.model_context import format_context_window_note

        note = format_context_window_note(model)
        await edit_query_rich_text(
            query,
            pick(language(update, context), f"模型已设置为：`{model}`", f"Model set to: `{model}`") + (f"\n{note}" if note else ""),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(language(update, context), "⬅️ 设置", "⬅️ Settings"), callback_data="ux:settings")]]),
        )
