"""Model picker UI and provider-prefixed model `/set` handlers."""

from __future__ import annotations

import asyncio
import logging
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from adapters.telegram.rich_text import edit_rich_text, reply_rich_text
from adapters.telegram.ux.locale import language, pick
from domain.services import get_user_settings, has_api_key, update_user_setting
from infrastructure.ai import get_ai_client
from infrastructure.config import MODELS_PER_PAGE
from shared.utils.platform import build_api_key_required_message, build_provider_save_hint_message

logger = logging.getLogger(__name__)


def fetch_models(user_id: int) -> list[str]:
    try:
        return get_ai_client(user_id).list_models()
    except Exception:
        logger.exception("Failed to fetch models")
        return []


def _build_model_keyboard(
    models: list[str],
    page: int,
    current_model: str,
    *,
    back_callback: str = "ux:settings",
    lang: str = "en",
) -> InlineKeyboardMarkup:
    total_pages = max(1, math.ceil(len(models) / MODELS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * MODELS_PER_PAGE
    end = start + MODELS_PER_PAGE
    page_models = models[start:end]
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'* ' if model == current_model else ''}{model[:48]}{'…' if len(model) > 48 else ''}",
                callback_data=f"model:index:{start + offset}",
            )
        ]
        for offset, model in enumerate(page_models)
    ]

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("< 上一页" if lang == "zh" else "< Prev", callback_data=f"models_page:{page - 1}")
        )
    nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="models_noop"))
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("下一页 >" if lang == "zh" else "Next >", callback_data=f"models_page:{page + 1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    if back_callback:
        keyboard.append([
            InlineKeyboardButton("⬅️ 设置" if lang == "zh" else "⬅️ Settings", callback_data=back_callback)
        ])
    return InlineKeyboardMarkup(keyboard)


async def show_model_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    message = update.effective_message
    lang = language(update, context)
    if not has_api_key(user_id):
        await reply_rich_text(message, build_api_key_required_message("/"))
        return

    msg = await reply_rich_text(message, pick(lang, "正在获取模型…", "Fetching models…"))
    models = await asyncio.get_event_loop().run_in_executor(None, lambda: fetch_models(user_id))
    if not models:
        await edit_rich_text(msg, pick(lang, "无法获取模型，请检查 API Key 和 API 地址。", "Failed to fetch models. Check your API key and base_url."))
        return

    context.user_data["models"] = models
    keyboard = _build_model_keyboard(models, page, settings["model"], lang=lang)
    await edit_rich_text(
        msg,
        pick(lang, f"选择模型（当前：`{settings['model']}`）", f"Select a model (current: `{settings['model']}`)"),
        reply_markup=keyboard,
    )


async def handle_specialized_model_set(
    message: Message, *, user_id: int, settings: dict, key: str, value: str, command_prefix: str
) -> bool:
    val = value.strip()
    if not val or val.lower() in {"off", "clear", "none"}:
        update_user_setting(user_id, key, "")
        await reply_rich_text(message, f"{key} cleared (will use current provider + model)")
        return True
    update_user_setting(user_id, key, val)
    if ":" not in val:
        await reply_rich_text(message, f"{key} set to: {val}\n(uses current provider's API)")
        return True
    provider, model = val.split(":", 1)
    presets = settings.get("api_presets", {})
    found = any(name.lower() == provider.lower() for name in presets)
    if found:
        await reply_rich_text(message, f"{key} set to: {val}\nProvider: {provider} | Model: {model}")
        return True
    available = ", ".join(presets.keys()) if presets else "(none)"
    await reply_rich_text(
        message,
        f"{key} set to: {val}\nProvider '{provider}' not found in presets.\n"
        f"Available: {available}\n{build_provider_save_hint_message(command_prefix)}",
    )
    return True
