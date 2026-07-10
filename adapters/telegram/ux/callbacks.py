"""Router for button-driven Telegram UX callbacks."""

from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from adapters.telegram.commands.settings.model import _build_model_keyboard, fetch_models
from adapters.telegram.rich_text import edit_query_rich_text, reply_rich_text
from domain.services import (
    create_session,
    delete_chat_session,
    delete_persona,
    get_current_persona_name,
    get_current_session_id,
    get_personas,
    get_sessions,
    switch_persona,
    update_user_setting,
)
from domain.services.cron.trigger import run_cron_task
from domain.services.refresh import ensure_user_state
from infrastructure.cache import cache, sync_to_database

from .locale import language, pick
from .panels import (
    confirmation,
    connection_panel,
    cron_detail,
    cron_panel,
    generation_panel,
    help_panel,
    help_topic,
    main_panel,
    personas_panel,
    sessions_panel,
    settings_panel,
    timezone_panel,
)
from .tokens import stable_token

logger = logging.getLogger(__name__)


async def _edit(query, panel) -> None:
    text, keyboard = panel
    try:
        await edit_query_rich_text(query, text, reply_markup=keyboard)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def _persist() -> None:
    await asyncio.to_thread(sync_to_database)


def _cron_task(user_id: int, token: str) -> dict | None:
    return next((task for task in cache.get_cron_tasks(user_id) if stable_token(task["name"]) == token), None)


def _action_owner(data: str, action: str) -> int | None:
    prefix = f"ux:{action}:"
    if not data.startswith(prefix):
        return None
    try:
        return int(data[len(prefix):])
    except ValueError:
        return None


