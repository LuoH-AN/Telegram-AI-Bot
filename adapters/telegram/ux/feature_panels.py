"""Feature-center panels for command capabilities exposed as buttons."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from domain.services import get_current_persona_name, get_memories
from infrastructure.config import is_admin
from infrastructure.tools.skills.manager import get_skill_manager

from .locale import pick
from .tokens import stable_token

PAGE_SIZE = 8


def _markup(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


def feature_panel(user_id: int, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    text = pick(
        lang,
        "🧰 **功能中心**\n\n"
        "这里集中管理不常用但重要的功能。会删除数据或重启服务的操作都会再次确认。",
        "🧰 **Feature center**\n\n"
        "Less-frequent but important actions live here. Anything that deletes data or restarts the service requires confirmation.",
    )
    rows = [
        [
            InlineKeyboardButton(pick(lang, "🧠 管理长期记忆", "🧠 Manage memories"), callback_data="ux:memory"),
            InlineKeyboardButton(pick(lang, "🔌 管理技能", "🔌 Manage skills"), callback_data="ux:skills"),
        ],
        [
            InlineKeyboardButton(pick(lang, "🟢 查看运行状态", "🟢 View runtime status"), callback_data="ux:status"),
            InlineKeyboardButton(pick(lang, "📤 导出当前会话", "📤 Export current chat"), callback_data="ux:chat:export"),
        ],
        [InlineKeyboardButton(pick(lang, "🧹 清空当前会话", "🧹 Clear current chat"), callback_data="ux:confirm:clear_chat")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(pick(lang, "🛡 管理员操作", "🛡 Administrator actions"), callback_data="ux:admin")])
    rows.append([InlineKeyboardButton(pick(lang, "⬅️ 返回主菜单", "⬅️ Back to main menu"), callback_data="ux:menu")])
    return text, _markup(rows)


def memory_panel(user_id: int, lang: str, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    memories = get_memories(user_id)
    pages = max(1, (len(memories) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * PAGE_SIZE
    page_memories = memories[start:start + PAGE_SIZE]
    if memories:
        lines = [pick(lang, "🧠 **长期记忆**", "🧠 **Long-term memories**"), ""]
        for index, memory in enumerate(page_memories, start + 1):
            content = " ".join(str(memory.get("content", "")).split())
            lines.append(f"{index}. {content[:120]}{'…' if len(content) > 120 else ''}")
        lines.append("")
        lines.append(pick(lang, f"第 {page + 1}/{pages} 页 · 选择编号可删除单条记忆。", f"Page {page + 1}/{pages} · Select a numbered item to delete one memory."))
        text = "\n".join(lines)
    else:
        text = pick(
            lang,
            "🧠 **长期记忆**\n\n目前没有保存的记忆。可保存稳定偏好、个人信息或长期项目约束。\n请勿保存密码、API Key 或临时任务。",
            "🧠 **Long-term memories**\n\nNo memories are saved. You can store stable preferences, personal facts, or long-term project constraints.\nDo not store passwords, API keys, or temporary tasks.",
        )
    indexes = list(range(start + 1, start + len(page_memories) + 1))
    rows = [[InlineKeyboardButton(f"🗑 {index}", callback_data=f"ux:memory:delete:{index}") for index in indexes[i:i + 4]] for i in range(0, len(indexes), 4)]
    if pages > 1:
        rows.append([
            InlineKeyboardButton("◀️", callback_data=f"ux:memory:page:{max(0, page - 1)}"),
            InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="ux:noop"),
            InlineKeyboardButton("▶️", callback_data=f"ux:memory:page:{min(pages - 1, page + 1)}"),
        ])
    rows.extend([
        [InlineKeyboardButton(pick(lang, "➕ 添加长期记忆", "➕ Add memory"), callback_data="ux:memory:add")],
        [InlineKeyboardButton(pick(lang, "🧹 清空全部记忆", "🧹 Clear all memories"), callback_data="ux:memory:clear")],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回功能中心", "⬅️ Back to feature center"), callback_data="ux:features")],
    ])
    return text, _markup(rows)


def skills_panel(user_id: int, lang: str, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    manager = get_skill_manager()
    skills = sorted(manager.list_manifests(user_id), key=lambda item: item.name.casefold())
    pages = max(1, (len(skills) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    page_skills = skills[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    text = pick(
        lang,
        f"🔌 **技能管理**\n\n共 {len(skills)} 个可用技能 · 第 {page + 1}/{pages} 页。启用的技能会向 AI 提供额外说明或工具能力。",
        f"🔌 **Skill management**\n\n{len(skills)} skill(s) available · page {page + 1}/{pages}. Enabled skills provide the AI with additional instructions or tool capabilities.",
    )
    rows = []
    for skill in page_skills:
        enabled = manager.is_enabled(skill.name, user_id)
        rows.append([InlineKeyboardButton(
            f"{'✅' if enabled else '⚪'} {skill.name[:38]}",
            callback_data=f"ux:skill:view:{stable_token(skill.name)}",
        )])
    if pages > 1:
        rows.append([
            InlineKeyboardButton("◀️", callback_data=f"ux:skills:page:{max(0, page - 1)}"),
            InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="ux:noop"),
            InlineKeyboardButton("▶️", callback_data=f"ux:skills:page:{min(pages - 1, page + 1)}"),
        ])
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(pick(lang, "➕ 安装新技能", "➕ Install a skill"), callback_data="ux:skill:install")])
    rows.append([InlineKeyboardButton(pick(lang, "⬅️ 返回功能中心", "⬅️ Back to feature center"), callback_data="ux:features")])
    return text, _markup(rows)


def skill_detail(user_id: int, token: str, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    manager = get_skill_manager()
    skill = next((item for item in manager.list_manifests(user_id) if stable_token(item.name) == token), None)
    if skill is None:
        return skills_panel(user_id, lang)
    enabled = manager.is_enabled(skill.name, user_id)
    enabled_text = pick(lang, "✅ 已启用", "✅ Enabled") if enabled else pick(lang, "⚪ 已停用", "⚪ Disabled")
    kind = pick(lang, "内置技能", "Built-in skill") if skill.is_builtin else pick(lang, "外部技能", "External skill")
    capabilities = ", ".join(skill.capabilities) or pick(lang, "仅提示词", "Prompt only")
    text = pick(
        lang,
        f"🔌 **技能：{skill.name}**\n\n"
        f"状态：{enabled_text}\n"
        f"类型：{kind}\n"
        f"版本：`{skill.version}`\n"
        f"能力：{capabilities}\n\n"
        f"{skill.description or '暂无说明'}",
        f"🔌 **Skill: {skill.name}**\n\n"
        f"Status: {enabled_text}\n"
        f"Type: {kind}\n"
        f"Version: `{skill.version}`\n"
        f"Capabilities: {capabilities}\n\n"
        f"{skill.description or 'No description provided.'}",
    )
    rows = [[InlineKeyboardButton(
        pick(lang, "⚪ 停用此技能", "⚪ Disable this skill") if enabled else pick(lang, "✅ 启用此技能", "✅ Enable this skill"),
        callback_data=f"ux:skill:toggle:{token}",
    )]]
    if not skill.is_builtin:
        rows.append([InlineKeyboardButton(pick(lang, "🗑 移除此技能", "🗑 Remove this skill"), callback_data=f"ux:skill:remove:{token}")])
    rows.append([InlineKeyboardButton(pick(lang, "⬅️ 返回技能列表", "⬅️ Back to skills"), callback_data="ux:skills")])
    return text, _markup(rows)


def admin_panel(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    text = pick(
        lang,
        "🛡 **管理员操作**\n\n更新会从远程主分支拉取代码；安全重启会先同步运行数据。两项操作都会再次确认。",
        "🛡 **Administrator actions**\n\nUpdate pulls code from the remote main branch. Safe restart syncs runtime data first. Both actions require confirmation.",
    )
    rows = [
        [InlineKeyboardButton(pick(lang, "⬇️ 检查并应用更新", "⬇️ Check and apply updates"), callback_data="ux:admin:update")],
        [InlineKeyboardButton(pick(lang, "🔄 安全重启服务", "🔄 Safely restart service"), callback_data="ux:admin:restart")],
        [InlineKeyboardButton(pick(lang, "⬅️ 返回功能中心", "⬅️ Back to feature center"), callback_data="ux:features")],
    ]
    return text, _markup(rows)
