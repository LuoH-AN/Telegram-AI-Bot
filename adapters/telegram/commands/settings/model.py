"""Model list helpers for /set model interaction."""

from __future__ import annotations

import asyncio
import logging
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from adapters.telegram.rich_text import edit_rich_text, reply_rich_text
from infrastructure.ai import get_ai_client
from infrastructure.config import MODELS_PER_PAGE
from domain.services import get_user_settings, has_api_key
from shared.utils.platform import build_api_key_required_message

logger = logging.getLogger(__name__)


def fetch_models(user_id: int) -> list[str]:
    try:
        return get_ai_client(user_id).list_models()
    except Exception:
        logger.exception("Failed to fetch models")
        return []


def _build_model_keyboard(models: list[str], page: int, current_model: str) -> InlineKeyboardMarkup:
    total_pages = math.ceil(len(models) / MODELS_PER_PAGE)
    start = page * MODELS_PER_PAGE
    end = start + MODELS_PER_PAGE
    page_models = models[start:end]
    keyboard = [
        [InlineKeyboardButton(f"{'* ' if model == current_model else ''}{model}", callback_data=f"model:{model}")]
        for model in page_models
    ]

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("< Prev", callback_data=f"models_page:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="models_noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next >", callback_data=f"models_page:{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    return InlineKeyboardMarkup(keyboard)


async def show_model_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    message = update.effective_message
    if not has_api_key(user_id):
        await reply_rich_text(message, build_api_key_required_message("/"))
        return

    msg = await reply_rich_text(message, "Fetching models...")
    models = await asyncio.get_event_loop().run_in_executor(None, lambda: fetch_models(user_id))
    if not models:
        await edit_rich_text(msg, "Failed to fetch models. Check your API key and base_url.")
        return

    context.user_data["models"] = models
    keyboard = _build_model_keyboard(models, page, settings["model"])
    await edit_rich_text(msg, f"Select a model (current: {settings['model']}):", reply_markup=keyboard)
