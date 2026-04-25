"""Callback query handlers."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from services import get_user_settings, update_user_setting
from handlers.common import get_log_context
from handlers.commands.settings import _build_model_keyboard
from utils.platform import (
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
        await query.edit_message_text(text)


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle model selection and pagination callbacks."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data == "models_noop":
        return

    if data.startswith("models_page:"):
        page = int(data.split(":")[1])
        logger.info("%s model page %d", get_log_context(update), page)
        models = context.user_data.get("models", [])
        if not models:
            await query.edit_message_text("Session expired. Use /set model again.")
            return

        settings = get_user_settings(user_id)
        keyboard = _build_model_keyboard(models, page, settings["model"])
        await query.edit_message_reply_markup(reply_markup=keyboard)

    elif data.startswith("model:"):
        model = data.split(":", 1)[1]
        update_user_setting(user_id, "model", model)
        logger.info("%s set model = %s (callback)", get_log_context(update), model)
        await query.edit_message_text(f"Model set to: {model}")
