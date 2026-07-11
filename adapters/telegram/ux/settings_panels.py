"""Settings-specific text and keyboard builders."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from domain.services import (
    get_current_persona_name,
    get_token_limit,
    get_user_settings,
)
from domain.services.platform import mask_key
from infrastructure.config import (
    normalize_telegram_busy_mode,
    normalize_telegram_tool_progress,
)

from .locale import pick
from .tokens import stable_token


def _markup(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


def _selected(current: str, value: str, label: str) -> str:
    return f"{'✅ ' if current == value else ''}{label}"


def _reasoning_label(value: str, lang: str) -> str:
    labels = {
        "": pick(lang, "自动（模型默认）", "Auto (model default)"),
        "none": pick(lang, "关闭", "Off"),
        "minimal": pick(lang, "最少", "Minimal"),
        "low": pick(lang, "低", "Low"),
        "medium": pick(lang, "中", "Medium"),
        "high": pick(lang, "高", "High"),
        "xhigh": pick(lang, "极高", "Extra high"),
    }
    return labels.get(value or "", value or labels[""])


def _stream_label(value: str, lang: str) -> str:
    labels = {
        "": pick(lang, "实时流式", "Live streaming"),
        "default": pick(lang, "实时流式", "Live streaming"),
        "time": pick(lang, "定时刷新", "Timed updates"),
        "chars": pick(lang, "按字数刷新", "Character batches"),
        "off": pick(lang, "生成完再发送", "Send when complete"),
    }
    return labels.get(value or "", value or labels[""])


def _connection_type(base_url: str, lang: str) -> str:
    if (base_url or "").rstrip("/") == "https://api.openai.com/v1":
        return pick(lang, "OpenAI 官方接口", "Official OpenAI endpoint")
    return pick(lang, "自定义 OpenAI 兼容接口", "Custom OpenAI-compatible endpoint")


def settings_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    settings = get_user_settings(user_id)
    persona = get_current_persona_name(user_id)
    key_state = pick(lang, "✅ 已配置", "✅ Configured") if settings.get("api_key") else pick(lang, "❌ 未配置", "❌ Missing")
    text = pick(
        lang,
        "⚙️ **设置中心**\n\n"
        f"🔌 模型服务：{_connection_type(settings.get('base_url', ''), lang)}\n"
        f"🔑 API Key：{key_state}\n"
        f"🤖 对话模型：`{settings.get('model')}`\n"
        f"🎨 输出方式：{_stream_label(settings.get('stream_mode', ''), lang)}\n"
        f"🧠 推理强度：{_reasoning_label(settings.get('reasoning_effort', ''), lang)}\n"
        f"🎭 当前角色：`{persona}`\n"
        f"🕐 时区：`{settings.get('timezone', 'Asia/Shanghai')}`\n\n"
        "选择要修改的类别。",
        "⚙️ **Settings center**\n\n"
        f"🔌 Model service: {_connection_type(settings.get('base_url', ''), lang)}\n"
        f"🔑 API key: {key_state}\n"
        f"🤖 Chat model: `{settings.get('model')}`\n"
        f"🎨 Delivery: {_stream_label(settings.get('stream_mode', ''), lang)}\n"
        f"🧠 Reasoning: {_reasoning_label(settings.get('reasoning_effort', ''), lang)}\n"
        f"🎭 Current persona: `{persona}`\n"
        f"🕐 Timezone: `{settings.get('timezone', 'Asia/Shanghai')}`\n\n"
        "Choose a category to change.",
    )
    rows = [
        [InlineKeyboardButton(pick(lang, "🤖 选择对话模型", "🤖 Choose chat model"), callback_data="ux:settings:model")],
        [
            InlineKeyboardButton(pick(lang, "🔌 模型服务连接", "🔌 Model service"), callback_data="ux:settings:connection"),
            InlineKeyboardButton(pick(lang, "🎨 生成与发送", "🎨 Generation & delivery"), callback_data="ux:settings:generation"),
        ],
        [
            InlineKeyboardButton(pick(lang, "🧩 高级设置", "🧩 Advanced settings"), callback_data="ux:settings:advanced"),
            InlineKeyboardButton(pick(lang, "🕐 时区设置", "🕐 Timezone"), callback_data="ux:settings:timezone"),
        ],
        [
            InlineKeyboardButton(pick(lang, "📊 用量与上下文", "📊 Usage & context"), callback_data="ux:usage"),
            InlineKeyboardButton(pick(lang, "📋 查看全部配置", "📋 View all values"), callback_data="ux:settings:full"),
        ],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回主菜单", "⬅️ Back to main menu"), callback_data="ux:menu")],
    ]
    return text, _markup(rows)


def generation_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    settings = get_user_settings(user_id)
    reasoning = settings.get("reasoning_effort", "") or ""
    stream = settings.get("stream_mode", "") or "default"
    busy_mode = normalize_telegram_busy_mode(settings.get("busy_mode"))
    tool_progress = normalize_telegram_tool_progress(settings.get("tool_progress"))
    thinking = bool(settings.get("show_thinking"))
    busy_label = pick(
        lang,
        {"interrupt": "中断旧回复并处理新消息", "queue": "让新消息排队等待"}[busy_mode],
        {"interrupt": "Interrupt the old reply", "queue": "Queue the new message"}[busy_mode],
    )
    progress_label = pick(
        lang,
        {"off": "不显示", "compact": "只显示关键进度", "full": "显示完整进度"}[tool_progress],
        {"off": "Hidden", "compact": "Key activity only", "full": "Full activity"}[tool_progress],
    )
    text = pick(
        lang,
        "🎨 **生成与发送**\n\n"
        f"🧠 推理强度：{_reasoning_label(reasoning, lang)}\n"
        f"🌊 消息发送：{_stream_label(stream, lang)}\n"
        f"💭 思考摘要：{'显示' if thinking else '隐藏'}\n"
        f"📨 收到新消息时：{busy_label}\n"
        f"🧰 工具活动：{progress_label}\n"
        f"🌡 温度：`{settings.get('temperature', 0.7)}`\n\n"
        "“消息发送”只影响 Telegram 中的刷新方式，不会改变模型能力。",
        "🎨 **Generation & delivery**\n\n"
        f"🧠 Reasoning effort: {_reasoning_label(reasoning, lang)}\n"
        f"🌊 Message delivery: {_stream_label(stream, lang)}\n"
        f"💭 Thinking summary: {'Shown' if thinking else 'Hidden'}\n"
        f"📨 When a new message arrives: {busy_label}\n"
        f"🧰 Tool activity: {progress_label}\n"
        f"🌡 Temperature: `{settings.get('temperature', 0.7)}`\n\n"
        "Message delivery only controls Telegram updates; it does not change model capability.",
    )
    rows = [
        [
            InlineKeyboardButton(_selected(reasoning, "", pick(lang, "自动", "Auto")), callback_data="ux:set:reasoning:clear"),
            InlineKeyboardButton(_selected(reasoning, "none", pick(lang, "关闭", "Off")), callback_data="ux:set:reasoning:none"),
            InlineKeyboardButton(_selected(reasoning, "minimal", pick(lang, "最少", "Minimal")), callback_data="ux:set:reasoning:minimal"),
        ],
        [
            InlineKeyboardButton(_selected(reasoning, "low", pick(lang, "低", "Low")), callback_data="ux:set:reasoning:low"),
            InlineKeyboardButton(_selected(reasoning, "medium", pick(lang, "中", "Medium")), callback_data="ux:set:reasoning:medium"),
            InlineKeyboardButton(_selected(reasoning, "high", pick(lang, "高", "High")), callback_data="ux:set:reasoning:high"),
            InlineKeyboardButton(_selected(reasoning, "xhigh", pick(lang, "极高", "XHigh")), callback_data="ux:set:reasoning:xhigh"),
        ],
        [
            InlineKeyboardButton(_selected(stream, "default", pick(lang, "实时流式", "Live")), callback_data="ux:set:stream:default"),
            InlineKeyboardButton(_selected(stream, "time", pick(lang, "定时刷新", "Timed")), callback_data="ux:set:stream:time"),
        ],
        [
            InlineKeyboardButton(_selected(stream, "chars", pick(lang, "按字数刷新", "Batched")), callback_data="ux:set:stream:chars"),
            InlineKeyboardButton(_selected(stream, "off", pick(lang, "完成后发送", "On completion")), callback_data="ux:set:stream:off"),
        ],
        [InlineKeyboardButton(pick(lang, f"💭 思考摘要：{'显示' if thinking else '隐藏'}", f"💭 Thinking summary: {'shown' if thinking else 'hidden'}"), callback_data="ux:set:thinking:toggle")],
        [
            InlineKeyboardButton(_selected(busy_mode, "interrupt", pick(lang, "⚡ 中断旧回复", "⚡ Interrupt old reply")), callback_data="ux:set:busy:interrupt"),
            InlineKeyboardButton(_selected(busy_mode, "queue", pick(lang, "🕐 新消息排队", "🕐 Queue new message")), callback_data="ux:set:busy:queue"),
        ],
        [
            InlineKeyboardButton(_selected(tool_progress, "off", pick(lang, "🔕 隐藏工具进度", "🔕 Hide tools")), callback_data="ux:set:progress:off"),
            InlineKeyboardButton(_selected(tool_progress, "compact", pick(lang, "🧰 关键进度", "🧰 Key activity")), callback_data="ux:set:progress:compact"),
        ],
        [InlineKeyboardButton(_selected(tool_progress, "full", pick(lang, "📋 完整工具进度", "📋 Full tool activity")), callback_data="ux:set:progress:full")],
        [
            InlineKeyboardButton("🌡 0.2", callback_data="ux:set:temperature:0.2"),
            InlineKeyboardButton("🌡 0.7", callback_data="ux:set:temperature:0.7"),
            InlineKeyboardButton("🌡 1.0", callback_data="ux:set:temperature:1.0"),
        ],
        [InlineKeyboardButton(pick(lang, "✏️ 输入自定义温度", "✏️ Enter custom temperature"), callback_data="ux:settings:temperature_custom")],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回设置中心", "⬅️ Back to settings"), callback_data="ux:settings")],
    ]
    return text, _markup(rows)


def connection_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    settings = get_user_settings(user_id)
    base_url = settings.get("base_url", "")
    key_state = pick(lang, "✅ 已安全保存", "✅ Saved securely") if settings.get("api_key") else pick(lang, "❌ 尚未设置", "❌ Not set")
    text = pick(
        lang,
        "🔌 **模型服务连接**\n\n"
        f"服务类型：{_connection_type(base_url, lang)}\n"
        f"API 地址：`{base_url}`\n"
        f"API Key：{key_state}\n\n"
        "API 地址决定请求发送到哪里；“使用 OpenAI 官方地址”只会恢复地址，不会更改密钥或模型。\n"
        "为保护密钥，API Key 只能在私聊中输入。",
        "🔌 **Model service connection**\n\n"
        f"Service type: {_connection_type(base_url, lang)}\n"
        f"API endpoint: `{base_url}`\n"
        f"API key: {key_state}\n\n"
        "The endpoint controls where requests are sent. “Use official OpenAI endpoint” only restores the URL; it does not change your key or model.\n"
        "For safety, API keys can only be entered in a private chat.",
    )
    rows = [
        [
            InlineKeyboardButton(pick(lang, "🔑 设置或更换 API Key", "🔑 Set or replace API key"), callback_data="ux:onboard:key"),
            InlineKeyboardButton(pick(lang, "🧪 测试当前连接", "🧪 Test connection"), callback_data="ux:settings:connection_test"),
        ],
        [InlineKeyboardButton(pick(lang, "🌐 输入自定义兼容 API 地址", "🌐 Enter custom compatible endpoint"), callback_data="ux:onboard:base_custom")],
        [InlineKeyboardButton(pick(lang, "↩️ 使用 OpenAI 官方 API 地址", "↩️ Use official OpenAI API endpoint"), callback_data="ux:onboard:base_default")],
        [InlineKeyboardButton(pick(lang, "💾 管理已保存的模型服务", "💾 Manage saved model services"), callback_data="ux:providers")],
        [InlineKeyboardButton(pick(lang, "🗑 清除已保存的 API Key", "🗑 Clear saved API key"), callback_data="ux:confirm:clear_key")],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回设置中心", "⬅️ Back to settings"), callback_data="ux:settings")],
    ]
    return text, _markup(rows)


def providers_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    settings = get_user_settings(user_id)
    presets = settings.get("api_presets", {}) or {}
    text = pick(
        lang,
        "💾 **已保存的模型服务**\n\n"
        "保存项会同时记录 API 地址、API Key 和模型，便于在不同服务之间切换。\n"
        f"当前共有 {len(presets)} 个保存项。",
        "💾 **Saved model services**\n\n"
        "Each saved service stores its endpoint, API key, and model so you can switch providers quickly.\n"
        f"You currently have {len(presets)} saved service(s).",
    )
    rows = []
    current = (settings.get("base_url"), settings.get("api_key"), settings.get("model"))
    for name, preset in sorted(presets.items(), key=lambda item: item[0].casefold()):
        active = current == (preset.get("base_url"), preset.get("api_key"), preset.get("model"))
        rows.append([InlineKeyboardButton(f"{'✅ ' if active else '🔌 '}{name[:40]}", callback_data=f"ux:provider:view:{stable_token(name)}")])
    rows.extend([
        [InlineKeyboardButton(pick(lang, "➕ 保存当前模型服务", "➕ Save current model service"), callback_data="ux:provider:save")],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回模型服务连接", "⬅️ Back to model service"), callback_data="ux:settings:connection")],
    ])
    return text, _markup(rows)


def provider_detail(user_id: int, token: str, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    settings = get_user_settings(user_id)
    presets = settings.get("api_presets", {}) or {}
    match = next(((name, preset) for name, preset in presets.items() if stable_token(name) == token), None)
    if match is None:
        return providers_panel(user_id, lang)
    name, preset = match
    active = (
        settings.get("base_url"),
        settings.get("api_key"),
        settings.get("model"),
    ) == (
        preset.get("base_url"),
        preset.get("api_key"),
        preset.get("model"),
    )
    status = pick(lang, "✅ 当前正在使用", "✅ Currently active") if active else pick(lang, "⚪ 当前未使用", "⚪ Not active")
    text = pick(
        lang,
        f"🔌 **已保存服务：{name}**\n\n"
        f"状态：{status}\n"
        f"API 地址：`{preset.get('base_url', '')}`\n"
        f"API Key：`{mask_key(preset.get('api_key', ''))}`\n"
        f"模型：`{preset.get('model', '')}`",
        f"🔌 **Saved service: {name}**\n\n"
        f"Status: {status}\n"
        f"API endpoint: `{preset.get('base_url', '')}`\n"
        f"API key: `{mask_key(preset.get('api_key', ''))}`\n"
        f"Model: `{preset.get('model', '')}`",
    )
    rows = [
        [InlineKeyboardButton(
            pick(lang, "✅ 当前正在使用", "✅ Currently active") if active else pick(lang, "🔄 切换到此服务", "🔄 Switch to this service"),
            callback_data="ux:noop" if active else f"ux:provider:load:{token}",
        )],
        [InlineKeyboardButton(pick(lang, "🗑 删除此保存项", "🗑 Delete this saved service"), callback_data=f"ux:provider:delete:{token}")],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回保存列表", "⬅️ Back to saved services"), callback_data="ux:providers")],
    ]
    return text, _markup(rows)


def advanced_settings_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    settings = get_user_settings(user_id)
    persona = get_current_persona_name(user_id)
    token_limit = get_token_limit(user_id, persona)
    global_prompt = settings.get("global_prompt", "") or ""
    current_model = settings.get("model", "")
    title_model = settings.get("title_model", "") or current_model
    cron_model = settings.get("cron_model", "") or current_model
    prompt_state = pick(lang, "已设置", "Set") if global_prompt else pick(lang, "未设置", "Not set")
    text = pick(
        lang,
        "🧩 **高级设置**\n\n"
        f"📝 全局提示词：{prompt_state}\n"
        f"🏷 会话标题模型：`{title_model}`{'（跟随当前模型）' if not settings.get('title_model') else ''}\n"
        f"⏰ 定时任务模型：`{cron_model}`{'（跟随当前模型）' if not settings.get('cron_model') else ''}\n"
        f"📏 角色 `{persona}` 的 Token 限额：{'不限' if token_limit <= 0 else f'{token_limit:,}'}\n\n"
        "标题模型和定时任务模型可填写 `模型名`，也可填写 `保存项名称:模型名`。",
        "🧩 **Advanced settings**\n\n"
        f"📝 Global prompt: {prompt_state}\n"
        f"🏷 Chat-title model: `{title_model}`{' (follows current model)' if not settings.get('title_model') else ''}\n"
        f"⏰ Scheduled-task model: `{cron_model}`{' (follows current model)' if not settings.get('cron_model') else ''}\n"
        f"📏 Token limit for persona `{persona}`: {'Unlimited' if token_limit <= 0 else f'{token_limit:,}'}\n\n"
        "Title and scheduled-task models accept either `model` or `saved-service:model`.",
    )
    rows = [
        [
            InlineKeyboardButton(pick(lang, "📝 设置全局提示词", "📝 Set global prompt"), callback_data="ux:advanced:global_prompt"),
            InlineKeyboardButton(pick(lang, "🧹 清除全局提示词", "🧹 Clear global prompt"), callback_data="ux:advanced:global_prompt_clear"),
        ],
        [InlineKeyboardButton(pick(lang, "🏷 设置会话标题模型", "🏷 Set chat-title model"), callback_data="ux:advanced:title_model")],
        [InlineKeyboardButton(pick(lang, "⏰ 设置定时任务模型", "⏰ Set scheduled-task model"), callback_data="ux:advanced:cron_model")],
        [InlineKeyboardButton(pick(lang, "♻️ 两者都跟随当前模型", "♻️ Both follow current model"), callback_data="ux:advanced:models_current")],
        [
            InlineKeyboardButton(pick(lang, "📏 设置 Token 限额", "📏 Set token limit"), callback_data="ux:advanced:token_limit"),
            InlineKeyboardButton(pick(lang, "♾ 取消 Token 限额", "♾ Remove token limit"), callback_data="ux:advanced:token_limit_clear"),
        ],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回设置中心", "⬅️ Back to settings"), callback_data="ux:settings")],
    ]
    return text, _markup(rows)


def timezone_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    current = get_user_settings(user_id).get("timezone", "Asia/Shanghai")
    text = pick(
        lang,
        f"🕐 **时区设置**\n\n当前时区：`{current}`\n定时任务的执行时间和时间提示都会使用此时区。",
        f"🕐 **Timezone settings**\n\nCurrent timezone: `{current}`\nScheduled tasks and time context use this timezone.",
    )
    rows = [
        [InlineKeyboardButton("🇨🇳 Asia/Shanghai", callback_data="ux:set:timezone:Asia/Shanghai")],
        [InlineKeyboardButton("🌐 UTC", callback_data="ux:set:timezone:UTC"), InlineKeyboardButton("🇬🇧 Europe/London", callback_data="ux:set:timezone:Europe/London")],
        [InlineKeyboardButton(pick(lang, "✏️ 输入其他 IANA 时区", "✏️ Enter another IANA timezone"), callback_data="ux:settings:timezone_custom")],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回设置中心", "⬅️ Back to settings"), callback_data="ux:settings")],
    ]
    return text, _markup(rows)
