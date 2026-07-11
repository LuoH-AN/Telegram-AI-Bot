"""Telegram 终端审批按钮回调。"""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from infrastructure.config import is_admin
from infrastructure.tools.approval import add_permanent_approval, approval_broker, rule_label

from .ux.locale import language, pick

logger = logging.getLogger(__name__)


async def terminal_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    if query is None or user is None or chat is None:
        return
    parts = (query.data or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "term" or parts[2] not in {"once", "session", "always", "deny"}:
        await query.answer("Invalid approval button.", show_alert=True)
        return

    approval_id, choice = parts[1], parts[2]
    pending = approval_broker.get(approval_id)
    lang = pending.lang if pending is not None else language(update, context)
    if not is_admin(user.id):
        await query.answer(pick(lang, "只有机器人管理员可以批准终端命令。", "Only bot administrators can approve terminal commands."), show_alert=True)
        return

    if pending is None or pending.future.done() or pending.processing:
        await query.answer(pick(lang, "该审批已处理或已过期。", "This approval was already resolved or has expired."), show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    if pending.user_id != int(user.id) or pending.chat_id != int(chat.id):
        await query.answer(pick(lang, "只有发起该请求的用户才能操作。", "Only the user who started this request can use this button."), show_alert=True)
        return
    pending.processing = True

    if choice in {"session", "always"} and pending.prefix_rule is None:
        pending.processing = False
        await query.answer(pick(lang, "这条命令包含高风险或复合 Shell 语法，只能单次允许。", "This command uses high-risk or compound shell syntax and can only be allowed once."), show_alert=True)
        return

    if choice == "session":
        approval_broker.allow_session(pending)
    if choice == "always":
        try:
            await asyncio.to_thread(add_permanent_approval, user.id, pending.prefix_rule)
        except Exception:
            pending.processing = False
            logger.exception("failed to persist terminal approval for user=%s", user.id)
            await query.answer(pick(lang, "永久授权保存失败，请重试或选择一次允许。", "Could not save permanent approval. Retry or choose Allow once."), show_alert=True)
            return

    result = approval_broker.resolve(
        approval_id,
        user_id=user.id,
        chat_id=chat.id,
        approve=choice != "deny",
    )
    if result.status == "missing":
        await query.answer(pick(lang, "该审批已处理或已过期。", "This approval was already resolved or has expired."), show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    labels = {
        "once": pick(lang, "✅ 已允许本次执行。", "✅ Approved for this execution."),
        "session": pick(lang, f"🔁 当前会话已允许命令前缀：`{rule_label(pending.prefix_rule)}`", f"🔁 Allowed for this session: `{rule_label(pending.prefix_rule)}`"),
        "always": pick(lang, f"🔒 已永久允许命令前缀：`{rule_label(pending.prefix_rule)}`", f"🔒 Always allowed: `{rule_label(pending.prefix_rule)}`"),
        "deny": pick(lang, "❌ 已拒绝，命令不会执行。", "❌ Denied; the command will not run."),
    }
    label = labels[choice]
    await query.answer(label)
    try:
        await query.edit_message_text(label, reply_markup=None)
    except Exception:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
