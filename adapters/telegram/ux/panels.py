"""Text and keyboard builders for the button-driven Telegram UI."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from domain.services import (
    get_current_persona_name,
    get_current_session_id,
    get_personas,
    get_session_message_count,
    get_sessions,
    get_user_settings,
    has_api_key,
)
from domain.services.cron.timezone import describe_cron, next_run_at
from infrastructure.cache import cache
from infrastructure.config import (
    is_admin,
)

from .locale import pick
from .choice_panels import (
    CRON_PRESETS,
    cron_schedule_panel,
    specialized_model_keyboard,
    specialized_model_source_panel,
    token_limit_panel,
)
from .feature_panels import (
    admin_panel,
    feature_panel,
    memory_panel,
    skill_detail,
    skills_panel,
)
from .settings_panels import (
    advanced_settings_panel,
    connection_panel,
    generation_panel,
    provider_detail,
    providers_panel,
    settings_panel,
    timezone_panel,
)
from .tokens import stable_token

PAGE_SIZE = 6


def _markup(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


def main_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    configured = has_api_key(user_id)
    persona = get_current_persona_name(user_id)
    if configured:
        text = pick(
            lang,
            f"👋 **欢迎回来**\n\n当前角色：`{persona}`\n直接发送消息即可开始聊天。",
            f"👋 **Welcome back**\n\nCurrent persona: `{persona}`\nSend a message to start chatting.",
        )
        rows = [
            [InlineKeyboardButton(pick(lang, "💬 会话", "💬 Chats"), callback_data="ux:chat:0"), InlineKeyboardButton(pick(lang, "🎭 角色", "🎭 Personas"), callback_data="ux:persona:0")],
            [InlineKeyboardButton(pick(lang, "⚙️ 设置", "⚙️ Settings"), callback_data="ux:settings"), InlineKeyboardButton(pick(lang, "⏰ 定时任务", "⏰ Schedules"), callback_data="ux:cron")],
            [InlineKeyboardButton(pick(lang, "🧰 功能中心", "🧰 Features"), callback_data="ux:features"), InlineKeyboardButton(pick(lang, "➕ 新会话", "➕ New chat"), callback_data="ux:chat:new")],
            [InlineKeyboardButton(pick(lang, "📚 帮助", "📚 Help"), callback_data="ux:help")],
        ]
    else:
        text = pick(
            lang,
            "👋 **欢迎使用 AI Bot**\n\n只需三步：\n1. 设置 API 地址\n2. 安全保存 API Key\n3. 选择模型并发送第一条消息",
            "👋 **Welcome to AI Bot**\n\nThree quick steps:\n1. Choose an API endpoint\n2. Save your API key securely\n3. Pick a model and send your first message",
        )
        rows = [
            [InlineKeyboardButton(pick(lang, "1️⃣ 使用 OpenAI 官方 API 地址", "1️⃣ Use official OpenAI API endpoint"), callback_data="ux:onboard:base_default")],
            [InlineKeyboardButton(pick(lang, "🌐 使用其他兼容 API 地址", "🌐 Use another compatible endpoint"), callback_data="ux:onboard:base_custom")],
            [InlineKeyboardButton(pick(lang, "🔑 设置服务商 API Key", "🔑 Set provider API key"), callback_data="ux:onboard:key")],
            [InlineKeyboardButton(pick(lang, "📚 查看帮助", "📚 View help"), callback_data="ux:help")],
        ]
    rows.append([
        InlineKeyboardButton("中文", callback_data="ux:lang:zh"),
        InlineKeyboardButton("English", callback_data="ux:lang:en"),
    ])
    return text, _markup(rows)


def sessions_panel(user_id: int, lang: str, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    persona = get_current_persona_name(user_id)
    sessions = get_sessions(user_id, persona)
    current = get_current_session_id(user_id, persona)
    pages = max(1, (len(sessions) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    page_items = sessions[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    text = pick(lang, f"💬 **会话** · 角色 `{persona}`\n\n选择一个会话，或创建新会话。", f"💬 **Chats** · persona `{persona}`\n\nChoose a chat or create a new one.")
    rows = []
    for session in page_items:
        marker = "✅ " if session["id"] == current else ""
        title = session.get("title") or pick(lang, "新会话", "New chat")
        count = get_session_message_count(session["id"])
        rows.append([InlineKeyboardButton(f"{marker}{title[:34]} · {count}", callback_data=f"ux:chat:switch:{session['id']}")])
    if pages > 1:
        rows.append([
            InlineKeyboardButton("◀️", callback_data=f"ux:chat:{max(0, page - 1)}"),
            InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="ux:noop"),
            InlineKeyboardButton("▶️", callback_data=f"ux:chat:{min(pages - 1, page + 1)}"),
        ])
    rows.extend([
        [InlineKeyboardButton(pick(lang, "➕ 新会话", "➕ New chat"), callback_data="ux:chat:new"), InlineKeyboardButton(pick(lang, "✏️ 重命名当前", "✏️ Rename current"), callback_data="ux:chat:rename")],
        [InlineKeyboardButton(pick(lang, "🗑 删除当前", "🗑 Delete current"), callback_data="ux:confirm:delete_chat"), InlineKeyboardButton(pick(lang, "⬅️ 主菜单", "⬅️ Main menu"), callback_data="ux:menu")],
    ])
    return text, _markup(rows)


def personas_panel(user_id: int, lang: str, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    personas = list(get_personas(user_id).values())
    current = get_current_persona_name(user_id)
    pages = max(1, (len(personas) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    text = pick(lang, "🎭 **角色**\n\n不同角色拥有独立的提示词、会话和用量。", "🎭 **Personas**\n\nEach persona has its own prompt, chats, and usage.")
    rows = []
    for persona in personas[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        name = persona["name"]
        rows.append([InlineKeyboardButton(f"{'✅ ' if name == current else ''}{name[:42]}", callback_data=f"ux:persona:switch:{stable_token(name)}")])
    if pages > 1:
        rows.append([
            InlineKeyboardButton("◀️", callback_data=f"ux:persona:{max(0, page - 1)}"),
            InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="ux:noop"),
            InlineKeyboardButton("▶️", callback_data=f"ux:persona:{min(pages - 1, page + 1)}"),
        ])
    rows.extend([
        [InlineKeyboardButton(pick(lang, "➕ 新角色", "➕ New persona"), callback_data="ux:persona:new"), InlineKeyboardButton(pick(lang, "📝 编辑提示词", "📝 Edit prompt"), callback_data="ux:persona:prompt")],
        [InlineKeyboardButton(pick(lang, "🗑 删除当前", "🗑 Delete current"), callback_data="ux:confirm:delete_persona"), InlineKeyboardButton(pick(lang, "⬅️ 主菜单", "⬅️ Main menu"), callback_data="ux:menu")],
    ])
    return text, _markup(rows)


def help_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    text = pick(lang, "📚 **帮助中心**\n\n你想完成什么？", "📚 **Help center**\n\nWhat would you like to do?")
    rows = [
        [InlineKeyboardButton(pick(lang, "💬 开始聊天", "💬 Start chatting"), callback_data="ux:help:chat"), InlineKeyboardButton(pick(lang, "🤖 更换模型", "🤖 Change model"), callback_data="ux:settings:model")],
        [InlineKeyboardButton(pick(lang, "🗂 管理会话", "🗂 Manage chats"), callback_data="ux:chat:0"), InlineKeyboardButton(pick(lang, "🎭 管理角色", "🎭 Manage personas"), callback_data="ux:persona:0")],
        [InlineKeyboardButton(pick(lang, "🧠 记忆功能", "🧠 Memory"), callback_data="ux:help:memory"), InlineKeyboardButton(pick(lang, "⏰ 定时任务", "⏰ Schedules"), callback_data="ux:cron")],
        [InlineKeyboardButton(pick(lang, "⚙️ 设置", "⚙️ Settings"), callback_data="ux:settings")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(pick(lang, "🛡 管理员功能", "🛡 Admin tools"), callback_data="ux:help:admin")])
    rows.append([InlineKeyboardButton(pick(lang, "⬅️ 主菜单", "⬅️ Main menu"), callback_data="ux:menu")])
    return text, _markup(rows)


def help_topic(topic: str, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    topics = {
        "chat": pick(lang, "💬 **开始聊天**\n\n私聊中直接发送文字、图片或文件。群聊中请 @机器人 或回复机器人消息。\n\n生成时可点击“停止生成”。", "💬 **Start chatting**\n\nSend text, images, or files in a private chat. In groups, mention the bot or reply to it.\n\nUse the Stop button while generating."),
        "memory": pick(lang, "🧠 **记忆功能**\n\n`/remember 内容` 保存长期偏好。\n`/memories` 查看。\n`/forget 编号` 删除。\n\n不要保存密码、密钥或临时任务信息。", "🧠 **Memory**\n\n`/remember text` saves a durable preference.\n`/memories` lists memories.\n`/forget number` deletes one.\n\nDo not store passwords, keys, or temporary task details."),
        "admin": pick(lang, "🛡 **管理员功能**\n\n`/update` 更新服务\n`/restart` 安全重启\n`/skill install ...` 安装技能\n\n这些命令只对 `ADMIN_IDS`/`OWNER_ID` 开放。", "🛡 **Admin tools**\n\n`/update` updates the service\n`/restart` safely restarts it\n`/skill install ...` installs skills\n\nThese commands require `ADMIN_IDS`/`OWNER_ID`."),
    }
    return topics.get(topic, topics["chat"]), _markup([[InlineKeyboardButton(pick(lang, "⬅️ 帮助", "⬅️ Help"), callback_data="ux:help")]])


def cron_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    tasks = cache.get_cron_tasks(user_id)
    timezone = get_user_settings(user_id).get("timezone", "Asia/Shanghai")
    text = pick(lang, f"⏰ **定时任务**\n\n时区：`{timezone}`\n共 {len(tasks)} 个任务。", f"⏰ **Schedules**\n\nTimezone: `{timezone}`\n{len(tasks)} task(s).")
    rows = []
    for task in tasks:
        next_run = next_run_at(task["cron_expression"], timezone)
        when = next_run.strftime("%m-%d %H:%M") if next_run else "—"
        token = stable_token(task["name"])
        rows.append([InlineKeyboardButton(f"{'✅' if task.get('enabled', True) else '⏸'} {task['name'][:28]} · {when}", callback_data=f"ux:cron:view:{token}")])
    rows.extend([
        [InlineKeyboardButton(pick(lang, "➕ 新建任务", "➕ New task"), callback_data="ux:cron:add"), InlineKeyboardButton(pick(lang, "🕐 修改时区", "🕐 Change timezone"), callback_data="ux:settings:timezone")],
        [InlineKeyboardButton(pick(lang, "⬅️ 主菜单", "⬅️ Main menu"), callback_data="ux:menu")],
    ])
    return text, _markup(rows)


def cron_detail(user_id: int, token: str, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    tasks = cache.get_cron_tasks(user_id)
    task = next((item for item in tasks if stable_token(item["name"]) == token), None)
    if task is None:
        return cron_panel(user_id, lang)
    timezone = get_user_settings(user_id).get("timezone", "Asia/Shanghai")
    next_run = next_run_at(task["cron_expression"], timezone)
    next_text = next_run.strftime("%Y-%m-%d %H:%M") if next_run else pick(lang, "未来 32 天内无匹配", "No match in the next 32 days")
    text = pick(
        lang,
        f"⏰ **{task['name']}**\n\n状态：{'启用' if task.get('enabled', True) else '暂停'}\n计划：{describe_cron(task['cron_expression'], lang=lang)}\n表达式：`{task['cron_expression']}`\n时区：`{timezone}`\n下次：`{next_text}`\n上次：`{task.get('last_run_at') or '—'}`\n\n提示词：\n{task['prompt'][:800]}",
        f"⏰ **{task['name']}**\n\nStatus: {'enabled' if task.get('enabled', True) else 'paused'}\nSchedule: {describe_cron(task['cron_expression'], lang=lang)}\nExpression: `{task['cron_expression']}`\nTimezone: `{timezone}`\nNext: `{next_text}`\nLast: `{task.get('last_run_at') or '—'}`\n\nPrompt:\n{task['prompt'][:800]}",
    )
    rows = [
        [InlineKeyboardButton(pick(lang, "▶️ 立即测试", "▶️ Run now"), callback_data=f"ux:cron:run:{token}"), InlineKeyboardButton(pick(lang, "⏯ 启用/暂停", "⏯ Toggle"), callback_data=f"ux:cron:toggle:{token}")],
        [InlineKeyboardButton(pick(lang, "🗑 删除", "🗑 Delete"), callback_data=f"ux:cron:delete:{token}"), InlineKeyboardButton(pick(lang, "⬅️ 列表", "⬅️ List"), callback_data="ux:cron")],
    ]
    return text, _markup(rows)


def confirmation(text: str, yes_callback: str, back_callback: str, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    return text, _markup([[
        InlineKeyboardButton(pick(lang, "确认", "Confirm"), callback_data=yes_callback),
        InlineKeyboardButton(pick(lang, "取消", "Cancel"), callback_data=back_callback),
    ]])


def stop_keyboard(lang: str, *, user_id: int | None = None) -> InlineKeyboardMarkup:
    callback = f"ux:stop:{user_id}" if user_id is not None else "ux:stop"
    return _markup([[InlineKeyboardButton(pick(lang, "⏹ 停止生成", "⏹ Stop generating"), callback_data=callback)]])