def _pending_keyboard(lang: str, back: str = "ux:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "取消", "Cancel"), callback_data=back)]])


async def _ask(query, context, *, kind: str, text: str, lang: str, extra: dict | None = None, back: str = "ux:menu") -> None:
    context.user_data["ux_pending"] = {"kind": kind, **(extra or {})}
    await edit_query_rich_text(query, text, reply_markup=_pending_keyboard(lang, back))


async def _model_picker(query, context, user_id: int, lang: str) -> None:
    if not cache.get_settings(user_id).get("api_key"):
        await _edit(query, connection_panel(user_id, lang))
        return
    await edit_query_rich_text(query, pick(lang, "正在获取模型…", "Fetching models…"))
    models = await asyncio.to_thread(fetch_models, user_id)
    if not models:
        text = pick(lang, "❌ 无法获取模型，请检查 API 地址和密钥。", "❌ Could not fetch models. Check the API endpoint and key.")
        await edit_query_rich_text(query, text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ API 连接", "⬅️ API connection"), callback_data="ux:settings:connection")]]))
        return
    context.user_data["models"] = models
    current = cache.get_settings(user_id).get("model", "")
    keyboard = _build_model_keyboard(models, 0, current, lang=lang)
    await edit_query_rich_text(query, pick(lang, f"选择模型（当前：`{current}`）", f"Choose a model (current: `{current}`)"), reply_markup=keyboard)


async def ux_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    lang = language(update, context)
    user_id = update.effective_user.id
    is_stop = data == "ux:stop" or data.startswith("ux:stop:")
    is_retry = data == "ux:retry" or data.startswith("ux:retry:")

    if data == "ux:noop":
        await query.answer()
        return
    is_group = bool(update.effective_chat and update.effective_chat.type != ChatType.PRIVATE)
    if is_group and not (is_stop or is_retry):
        await query.answer(pick(lang, "请在私聊中打开交互面板。", "Open the interactive panel in a private chat."), show_alert=True)
        return
    if is_stop or is_retry:
        owner = _action_owner(data, "stop" if is_stop else "retry")
        if owner is not None and owner != user_id:
            await query.answer(
                pick(lang, "只有发起这次请求的人可以操作。", "Only the person who started this request can use this button."),
                show_alert=True,
            )
            return
        if is_group and owner is None:
            await query.answer(
                pick(lang, "这个旧按钮无法验证发起者，请重新发送请求。", "This old button cannot verify its owner. Send the request again."),
                show_alert=True,
            )
            return
    await query.answer()
    if not (is_stop or is_retry):
        await ensure_user_state(user_id)
    context.user_data.pop("ux_pending", None)

    if data.startswith("ux:lang:"):
        context.user_data["ux_language"] = data.rsplit(":", 1)[1]
        lang = language(update, context)
        await _edit(query, main_panel(user_id, lang))
        return
    if data == "ux:menu":
        await _edit(query, main_panel(user_id, lang))
        return
    if data == "ux:settings":
        await _edit(query, settings_panel(user_id, lang))
        return
    if data == "ux:settings:generation":
        await _edit(query, generation_panel(user_id, lang))
        return
    if data == "ux:settings:connection":
        await _edit(query, connection_panel(user_id, lang))
        return
    if data == "ux:settings:timezone":
        await _edit(query, timezone_panel(user_id, lang))
        return
    if data == "ux:settings:full":
        from domain.services.platform import build_settings_text

        text = build_settings_text(user_id, command_prefix="/", lang=lang)
        await edit_query_rich_text(query, text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 设置", "⬅️ Settings"), callback_data="ux:settings")]]))
        return
    if data == "ux:usage":
        from domain.services.platform import build_usage_text

        await edit_query_rich_text(query, build_usage_text(user_id, lang=lang), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 设置", "⬅️ Settings"), callback_data="ux:settings")]]))
        return
    if data == "ux:settings:model":
        await _model_picker(query, context, user_id, lang)
        return
    if data == "ux:settings:timezone_custom":
        await _ask(query, context, kind="timezone", lang=lang, back="ux:settings:timezone", text=pick(lang, "请输入 IANA 时区，例如 `Asia/Shanghai`、`Europe/Paris` 或 `UTC`。", "Send an IANA timezone such as `Asia/Shanghai`, `Europe/Paris`, or `UTC`."))
        return
    if data == "ux:settings:temperature_custom":
        await _ask(query, context, kind="temperature", lang=lang, back="ux:settings:generation", text=pick(lang, "请输入 0.0–2.0 之间的温度值。", "Send a temperature between 0.0 and 2.0."))
        return
    if data == "ux:onboard:key":
        await _ask(query, context, kind="api_key", lang=lang, back="ux:settings:connection", text=pick(lang, "🔑 请发送 API Key。\n\n收到后会立即尝试删除包含密钥的消息，并验证连接。", "🔑 Send your API key.\n\nThe message containing it will be deleted when possible, then the connection will be verified."))
        return
    if data == "ux:onboard:base_custom":
        await _ask(query, context, kind="base_url", lang=lang, back="ux:settings:connection", text=pick(lang, "请发送完整 API 地址，例如 `https://api.openai.com/v1`。", "Send the full API endpoint, for example `https://api.openai.com/v1`."))
        return
    if data == "ux:onboard:base_default":
        update_user_setting(user_id, "base_url", "https://api.openai.com/v1")
        await _persist()
        await _edit(query, connection_panel(user_id, lang))
        return
    if data == "ux:confirm:clear_key":
        await _edit(query, confirmation(pick(lang, "确定清除已保存的 API Key？", "Clear the saved API key?"), "ux:clear_key:yes", "ux:settings:connection", lang))
        return
    if data == "ux:clear_key:yes":
        update_user_setting(user_id, "api_key", "")
        await _persist()
        await _edit(query, connection_panel(user_id, lang))
        return

    if data.startswith("ux:set:reasoning:"):
        effort = data.rsplit(":", 1)[1]
        update_user_setting(user_id, "reasoning_effort", "" if effort == "clear" else effort)
        await _persist()
        await _edit(query, generation_panel(user_id, lang))
        return
    if data.startswith("ux:set:stream:"):
        update_user_setting(user_id, "stream_mode", data.rsplit(":", 1)[1])
        await _persist()
        await _edit(query, generation_panel(user_id, lang))
        return
    if data == "ux:set:thinking:toggle":
        current = bool(cache.get_settings(user_id).get("show_thinking"))
        update_user_setting(user_id, "show_thinking", not current)
        await _persist()
        await _edit(query, generation_panel(user_id, lang))
        return
    if data.startswith("ux:set:temperature:"):
        update_user_setting(user_id, "temperature", float(data.rsplit(":", 1)[1]))
        await _persist()
        await _edit(query, generation_panel(user_id, lang))
        return
    if data.startswith("ux:set:timezone:"):
        timezone_name = data[len("ux:set:timezone:"):]
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            await _edit(query, timezone_panel(user_id, lang))
            return
        update_user_setting(user_id, "timezone", timezone_name)
        await _persist()
        await _edit(query, timezone_panel(user_id, lang))
        return

    if data.startswith("ux:chat:"):
        action = data.split(":", 2)[2]
        persona = get_current_persona_name(user_id)
        if action.isdigit():
            await _edit(query, sessions_panel(user_id, lang, int(action)))
            return
        if action == "new":
            create_session(user_id, persona)
            await _persist()
            await _edit(query, sessions_panel(user_id, lang))
            return
        if action == "rename":
            session_id = get_current_session_id(user_id, persona)
            await _ask(query, context, kind="session_title", extra={"session_id": session_id}, lang=lang, back="ux:chat:0", text=pick(lang, "请输入当前会话的新标题。", "Send a new title for the current chat."))
            return
        if action.startswith("switch:"):
            session_id = int(action.split(":", 1)[1])
            session = cache.get_session_by_id(session_id)
            if session and session.get("user_id") == user_id:
                cache.set_current_session_id(user_id, session["persona_name"], session_id)
                await _persist()
            await _edit(query, sessions_panel(user_id, lang))
            return
    if data == "ux:confirm:delete_chat":
        await _edit(query, confirmation(pick(lang, "确定删除当前会话及其全部消息？", "Delete the current chat and all its messages?"), "ux:delete_chat:yes", "ux:chat:0", lang))
        return
    if data == "ux:delete_chat:yes":
        persona = get_current_persona_name(user_id)
        current = get_current_session_id(user_id, persona)
        sessions = get_sessions(user_id, persona)
        index = next((i for i, item in enumerate(sessions, 1) if item["id"] == current), None)
        if index:
            delete_chat_session(user_id, index, persona)
            await _persist()
        await _edit(query, sessions_panel(user_id, lang))
        return

    if data.startswith("ux:persona:"):
        action = data.split(":", 2)[2]
        if action.isdigit():
            await _edit(query, personas_panel(user_id, lang, int(action)))
            return
        if action == "new":
            await _ask(query, context, kind="persona_name", lang=lang, back="ux:persona:0", text=pick(lang, "请输入新角色名称。", "Send a name for the new persona."))
            return
        if action == "prompt":
            await _ask(query, context, kind="persona_prompt", lang=lang, back="ux:persona:0", text=pick(lang, "请输入当前角色的新系统提示词。", "Send the new system prompt for the current persona."))
            return
        if action.startswith("switch:"):
            token = action.split(":", 1)[1]
            personas = list(get_personas(user_id).values())
            persona = next((item for item in personas if stable_token(item["name"]) == token), None)
            if persona:
                switch_persona(user_id, persona["name"])
                await _persist()
            await _edit(query, personas_panel(user_id, lang))
            return
    if data == "ux:confirm:delete_persona":
        current = get_current_persona_name(user_id)
        if current == "default":
            await edit_query_rich_text(query, pick(lang, "默认角色不能删除。", "The default persona cannot be deleted."), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 角色", "⬅️ Personas"), callback_data="ux:persona:0")]]))
            return
        await _edit(query, confirmation(pick(lang, f"确定删除角色 `{current}` 及其会话？", f"Delete persona `{current}` and its chats?"), "ux:delete_persona:yes", "ux:persona:0", lang))
        return
    if data == "ux:delete_persona:yes":
        delete_persona(user_id, get_current_persona_name(user_id))
        await _persist()
        await _edit(query, personas_panel(user_id, lang))
        return

    if data == "ux:help":
        await _edit(query, help_panel(user_id, lang))
        return
    if data.startswith("ux:help:"):
        await _edit(query, help_topic(data.rsplit(":", 1)[1], lang))
        return

    if data == "ux:cron":
        await _edit(query, cron_panel(user_id, lang))
        return
    if data == "ux:cron:add":
        context.user_data.pop("cron_draft", None)
        await _ask(query, context, kind="cron_name", lang=lang, back="ux:cron:cancel", text=pick(lang, "请输入任务名称。", "Send a name for the scheduled task."))
        return
    if data.startswith("ux:cron:view:"):
        await _edit(query, cron_detail(user_id, data.rsplit(":", 1)[1], lang))
        return
    if data.startswith("ux:cron:run:"):
        task = _cron_task(user_id, data.rsplit(":", 1)[1])
        if task:
            await reply_rich_text(query.message, run_cron_task(user_id, task["name"], lang=lang))
        return
    if data.startswith("ux:cron:toggle:"):
        token = data.rsplit(":", 1)[1]
        task = _cron_task(user_id, token)
        if task:
            cache.update_cron_task(user_id, task["name"], enabled=not task.get("enabled", True))
            await _persist()
        await _edit(query, cron_detail(user_id, token, lang))
        return
    if data.startswith("ux:cron:delete:"):
        token = data.rsplit(":", 1)[1]
        await _edit(query, confirmation(pick(lang, "确定删除这个定时任务？", "Delete this scheduled task?"), f"ux:cron:delete_yes:{token}", f"ux:cron:view:{token}", lang))
        return
    if data.startswith("ux:cron:delete_yes:"):
        task = _cron_task(user_id, data.rsplit(":", 1)[1])
        if task:
            cache.delete_cron_task(user_id, task["name"])
            await _persist()
        await _edit(query, cron_panel(user_id, lang))
        return
    if data == "ux:cron:confirm":
        draft = context.user_data.get("cron_draft") or {}
        if all(draft.get(key) for key in ("name", "cron_expression", "prompt")):
            created = cache.add_cron_task(user_id, draft["name"], draft["cron_expression"], draft["prompt"])
            if created:
                await asyncio.to_thread(sync_to_database)
            else:
                await edit_query_rich_text(query, pick(lang, "❌ 无法创建任务：名称重复或已达到数量上限。", "❌ Could not create the task: duplicate name or task limit reached."), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 定时任务", "⬅️ Schedules"), callback_data="ux:cron")]]))
                return
        context.user_data.pop("cron_draft", None)
        context.user_data.pop("ux_pending", None)
        await _edit(query, cron_panel(user_id, lang))
        return
    if data == "ux:cron:cancel":
        context.user_data.pop("cron_draft", None)
        context.user_data.pop("ux_pending", None)
        await _edit(query, cron_panel(user_id, lang))
        return

    if is_retry:
        retry = context.user_data.get("ux_last_retry") or {}
        if not retry:
            await edit_query_rich_text(query, pick(lang, "没有可重试的请求，请重新发送消息。", "There is no request to retry. Send the message again."), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 主菜单", "⬅️ Main menu"), callback_data="ux:menu")]]))
            return
        await edit_query_rich_text(query, pick(lang, "🔄 正在重试…", "🔄 Retrying…"), reply_markup=None)
        from adapters.telegram.handlers.messages.chat.run import chat

        await chat(
            update,
            context,
            user_content=retry.get("user_content"),
            save_msg=retry.get("save_msg"),
            frozen_persona_name=retry.get("persona_name"),
            frozen_session_id=retry.get("session_id"),
            retry_existing=True,
            bot_message=query.message,
        )
        return

    if is_stop:
        from domain.services.queue import cancel_user_responses

        cancelled = cancel_user_responses(update.effective_chat.id, user_id, platform="telegram")
        if not cancelled:
            await edit_query_rich_text(query, pick(lang, "当前没有正在生成的回复。", "There is no active response to stop."), reply_markup=None)
        logger.info("user=%s stopped %d response(s) from callback", user_id, len(cancelled))
