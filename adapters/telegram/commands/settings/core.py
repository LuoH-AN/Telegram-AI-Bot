"""Core `/set` key handlers."""

from __future__ import annotations

import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ChatType

from domain.services import update_user_setting
from domain.services.platform import fetch_models_for_user, mask_key
from shared.utils.platform import (
    build_api_key_verify_failed_message,
    build_api_key_verify_no_models_message,
    build_prompt_per_persona_message,
)
from adapters.telegram.rich_text import edit_rich_text, reply_rich_text, telegram_html
from adapters.telegram.ux.locale import pick
from infrastructure.cache import sync_to_database


async def set_api_key_secure(message: Message, *, user_id: int, value: str) -> list[str]:
    lang = "zh" if (getattr(message.from_user, "language_code", "") or "").lower().startswith("zh") else "en"
    if message.chat.type != ChatType.PRIVATE:
        try:
            await message.delete()
        except Exception:
            pass
        await message.chat.send_message(
            telegram_html(pick(lang, "🔒 为保护密钥，请在私聊中设置 API Key。群聊中的原消息已尝试删除。", "🔒 For safety, set your API key in a private chat. The group message was removed when possible.")),
            parse_mode="HTML",
        )
        return []

    try:
        await message.delete()
    except Exception:
        pass
    status = await message.chat.send_message(
        telegram_html(pick(lang, "🔐 密钥已接收，正在验证…", "🔐 Key received. Verifying…")),
        parse_mode="HTML",
    )
    update_user_setting(user_id, "api_key", value)
    await asyncio.to_thread(sync_to_database)
    masked = mask_key(value)
    try:
        models = await asyncio.get_running_loop().run_in_executor(None, lambda: fetch_models_for_user(user_id))
        if models:
            text = pick(lang, f"✅ API Key 已安全保存并验证，可用模型：{len(models)} 个。", f"✅ API key saved and verified. {len(models)} model(s) available.")
        else:
            text = build_api_key_verify_no_models_message(masked, lang=lang)
    except Exception:
        models = []
        text = build_api_key_verify_failed_message(masked, lang=lang)
    await edit_rich_text(
        status,
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(pick(lang, "🤖 选择模型", "🤖 Choose model"), callback_data="ux:settings:model"),
            InlineKeyboardButton(pick(lang, "⚙️ 设置", "⚙️ Settings"), callback_data="ux:settings"),
        ]]),
    )
    return models


async def handle_set_core(
    message: Message, *, user_id: int, key: str, value: str, command_prefix: str
) -> bool:
    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        await reply_rich_text(message, f"base_url set to: {value}")
        return True
    if key == "api_key":
        await set_api_key_secure(message, user_id=user_id, value=value)
        return True
    if key == "model":
        update_user_setting(user_id, "model", value)
        from infrastructure.ai.model_context import format_context_window_note

        note = format_context_window_note(value)
        await reply_rich_text(message, f"model set to: {value}" + (f"\n{note}" if note else ""))
        return True
    if key == "prompt":
        await reply_rich_text(message, build_prompt_per_persona_message(command_prefix))
        return True
    if key == "global_prompt":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "global_prompt", "")
            await reply_rich_text(message, "global_prompt cleared.\nNow personas will use their own system prompts only.")
            return True
        update_user_setting(user_id, "global_prompt", val)
        display = val[:100] + ("..." if len(val) > 100 else "")
        await reply_rich_text(
            message,
            f"global_prompt set to: {display}\n\nThis prompt will be prepended to all personas' system prompts.\n"
            f"Use {command_prefix}set global_prompt clear to remove.",
        )
        return True
    if key != "temperature":
        return False
    try:
        temp = float(value)
    except ValueError:
        await reply_rich_text(message, "Invalid temperature value")
        return True
    if not (0.0 <= temp <= 2.0):
        await reply_rich_text(message, "Temperature must be between 0.0 and 2.0")
        return True
    update_user_setting(user_id, "temperature", temp)
    await reply_rich_text(message, f"temperature set to: {temp}")
    return True
