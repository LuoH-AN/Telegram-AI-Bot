"""Multi-step private-chat input flows for the button-driven UX."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ApplicationHandlerStop, ContextTypes

from adapters.telegram.commands.settings.core import set_api_key_secure
from adapters.telegram.rich_text import telegram_html
from domain.services import (
    create_persona,
    get_personas,
    switch_persona,
    update_current_prompt,
    update_user_setting,
)
from domain.services.cron.matcher import is_valid_cron
from domain.services.cron.timezone import describe_cron, next_run_at
from infrastructure.cache import cache, sync_to_database

from .locale import language, pick
from .panels import connection_panel, personas_panel, sessions_panel, settings_panel


async def _send(message, text: str, keyboard=None):
    return await message.chat.send_message(
        telegram_html(text),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def _send_panel(message, panel):
    text, keyboard = panel
    return await _send(message, text, keyboard)


async def _persist() -> None:
    await asyncio.to_thread(sync_to_database)


def _cancel_keyboard(lang: str, callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "取消", "Cancel"), callback_data=callback)]])


async def handle_pending_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.user_data.get("ux_pending")
    if not pending:
        return
    message = update.effective_message
    if message is None or message.chat.type != ChatType.PRIVATE or not message.text:
        return

    lang = language(update, context)
    user_id = update.effective_user.id
    value = message.text.strip()
    kind = pending.get("kind")

    if kind == "api_key":
        if len(value) < 6:
            await _send(message, pick(lang, "API Key 看起来过短，请重新发送。", "That API key looks too short. Send it again."), _cancel_keyboard(lang, "ux:settings:connection"))
            raise ApplicationHandlerStop
        context.user_data.pop("ux_pending", None)
        models = await set_api_key_secure(message, user_id=user_id, value=value)
        if models:
            context.user_data["models"] = models
        raise ApplicationHandlerStop

    if kind == "base_url":
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            await _send(message, pick(lang, "请输入有效的 HTTP(S) API 地址。", "Send a valid HTTP(S) API endpoint."), _cancel_keyboard(lang, "ux:settings:connection"))
            raise ApplicationHandlerStop
        update_user_setting(user_id, "base_url", value.rstrip("/"))
        await _persist()
        context.user_data.pop("ux_pending", None)
        await _send_panel(message, connection_panel(user_id, lang))
        raise ApplicationHandlerStop

    if kind == "timezone":
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            await _send(message, pick(lang, "无效时区，请使用 `Asia/Shanghai`、`UTC` 等 IANA 名称。", "Invalid timezone. Use an IANA name such as `Asia/Shanghai` or `UTC`."), _cancel_keyboard(lang, "ux:settings:timezone"))
            raise ApplicationHandlerStop
        update_user_setting(user_id, "timezone", value)
        await _persist()
        context.user_data.pop("ux_pending", None)
        await _send_panel(message, settings_panel(user_id, lang))
        raise ApplicationHandlerStop

    if kind == "temperature":
        try:
            temperature = float(value)
        except ValueError:
            temperature = -1
        if not 0.0 <= temperature <= 2.0:
            await _send(message, pick(lang, "温度必须在 0.0–2.0 之间。", "Temperature must be between 0.0 and 2.0."), _cancel_keyboard(lang, "ux:settings:generation"))
            raise ApplicationHandlerStop
        update_user_setting(user_id, "temperature", temperature)
        await _persist()
        context.user_data.pop("ux_pending", None)
        await _send_panel(message, settings_panel(user_id, lang))
        raise ApplicationHandlerStop

    if kind == "session_title":
        title = " ".join(value.split())
        if not title:
            await _send(message, pick(lang, "标题不能为空。", "The title cannot be empty."), _cancel_keyboard(lang, "ux:chat:0"))
            raise ApplicationHandlerStop
        session_id = pending.get("session_id")
        session = cache.get_session_by_id(session_id) if session_id else None
        if session and session.get("user_id") == user_id:
            cache.update_session_title(session_id, title[:120])
            await _persist()
        context.user_data.pop("ux_pending", None)
        await _send_panel(message, sessions_panel(user_id, lang))
        raise ApplicationHandlerStop

    if kind == "persona_name":
        name = " ".join(value.split())
        if not name or len(name) > 32 or name in get_personas(user_id):
            await _send(message, pick(lang, "角色名需为 1–32 个字符且不能重复。", "Persona names must be 1–32 characters and unique."), _cancel_keyboard(lang, "ux:persona:0"))
            raise ApplicationHandlerStop
        create_persona(user_id, name)
        switch_persona(user_id, name)
        await _persist()
        context.user_data.pop("ux_pending", None)
        await _send_panel(message, personas_panel(user_id, lang))
        raise ApplicationHandlerStop

    if kind == "persona_prompt":
        update_current_prompt(user_id, value)
        await _persist()
        context.user_data.pop("ux_pending", None)
        await _send_panel(message, personas_panel(user_id, lang))
        raise ApplicationHandlerStop

    draft = context.user_data.setdefault("cron_draft", {})
    if kind == "cron_name":
        name = " ".join(value.split())
        existing = {task["name"] for task in cache.get_cron_tasks(user_id)}
        if not name or len(name) > 40 or name in existing:
            await _send(message, pick(lang, "任务名需为 1–40 个字符且不能重复。", "Task names must be 1–40 characters and unique."), _cancel_keyboard(lang, "ux:cron:cancel"))
            raise ApplicationHandlerStop
        draft["name"] = name
        context.user_data["ux_pending"] = {"kind": "cron_expression"}
        await _send(message, pick(lang, "请输入 5 段 Cron 表达式。\n例如每天 09:00：`0 9 * * *`\n每 30 分钟：`*/30 * * * *`", "Send a five-field cron expression.\nDaily at 09:00: `0 9 * * *`\nEvery 30 minutes: `*/30 * * * *`"), _cancel_keyboard(lang, "ux:cron:cancel"))
        raise ApplicationHandlerStop

    if kind == "cron_expression":
        if not is_valid_cron(value):
            await _send(message, pick(lang, "无效 Cron 表达式，请重新输入。", "Invalid cron expression. Send it again."), _cancel_keyboard(lang, "ux:cron:cancel"))
            raise ApplicationHandlerStop
        draft["cron_expression"] = value
        context.user_data["ux_pending"] = {"kind": "cron_prompt"}
        await _send(message, pick(lang, "请输入任务执行时交给 AI 的提示词。", "Send the prompt the AI should run for this task."), _cancel_keyboard(lang, "ux:cron:cancel"))
        raise ApplicationHandlerStop

    if kind == "cron_prompt":
        if not value:
            await _send(message, pick(lang, "提示词不能为空。", "The prompt cannot be empty."), _cancel_keyboard(lang, "ux:cron:cancel"))
            raise ApplicationHandlerStop
        draft["prompt"] = value
        context.user_data.pop("ux_pending", None)
        timezone = cache.get_settings(user_id).get("timezone", "Asia/Shanghai")
        next_run = next_run_at(draft["cron_expression"], timezone)
        next_text = next_run.strftime("%Y-%m-%d %H:%M") if next_run else "—"
        preview = pick(
            lang,
            f"⏰ **确认定时任务**\n\n名称：`{draft['name']}`\n计划：{describe_cron(draft['cron_expression'], lang=lang)}\n表达式：`{draft['cron_expression']}`\n时区：`{timezone}`\n下次：`{next_text}`\n\n提示词：\n{value[:800]}",
            f"⏰ **Confirm scheduled task**\n\nName: `{draft['name']}`\nSchedule: {describe_cron(draft['cron_expression'], lang=lang)}\nExpression: `{draft['cron_expression']}`\nTimezone: `{timezone}`\nNext: `{next_text}`\n\nPrompt:\n{value[:800]}",
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(pick(lang, "确认创建", "Create"), callback_data="ux:cron:confirm"),
            InlineKeyboardButton(pick(lang, "取消", "Cancel"), callback_data="ux:cron:cancel"),
        ]])
        await _send(message, preview, keyboard)
        raise ApplicationHandlerStop
