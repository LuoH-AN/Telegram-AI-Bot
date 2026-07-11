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
    add_memory,
    clear_conversation,
    clear_memories,
    create_session,
    delete_memory,
    delete_chat_session,
    delete_persona,
    ensure_session,
    export_to_markdown,
    get_current_persona_name,
    get_current_session_id,
    get_personas,
    get_sessions,
    reset_token_usage,
    run_hot_update,
    run_safe_restart,
    schedule_process_restart,
    set_token_limit,
    switch_persona,
    update_persona_prompt,
    update_user_setting,
)
from domain.services.cron.trigger import run_cron_task
from domain.services.refresh import ensure_user_state
from infrastructure.cache import cache, sync_to_database
from infrastructure.ai import create_openai_client
from infrastructure.config import is_admin, normalize_telegram_busy_mode, normalize_telegram_tool_progress
from infrastructure.tools.skills.manager import get_skill_manager

from .locale import language, pick
from .panels import (
    advanced_settings_panel,
    admin_panel,
    CRON_PRESETS,
    confirmation,
    connection_panel,
    cron_detail,
    cron_panel,
    cron_schedule_panel,
    generation_panel,
    delivery_panel,
    model_generation_panel,
    feature_panel,
    help_panel,
    help_topic,
    main_panel,
    memory_detail,
    memory_panel,
    persona_detail,
    personas_panel,
    provider_detail,
    providers_panel,
    skill_detail,
    skills_panel,
    sessions_panel,
    session_detail,
    settings_panel,
    specialized_model_keyboard,
    specialized_model_source_panel,
    timezone_panel,
    token_limit_panel,
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


def _provider(user_id: int, token: str) -> tuple[str, dict] | None:
    presets = cache.get_settings(user_id).get("api_presets", {}) or {}
    return next(((name, preset) for name, preset in presets.items() if stable_token(name) == token), None)


def _skill(user_id: int, token: str):
    manager = get_skill_manager()
    return next((skill for skill in manager.list_manifests(user_id) if stable_token(skill.name) == token), None)


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
        await edit_query_rich_text(query, text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 模型服务连接", "⬅️ Model service"), callback_data="ux:settings:connection")]]))
        return
    context.user_data["models"] = models
    current = cache.get_settings(user_id).get("model", "")
    keyboard = _build_model_keyboard(models, 0, current, lang=lang)
    await edit_query_rich_text(
        query,
        pick(
            lang,
            f"🤖 **选择对话模型**\n\n当前模型：`{current}`\n列表来自当前模型服务；选择模型不会更改 API 地址或 API Key。",
            f"🤖 **Choose a chat model**\n\nCurrent model: `{current}`\nThis list comes from the active model service. Choosing a model does not change the endpoint or API key.",
        ),
        reply_markup=keyboard,
    )


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
    if data.startswith("ux:admin") and not is_admin(user_id):
        await query.answer(pick(lang, "此操作仅限机器人管理员。", "This action is restricted to bot administrators."), show_alert=True)
        return
    if data == "ux:skill:install" and not is_admin(user_id):
        await query.answer(pick(lang, "只有管理员可以安装技能。", "Only administrators can install skills."), show_alert=True)
        return
    await query.answer()
    if not (is_stop or is_retry):
        await ensure_user_state(user_id)
    context.user_data.pop("ux_pending", None)

    if data.startswith("ux:lang:"):
        selected_language = data.rsplit(":", 1)[1]
        context.user_data["ux_language"] = selected_language
        update_user_setting(user_id, "ux_language", selected_language)
        await _persist()
        lang = language(update, context)
        await _edit(query, main_panel(user_id, lang))
        return
    if data == "ux:menu":
        await _edit(query, main_panel(user_id, lang))
        return
    if data == "ux:settings":
        await _edit(query, settings_panel(user_id, lang))
        return
    if data == "ux:features":
        await _edit(query, feature_panel(user_id, lang))
        return
    if data == "ux:settings:generation":
        await _edit(query, generation_panel(user_id, lang))
        return
    if data == "ux:settings:model_generation":
        await _edit(query, model_generation_panel(user_id, lang))
        return
    if data == "ux:settings:delivery":
        await _edit(query, delivery_panel(user_id, lang))
        return
    if data == "ux:settings:connection":
        await _edit(query, connection_panel(user_id, lang))
        return
    if data == "ux:settings:advanced":
        await _edit(query, advanced_settings_panel(user_id, lang))
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
    if data == "ux:settings:connection_test":
        if not cache.get_settings(user_id).get("api_key"):
            await _edit(query, connection_panel(user_id, lang))
            return
        await edit_query_rich_text(query, pick(lang, "🧪 正在测试模型服务连接…", "🧪 Testing the model service connection…"))
        models = await asyncio.to_thread(fetch_models, user_id)
        if not models:
            await edit_query_rich_text(
                query,
                pick(
                    lang,
                    "❌ **连接测试失败**\n\n服务没有返回模型列表。请检查 API 地址、API Key，以及服务是否兼容 OpenAI API。",
                    "❌ **Connection test failed**\n\nThe service returned no model list. Check the endpoint, API key, and OpenAI API compatibility.",
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(pick(lang, "⬅️ 返回模型服务连接", "⬅️ Back to model service"), callback_data="ux:settings:connection")
                ]]),
            )
            return
        context.user_data["models"] = models
        await edit_query_rich_text(
            query,
            pick(lang, f"✅ **连接正常**\n\n成功获取 {len(models)} 个模型。", f"✅ **Connection successful**\n\nReceived {len(models)} model(s)."),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(pick(lang, "🤖 选择模型", "🤖 Choose model"), callback_data="ux:settings:model"),
                InlineKeyboardButton(pick(lang, "⬅️ 返回连接", "⬅️ Back"), callback_data="ux:settings:connection"),
            ]]),
        )
        return
    if data == "ux:settings:timezone_custom":
        await _ask(query, context, kind="timezone", lang=lang, back="ux:settings:timezone", text=pick(lang, "请输入 IANA 时区，例如 `Asia/Shanghai`、`Europe/Paris` 或 `UTC`。", "Send an IANA timezone such as `Asia/Shanghai`, `Europe/Paris`, or `UTC`."))
        return
    if data == "ux:settings:temperature_custom":
        await _ask(query, context, kind="temperature", lang=lang, back="ux:settings:model_generation", text=pick(lang, "你正在设置模型温度。下一条消息不会发送给 AI。\n\n请输入 0.0–2.0 之间的数值，或使用 /cancel 取消。", "You are setting model temperature. Your next message will not be sent to the AI.\n\nSend a value between 0.0 and 2.0, or use /cancel to stop."))
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

    if data == "ux:providers":
        await _edit(query, providers_panel(user_id, lang))
        return
    if data == "ux:provider:save":
        if not cache.get_settings(user_id).get("api_key"):
            await edit_query_rich_text(
                query,
                pick(lang, "保存模型服务前，请先设置并验证 API Key。", "Set and verify an API key before saving a model service."),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(pick(lang, "🔑 设置 API Key", "🔑 Set API key"), callback_data="ux:onboard:key"),
                    InlineKeyboardButton(pick(lang, "⬅️ 返回", "⬅️ Back"), callback_data="ux:providers"),
                ]]),
            )
            return
        await _ask(
            query,
            context,
            kind="provider_name",
            lang=lang,
            back="ux:providers",
            text=pick(lang, "请输入这个模型服务的保存名称，例如 `工作 OpenAI` 或 `本地模型`。", "Enter a name for this model service, such as `Work OpenAI` or `Local model`."),
        )
        return
    if data.startswith("ux:provider:view:"):
        await _edit(query, provider_detail(user_id, data.rsplit(":", 1)[1], lang))
        return
    if data.startswith("ux:provider:load:"):
        token = data.rsplit(":", 1)[1]
        match = _provider(user_id, token)
        if match:
            _, preset = match
            update_user_setting(user_id, "base_url", preset.get("base_url", ""))
            update_user_setting(user_id, "api_key", preset.get("api_key", ""))
            update_user_setting(user_id, "model", preset.get("model", ""))
            await _persist()
        await _edit(query, provider_detail(user_id, token, lang))
        return
    if data.startswith("ux:provider:delete:"):
        token = data.rsplit(":", 1)[1]
        match = _provider(user_id, token)
        name = match[0] if match else ""
        await _edit(
            query,
            confirmation(
                pick(lang, f"确定删除保存的模型服务 `{name}`？当前正在使用的连接不会被清除。", f"Delete saved model service `{name}`? Your active connection will not be cleared."),
                f"ux:provider:delete_yes:{token}",
                f"ux:provider:view:{token}",
                lang,
            ),
        )
        return
    if data.startswith("ux:provider:delete_yes:"):
        token = data.rsplit(":", 1)[1]
        match = _provider(user_id, token)
        if match:
            name, _ = match
            presets = dict(cache.get_settings(user_id).get("api_presets", {}) or {})
            presets.pop(name, None)
            update_user_setting(user_id, "api_presets", presets)
            await _persist()
        await _edit(query, providers_panel(user_id, lang))
        return

    if data == "ux:advanced:global_prompt":
        await _ask(
            query,
            context,
            kind="global_prompt",
            lang=lang,
            back="ux:settings:advanced",
            text=pick(lang, "请输入全局提示词。它会放在所有角色提示词之前，并影响每次对话。", "Enter the global prompt. It is prepended to every persona prompt and affects every chat."),
        )
        return
    if data == "ux:advanced:global_prompt_clear":
        update_user_setting(user_id, "global_prompt", "")
        await _persist()
        await _edit(query, advanced_settings_panel(user_id, lang))
        return
    if data in {"ux:advanced:title_model", "ux:advanced:cron_model"}:
        target = "title" if data.endswith("title_model") else "cron"
        await _edit(query, specialized_model_source_panel(user_id, target, lang))
        return
    if data == "ux:advanced:models_current":
        update_user_setting(user_id, "title_model", "")
        update_user_setting(user_id, "cron_model", "")
        await _persist()
        await _edit(query, advanced_settings_panel(user_id, lang))
        return
    if data == "ux:advanced:token_limit":
        await _edit(query, token_limit_panel(user_id, lang))
        return
    if data == "ux:advanced:token_limit_custom":
        await _ask(
            query,
            context,
            kind="token_limit",
            lang=lang,
            back="ux:settings:advanced",
            text=pick(lang, "请输入当前角色的 Token 限额（非负整数）。输入 `0` 表示不限。", "Enter the token limit for the current persona (a non-negative integer). Use `0` for unlimited."),
        )
        return
    if data.startswith("ux:set:token_limit:"):
        limit = int(data.rsplit(":", 1)[1])
        set_token_limit(user_id, limit, get_current_persona_name(user_id))
        await _persist()
        await _edit(query, token_limit_panel(user_id, lang))
        return
    if data == "ux:advanced:token_limit_clear":
        set_token_limit(user_id, 0, get_current_persona_name(user_id))
        await _persist()
        await _edit(query, advanced_settings_panel(user_id, lang))
        return

    if data.startswith("ux:smodel:"):
        parts = data.split(":")
        if len(parts) >= 4 and parts[2] in {"title", "cron"} and parts[3] == "current":
            key = "title_model" if parts[2] == "title" else "cron_model"
            update_user_setting(user_id, key, "")
            await _persist()
            await _edit(query, advanced_settings_panel(user_id, lang))
            return
        if len(parts) >= 5 and parts[2] in {"title", "cron"} and parts[3] == "source":
            target = parts[2]
            source = parts[4]
            settings = cache.get_settings(user_id)
            provider_name = None
            if source == "current":
                api_key = settings.get("api_key", "")
                base_url = settings.get("base_url", "")
                fallback_model = settings.get("model", "")
                source_label = pick(lang, "当前模型服务", "current model service")
            else:
                match = _provider(user_id, source)
                if not match:
                    await _edit(query, specialized_model_source_panel(user_id, target, lang))
                    return
                provider_name, preset = match
                api_key = preset.get("api_key", "")
                base_url = preset.get("base_url", "")
                fallback_model = preset.get("model", "")
                source_label = provider_name
            await edit_query_rich_text(query, pick(lang, f"正在从 `{source_label}` 获取模型列表…", f"Fetching models from `{source_label}`…"))
            if source == "current":
                models = await asyncio.to_thread(fetch_models, user_id)
            else:
                def _list_models():
                    return create_openai_client(api_key=api_key, base_url=base_url, log_context=f"[user={user_id} picker]").list_models()

                try:
                    models = await asyncio.to_thread(_list_models)
                except Exception:
                    models = []
            models = list(dict.fromkeys(model for model in models if model))
            context.user_data["special_model_picker"] = {
                "target": target,
                "provider_name": provider_name,
                "models": models,
                "fallback_model": fallback_model,
                "source_label": source_label,
            }
            if not models:
                rows = []
                if fallback_model:
                    rows.append([InlineKeyboardButton(
                        pick(lang, f"✅ 使用已保存模型：{fallback_model[:28]}", f"✅ Use saved model: {fallback_model[:28]}"),
                        callback_data="ux:smodel:fallback",
                    )])
                rows.append([InlineKeyboardButton(
                    pick(lang, "⬅️ 重新选择模型服务", "⬅️ Choose another service"),
                    callback_data=f"ux:advanced:{'title_model' if target == 'title' else 'cron_model'}",
                )])
                await edit_query_rich_text(
                    query,
                    pick(lang, "无法获取模型列表。你仍可使用该保存项中记录的模型。", "Could not fetch the model list. You can still use the model stored in this saved service."),
                    reply_markup=InlineKeyboardMarkup(rows),
                )
                return
            selected = fallback_model
            await edit_query_rich_text(
                query,
                pick(lang, f"🤖 从 `{source_label}` 选择模型", f"🤖 Choose a model from `{source_label}`"),
                reply_markup=specialized_model_keyboard(models, 0, selected, target=target, lang=lang),
            )
            return
        if len(parts) >= 4 and parts[2] == "page":
            picker = context.user_data.get("special_model_picker") or {}
            models = picker.get("models") or []
            target = picker.get("target")
            if not models or target not in {"title", "cron"}:
                await _edit(query, advanced_settings_panel(user_id, lang))
                return
            page = int(parts[3])
            await query.edit_message_reply_markup(reply_markup=specialized_model_keyboard(
                models,
                page,
                picker.get("fallback_model", ""),
                target=target,
                lang=lang,
            ))
            return
        if len(parts) >= 4 and parts[2] == "pick":
            picker = context.user_data.get("special_model_picker") or {}
            models = picker.get("models") or []
            try:
                model = models[int(parts[3])]
            except (IndexError, TypeError, ValueError):
                await _edit(query, advanced_settings_panel(user_id, lang))
                return
            target = picker.get("target")
            key = "title_model" if target == "title" else "cron_model"
            provider_name = picker.get("provider_name")
            value = f"{provider_name}:{model}" if provider_name else model
            update_user_setting(user_id, key, value)
            await _persist()
            context.user_data.pop("special_model_picker", None)
            await _edit(query, advanced_settings_panel(user_id, lang))
            return
        if len(parts) >= 3 and parts[2] == "fallback":
            picker = context.user_data.get("special_model_picker") or {}
            model = picker.get("fallback_model", "")
            target = picker.get("target")
            if model and target in {"title", "cron"}:
                key = "title_model" if target == "title" else "cron_model"
                provider_name = picker.get("provider_name")
                value = f"{provider_name}:{model}" if provider_name else model
                update_user_setting(user_id, key, value)
                await _persist()
            context.user_data.pop("special_model_picker", None)
            await _edit(query, advanced_settings_panel(user_id, lang))
            return

    if data == "ux:memory":
        await _edit(query, memory_panel(user_id, lang))
        return
    if data.startswith("ux:memory:page:"):
        await _edit(query, memory_panel(user_id, lang, int(data.rsplit(":", 1)[1])))
        return
    if data.startswith("ux:memory:view:"):
        await _edit(query, memory_detail(user_id, int(data.rsplit(":", 1)[1]), lang))
        return
    if data == "ux:memory:add":
        await _ask(
            query,
            context,
            kind="memory_content",
            lang=lang,
            back="ux:memory",
            text=pick(
                lang,
                "请输入需要长期记住的内容，例如稳定偏好或长期项目约束。\n\n请勿发送密码、API Key 或临时任务。",
                "Enter something worth remembering long-term, such as a stable preference or project constraint.\n\nDo not send passwords, API keys, or temporary tasks.",
            ),
        )
        return
    if data.startswith("ux:memory:delete:"):
        index = data.rsplit(":", 1)[1]
        await _edit(
            query,
            confirmation(
                pick(lang, f"确定删除第 {index} 条长期记忆？", f"Delete long-term memory #{index}?"),
                f"ux:memory:delete_yes:{index}",
                "ux:memory",
                lang,
            ),
        )
        return
    if data.startswith("ux:memory:delete_yes:"):
        try:
            index = int(data.rsplit(":", 1)[1])
        except ValueError:
            index = 0
        if index > 0:
            delete_memory(user_id, index)
            await _persist()
        await _edit(query, memory_panel(user_id, lang))
        return
    if data == "ux:memory:clear":
        await _edit(
            query,
            confirmation(
                pick(lang, "确定清空全部长期记忆？此操作无法撤销。", "Clear all long-term memories? This cannot be undone."),
                "ux:memory:clear_yes",
                "ux:memory",
                lang,
            ),
        )
        return
    if data == "ux:memory:clear_yes":
        clear_memories(user_id)
        await _persist()
        await _edit(query, memory_panel(user_id, lang))
        return

    if data == "ux:skills":
        await _edit(query, skills_panel(user_id, lang))
        return
    if data.startswith("ux:skills:page:"):
        await _edit(query, skills_panel(user_id, lang, int(data.rsplit(":", 1)[1])))
        return
    if data == "ux:skill:install":
        await _ask(
            query,
            context,
            kind="skill_source",
            lang=lang,
            back="ux:skills",
            text=pick(lang, "请输入技能的 GitHub URL、`owner/repo` 或本地目录。", "Enter a GitHub URL, `owner/repo`, or local directory for the skill."),
        )
        return
    if data.startswith("ux:skill:view:"):
        await _edit(query, skill_detail(user_id, data.rsplit(":", 1)[1], lang))
        return
    if data.startswith("ux:skill:toggle:"):
        token = data.rsplit(":", 1)[1]
        skill = _skill(user_id, token)
        if skill:
            manager = get_skill_manager()
            enabled = manager.is_enabled(skill.name, user_id)
            await asyncio.to_thread(manager.set_user_enabled, user_id, skill.name, not enabled)
        await _edit(query, skill_detail(user_id, token, lang))
        return
    if data.startswith("ux:skill:remove:"):
        token = data.rsplit(":", 1)[1]
        skill = _skill(user_id, token)
        name = skill.name if skill else ""
        await _edit(
            query,
            confirmation(
                pick(lang, f"确定从你的账户移除技能 `{name}`？", f"Remove skill `{name}` from your account?"),
                f"ux:skill:remove_yes:{token}",
                f"ux:skill:view:{token}",
                lang,
            ),
        )
        return
    if data.startswith("ux:skill:remove_yes:"):
        token = data.rsplit(":", 1)[1]
        skill = _skill(user_id, token)
        if skill and not skill.is_builtin:
            await asyncio.to_thread(get_skill_manager().remove_user_skill, user_id, skill.name)
        await _edit(query, skills_panel(user_id, lang))
        return

    if data == "ux:status":
        from domain.services import build_status_text

        await edit_query_rich_text(
            query,
            build_status_text(user_id, lang=lang),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(pick(lang, "🔄 刷新状态", "🔄 Refresh status"), callback_data="ux:status"),
                InlineKeyboardButton(pick(lang, "⬅️ 功能中心", "⬅️ Features"), callback_data="ux:features"),
            ]]),
        )
        return
    if data == "ux:chat:export":
        persona = get_current_persona_name(user_id)
        file_buffer = export_to_markdown(user_id, persona)
        if file_buffer is None:
            await edit_query_rich_text(
                query,
                pick(lang, "当前会话没有可导出的消息。", "The current chat has no messages to export."),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(pick(lang, "⬅️ 返回功能中心", "⬅️ Back to feature center"), callback_data="ux:features")
                ]]),
            )
            return
        try:
            file_buffer.seek(0)
        except Exception:
            pass
        await query.message.reply_document(
            document=file_buffer,
            filename=getattr(file_buffer, "name", None) or f"chat_export_{persona}.md",
            caption=pick(lang, f"当前会话导出 · 角色：{persona}", f"Current chat export · Persona: {persona}"),
        )
        return
    if data == "ux:confirm:clear_chat":
        await _edit(
            query,
            confirmation(
                pick(lang, "确定清空当前会话的全部消息并重置当前角色用量？", "Clear all messages in the current chat and reset usage for this persona?"),
                "ux:clear_chat:yes",
                "ux:features",
                lang,
            ),
        )
        return
    if data == "ux:clear_chat:yes":
        persona = get_current_persona_name(user_id)
        clear_conversation(ensure_session(user_id, persona))
        reset_token_usage(user_id, persona)
        await _persist()
        await _edit(query, feature_panel(user_id, lang))
        return

    if data == "ux:admin":
        await _edit(query, admin_panel(lang))
        return
    if data == "ux:admin:update":
        await _edit(
            query,
            confirmation(
                pick(lang, "从远程主分支检查并应用更新？如有新版本，服务将自动重启。", "Check the remote main branch and apply updates? The service will restart if a new version is found."),
                "ux:admin:update_yes",
                "ux:admin",
                lang,
            ),
        )
        return
    if data == "ux:admin:update_yes":
        await edit_query_rich_text(query, pick(lang, "⬇️ 正在检查并应用更新…", "⬇️ Checking and applying updates…"))
        result = await asyncio.to_thread(run_hot_update)
        if not result.get("ok"):
            await edit_query_rich_text(
                query,
                pick(lang, f"❌ 更新失败\n\n{result.get('message')}", f"❌ Update failed\n\n{result.get('message')}"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 管理员操作", "⬅️ Administrator actions"), callback_data="ux:admin")]]),
            )
            return
        if not result.get("changed"):
            await edit_query_rich_text(
                query,
                pick(lang, "✅ 当前已经是最新版本。", "✅ The service is already up to date."),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 管理员操作", "⬅️ Administrator actions"), callback_data="ux:admin")]]),
            )
            return
        await edit_query_rich_text(
            query,
            pick(
                lang,
                f"✅ 更新完成\n\n分支：`{result.get('branch')}`\n提交：`{str(result.get('old', ''))[:7]}` → `{str(result.get('new', ''))[:7]}`\n服务即将重启。",
                f"✅ Update complete\n\nBranch: `{result.get('branch')}`\nCommit: `{str(result.get('old', ''))[:7]}` → `{str(result.get('new', ''))[:7]}`\nThe service will restart now.",
            ),
        )
        schedule_process_restart()
        return
    if data == "ux:admin:restart":
        await _edit(
            query,
            confirmation(
                pick(lang, "同步运行数据并安全重启服务？", "Sync runtime data and safely restart the service?"),
                "ux:admin:restart_yes",
                "ux:admin",
                lang,
            ),
        )
        return
    if data == "ux:admin:restart_yes":
        await edit_query_rich_text(query, pick(lang, "🔄 正在同步数据并准备重启…", "🔄 Syncing data and preparing to restart…"))
        result = await asyncio.to_thread(run_safe_restart)
        if not result.get("ok"):
            await edit_query_rich_text(
                query,
                pick(lang, f"❌ 无法重启\n\n{result.get('message')}", f"❌ Restart cancelled\n\n{result.get('message')}"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 管理员操作", "⬅️ Administrator actions"), callback_data="ux:admin")]]),
            )
            return
        await edit_query_rich_text(query, pick(lang, "✅ 数据已同步，服务即将重启。", "✅ Data synced. The service will restart now."))
        schedule_process_restart()
        return

    if data.startswith("ux:set:reasoning:"):
        effort = data.rsplit(":", 1)[1]
        update_user_setting(user_id, "reasoning_effort", "" if effort == "clear" else effort)
        await _persist()
        await _edit(query, model_generation_panel(user_id, lang))
        return
    if data.startswith("ux:set:stream:"):
        update_user_setting(user_id, "stream_mode", data.rsplit(":", 1)[1])
        await _persist()
        await _edit(query, delivery_panel(user_id, lang))
        return
    if data.startswith("ux:set:busy:"):
        busy_mode = normalize_telegram_busy_mode(data.rsplit(":", 1)[1], default="")
        if busy_mode:
            update_user_setting(user_id, "busy_mode", busy_mode)
            await _persist()
        await _edit(query, delivery_panel(user_id, lang))
        return
    if data.startswith("ux:set:progress:"):
        tool_progress = normalize_telegram_tool_progress(data.rsplit(":", 1)[1], default="")
        if tool_progress:
            update_user_setting(user_id, "tool_progress", tool_progress)
            await _persist()
        await _edit(query, delivery_panel(user_id, lang))
        return
    if data == "ux:set:thinking:toggle":
        current = bool(cache.get_settings(user_id).get("show_thinking"))
        update_user_setting(user_id, "show_thinking", not current)
        await _persist()
        await _edit(query, model_generation_panel(user_id, lang))
        return
    if data.startswith("ux:set:temperature:"):
        update_user_setting(user_id, "temperature", float(data.rsplit(":", 1)[1]))
        await _persist()
        await _edit(query, model_generation_panel(user_id, lang))
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
            session = create_session(user_id, persona)
            cache.set_current_session_id(user_id, persona, session["id"])
            await _persist()
            await _edit(query, session_detail(user_id, session["id"], lang))
            return
        if action.startswith("view:"):
            await _edit(query, session_detail(user_id, int(action.split(":", 1)[1]), lang))
            return
        if action == "rename":
            session_id = get_current_session_id(user_id, persona)
            await _ask(query, context, kind="session_title", extra={"session_id": session_id}, lang=lang, back="ux:chat:0", text=pick(lang, "请输入当前会话的新标题。", "Send a new title for the current chat."))
            return
        if action.startswith("rename:"):
            session_id = int(action.split(":", 1)[1])
            await _ask(query, context, kind="session_title", extra={"session_id": session_id}, lang=lang, back=f"ux:chat:view:{session_id}", text=pick(lang, "你正在重命名这个会话。下一条消息不会发送给 AI。\n\n请输入新标题，或使用 /cancel 取消。", "You are renaming this chat. Your next message will not be sent to the AI.\n\nSend the new title, or use /cancel to stop."))
            return
        if action.startswith("delete:"):
            session_id = int(action.split(":", 1)[1])
            await _edit(query, confirmation(pick(lang, "确定删除这个会话及其全部消息？此操作无法撤销。", "Delete this chat and all its messages? This cannot be undone."), f"ux:chat:delete_yes:{session_id}", f"ux:chat:view:{session_id}", lang))
            return
        if action.startswith("delete_yes:"):
            session_id = int(action.split(":", 1)[1])
            sessions = get_sessions(user_id, persona)
            index = next((i for i, item in enumerate(sessions, 1) if item["id"] == session_id), None)
            if index:
                delete_chat_session(user_id, index, persona)
                await _persist()
            await _edit(query, sessions_panel(user_id, lang))
            return
        if action.startswith("switch:"):
            session_id = int(action.split(":", 1)[1])
            session = cache.get_session_by_id(session_id)
            if session and session.get("user_id") == user_id:
                cache.set_current_session_id(user_id, session["persona_name"], session_id)
                await _persist()
            await _edit(query, session_detail(user_id, session_id, lang))
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
            await _ask(query, context, kind="persona_name", lang=lang, back="ux:persona:0", text=pick(lang, "你正在创建新角色。下一条消息不会发送给 AI。\n\n请输入角色名称，或使用 /cancel 取消。", "You are creating a persona. Your next message will not be sent to the AI.\n\nSend its name, or use /cancel to stop."))
            return
        if action.startswith("view:"):
            await _edit(query, persona_detail(user_id, action.split(":", 1)[1], lang))
            return
        if action == "prompt":
            await _ask(query, context, kind="persona_prompt", lang=lang, back="ux:persona:0", text=pick(lang, "请输入当前角色的新系统提示词。", "Send the new system prompt for the current persona."))
            return
        if action.startswith("prompt:"):
            token = action.split(":", 1)[1]
            persona = next((item for item in get_personas(user_id).values() if stable_token(item["name"]) == token), None)
            if persona:
                await _ask(query, context, kind="persona_prompt_named", extra={"persona_name": persona["name"], "token": token}, lang=lang, back=f"ux:persona:view:{token}", text=pick(lang, f"你正在编辑角色 `{persona['name']}` 的提示词。下一条消息不会发送给 AI。\n\n请输入新提示词，或使用 /cancel 取消。", f"You are editing the prompt for `{persona['name']}`. Your next message will not be sent to the AI.\n\nSend the new prompt, or use /cancel to stop."))
            return
        if action.startswith("delete:"):
            token = action.split(":", 1)[1]
            persona = next((item for item in get_personas(user_id).values() if stable_token(item["name"]) == token), None)
            if not persona or persona["name"] == "default":
                await edit_query_rich_text(query, pick(lang, "默认角色不能删除。", "The default persona cannot be deleted."), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(pick(lang, "⬅️ 角色", "⬅️ Personas"), callback_data="ux:persona:0")]]))
                return
            await _edit(query, confirmation(pick(lang, f"确定删除角色 `{persona['name']}` 及其全部会话？此操作无法撤销。", f"Delete persona `{persona['name']}` and all its chats? This cannot be undone."), f"ux:persona:delete_yes:{token}", f"ux:persona:view:{token}", lang))
            return
        if action.startswith("delete_yes:"):
            token = action.split(":", 1)[1]
            persona = next((item for item in get_personas(user_id).values() if stable_token(item["name"]) == token), None)
            if persona and persona["name"] != "default":
                delete_persona(user_id, persona["name"])
                await _persist()
            await _edit(query, personas_panel(user_id, lang))
            return
        if action.startswith("switch:"):
            token = action.split(":", 1)[1]
            personas = list(get_personas(user_id).values())
            persona = next((item for item in personas if stable_token(item["name"]) == token), None)
            if persona:
                switch_persona(user_id, persona["name"])
                await _persist()
            await _edit(query, persona_detail(user_id, token, lang))
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
    if data.startswith("ux:cron:schedule:"):
        preset = data.rsplit(":", 1)[1]
        if preset == "custom":
            await _ask(
                query,
                context,
                kind="cron_expression",
                lang=lang,
                back="ux:cron:cancel",
                text=pick(lang, "请输入 5 段 Cron 表达式，例如 `15 10 * * 1-5`。", "Enter a five-field cron expression, such as `15 10 * * 1-5`."),
            )
            return
        expression = CRON_PRESETS.get(preset)
        draft = context.user_data.setdefault("cron_draft", {})
        if not expression or not draft.get("name"):
            await _edit(query, cron_panel(user_id, lang))
            return
        draft["cron_expression"] = expression
        await _ask(
            query,
            context,
            kind="cron_prompt",
            lang=lang,
            back="ux:cron:cancel",
            text=pick(lang, "请输入任务执行时交给 AI 的提示词。", "Send the prompt the AI should run for this task."),
        )
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
