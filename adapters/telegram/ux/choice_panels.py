"""Button-first selectors for settings with enumerable values."""

from __future__ import annotations

import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from domain.services import get_current_persona_name, get_token_limit, get_user_settings
from infrastructure.config import MODELS_PER_PAGE

from .locale import pick
from .tokens import stable_token


TARGET_KEYS = {"title": "title_model", "cron": "cron_model"}


def _target_label(target: str, lang: str) -> str:
    if target == "title":
        return pick(lang, "会话标题模型", "chat-title model")
    return pick(lang, "定时任务模型", "scheduled-task model")


def specialized_model_source_panel(user_id: int, target: str, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    settings = get_user_settings(user_id)
    key = TARGET_KEYS.get(target, "title_model")
    selected = settings.get(key, "") or ""
    current = selected or settings.get("model", "")
    presets = settings.get("api_presets", {}) or {}
    label = _target_label(target, lang)
    text = pick(
        lang,
        f"🤖 **选择{label}**\n\n当前：`{current}`{'（跟随对话模型）' if not selected else ''}\n\n"
        "先选择模型服务，机器人会自动获取该服务的模型列表；无需手动填写 `保存项名称:模型名`。",
        f"🤖 **Choose the {label}**\n\nCurrent: `{current}`{' (follows chat model)' if not selected else ''}\n\n"
        "Choose a model service first. The bot will fetch its model list automatically; no `saved-service:model` formatting is required.",
    )
    rows = [
        [InlineKeyboardButton(pick(lang, "✅ 跟随当前对话模型", "✅ Follow current chat model"), callback_data=f"ux:smodel:{target}:current")],
        [InlineKeyboardButton(pick(lang, "🔌 从当前模型服务选择", "🔌 Choose from current service"), callback_data=f"ux:smodel:{target}:source:current")],
    ]
    for name in sorted(presets, key=str.casefold):
        rows.append([InlineKeyboardButton(
            f"💾 {name[:38]}",
            callback_data=f"ux:smodel:{target}:source:{stable_token(name)}",
        )])
    rows.append([InlineKeyboardButton(pick(lang, "⬅️ 返回高级设置", "⬅️ Back to advanced settings"), callback_data="ux:settings:advanced")])
    return text, InlineKeyboardMarkup(rows)


def specialized_model_keyboard(
    models: list[str],
    page: int,
    selected: str,
    *,
    target: str,
    lang: str,
) -> InlineKeyboardMarkup:
    total_pages = max(1, math.ceil(len(models) / MODELS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * MODELS_PER_PAGE
    rows = []
    for offset, model in enumerate(models[start:start + MODELS_PER_PAGE]):
        rows.append([InlineKeyboardButton(
            f"{'✅ ' if model == selected else ''}{model[:48]}{'…' if len(model) > 48 else ''}",
            callback_data=f"ux:smodel:pick:{start + offset}",
        )])
    if total_pages > 1:
        rows.append([
            InlineKeyboardButton("◀️", callback_data=f"ux:smodel:page:{max(0, page - 1)}"),
            InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="ux:noop"),
            InlineKeyboardButton("▶️", callback_data=f"ux:smodel:page:{min(total_pages - 1, page + 1)}"),
        ])
    rows.append([InlineKeyboardButton(pick(lang, "⬅️ 重新选择模型服务", "⬅️ Choose another service"), callback_data=f"ux:advanced:{TARGET_KEYS[target]}")])
    return InlineKeyboardMarkup(rows)


def token_limit_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    persona = get_current_persona_name(user_id)
    current = get_token_limit(user_id, persona)
    current_text = pick(lang, "不限", "Unlimited") if current <= 0 else f"{current:,}"
    text = pick(
        lang,
        f"📏 **Token 限额**\n\n当前角色：`{persona}`\n当前限额：{current_text}\n\n"
        "限额用于限制当前角色的累计 Token 用量。选择常用值，只有特殊数值才需要手动输入。",
        f"📏 **Token limit**\n\nCurrent persona: `{persona}`\nCurrent limit: {current_text}\n\n"
        "The limit caps cumulative token usage for this persona. Choose a preset; only unusual values need manual input.",
    )
    presets = [0, 8_000, 16_000, 32_000, 64_000, 128_000, 256_000, 1_000_000]
    labels = {0: pick(lang, "♾ 不限", "♾ Unlimited"), 1_000_000: "1M"}
    buttons = [InlineKeyboardButton(
        f"{'✅ ' if value == current else ''}{labels.get(value, f'{value // 1000}K')}",
        callback_data=f"ux:set:token_limit:{value}",
    ) for value in presets]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.extend([
        [InlineKeyboardButton(pick(lang, "✏️ 输入其他数值", "✏️ Enter another value"), callback_data="ux:advanced:token_limit_custom")],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回高级设置", "⬅️ Back to advanced settings"), callback_data="ux:settings:advanced")],
    ])
    return text, InlineKeyboardMarkup(rows)


CRON_PRESETS = {
    "every_30m": "*/30 * * * *",
    "hourly": "0 * * * *",
    "daily_0900": "0 9 * * *",
    "daily_1800": "0 18 * * *",
    "weekdays_0900": "0 9 * * 1-5",
    "monday_0900": "0 9 * * 1",
}


def cron_schedule_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    timezone = get_user_settings(user_id).get("timezone", "Asia/Shanghai")
    text = pick(
        lang,
        f"🕐 **选择执行计划**\n\n当前时区：`{timezone}`\n请选择常用计划；只有不在列表中的计划才需要输入 Cron 表达式。",
        f"🕐 **Choose a schedule**\n\nCurrent timezone: `{timezone}`\nChoose a common schedule. Only schedules not listed here require a custom cron expression.",
    )
    rows = [
        [
            InlineKeyboardButton(pick(lang, "每 30 分钟", "Every 30 minutes"), callback_data="ux:cron:schedule:every_30m"),
            InlineKeyboardButton(pick(lang, "每小时", "Hourly"), callback_data="ux:cron:schedule:hourly"),
        ],
        [
            InlineKeyboardButton(pick(lang, "每天 09:00", "Daily 09:00"), callback_data="ux:cron:schedule:daily_0900"),
            InlineKeyboardButton(pick(lang, "每天 18:00", "Daily 18:00"), callback_data="ux:cron:schedule:daily_1800"),
        ],
        [
            InlineKeyboardButton(pick(lang, "工作日 09:00", "Weekdays 09:00"), callback_data="ux:cron:schedule:weekdays_0900"),
            InlineKeyboardButton(pick(lang, "每周一 09:00", "Mondays 09:00"), callback_data="ux:cron:schedule:monday_0900"),
        ],
        [InlineKeyboardButton(pick(lang, "✏️ 自定义执行计划", "✏️ Custom schedule"), callback_data="ux:cron:schedule:custom")],
        [InlineKeyboardButton(pick(lang, "取消创建", "Cancel creation"), callback_data="ux:cron:cancel")],
    ]
    return text, InlineKeyboardMarkup(rows)
