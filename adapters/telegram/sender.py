"""Telegram OutboundSender — wraps Update/Context for media replies."""

from __future__ import annotations

import asyncio
import html
import io
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from adapters.telegram.outbound import OutboundSender
from infrastructure.tools.approval import approval_broker, is_permanently_allowed, rule_label
from shared.utils.format import markdown_to_telegram_html

from .ux.locale import language, pick


def _buf(data: bytes, filename: str) -> io.BytesIO:
    buf = io.BytesIO(data)
    buf.name = filename
    return buf


def _caption(text: str) -> str | None:
    return markdown_to_telegram_html(text) or None


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\b\s*=\s*)([^\s;&|]+)"
)


def _approval_preview(command: str) -> str:
    """隐藏命令中常见的内联凭据，同时保留足够的审批上下文。"""
    return _SECRET_ASSIGNMENT.sub(r"\1<已隐藏>", command)


class TelegramOutbound(OutboundSender):
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *, session_id: int | None = None):
        self.update = update
        self.context = context
        self.message = update.effective_message
        self.session_id = session_id

    async def send_image(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.message.reply_photo(
            photo=_buf(data, filename),
            caption=_caption(caption),
            parse_mode=ParseMode.HTML,
        )

    async def send_document(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.message.reply_document(
            document=_buf(data, filename),
            filename=filename,
            caption=_caption(caption),
            parse_mode=ParseMode.HTML,
        )

    async def send_voice(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.message.reply_voice(
            voice=_buf(data, filename),
            caption=_caption(caption),
            parse_mode=ParseMode.HTML,
        )

    async def send_video(self, data: bytes, *, filename: str, caption: str = "") -> None:
        await self.message.reply_video(
            video=_buf(data, filename),
            caption=_caption(caption),
            parse_mode=ParseMode.HTML,
        )

    async def request_terminal_approval(self, *, command: str, cwd: str, timeout: float = 300) -> str:
        """发送审批按钮，并在原工具协程中等待用户选择。"""
        user = self.update.effective_user
        chat = self.update.effective_chat
        if user is None or chat is None or self.message is None:
            return "unavailable"
        lang = language(self.update, self.context)
        session_key = f"telegram:{chat.id}:{user.id}:{self.session_id or 'default'}"
        if approval_broker.is_session_allowed(session_key, command, cwd):
            return "approve"
        if is_permanently_allowed(user.id, command, cwd):
            return "approve"
        pending = approval_broker.create(
            user_id=user.id,
            chat_id=chat.id,
            command=command,
            cwd=cwd,
            lang=lang,
            session_key=session_key,
        )
        rows = [
                [
                    InlineKeyboardButton(
                        pick(lang, "✅ 一次允许", "✅ Allow once"),
                        callback_data=f"term:{pending.approval_id}:once",
                    ),
                ],
        ]
        if pending.prefix_rule is not None:
            rows[0].append(InlineKeyboardButton(
                pick(lang, "🔁 本会话允许此前缀", "🔁 Allow prefix for session"),
                callback_data=f"term:{pending.approval_id}:session",
            ))
            rows.append([
                    InlineKeyboardButton(
                        pick(lang, "🔒 永久允许此前缀", "🔒 Always allow prefix"),
                        callback_data=f"term:{pending.approval_id}:always",
                    ),
            ])
        rows.append([
                    InlineKeyboardButton(
                        pick(lang, "❌ 拒绝", "❌ Deny"),
                        callback_data=f"term:{pending.approval_id}:deny",
                    ),
        ])
        keyboard = InlineKeyboardMarkup(rows)
        preview = _approval_preview(command)
        if len(preview) > 3000:
            preview = preview[:3000] + "…"
        text = pick(
            lang,
            "⚠️ <b>终端命令需要批准</b>\n\n"
            f"<pre>{html.escape(preview)}</pre>\n\n"
            f"工作目录：<code>{html.escape(cwd)}</code>\n"
            f"重复授权范围：<code>{html.escape(rule_label(pending.prefix_rule) or '不可创建安全前缀，仅可单次允许')}</code>\n"
            "本会话/永久授权按上方命令前缀匹配；复合或高风险命令只支持单次允许。",
            "⚠️ <b>Terminal command requires approval</b>\n\n"
            f"<pre>{html.escape(preview)}</pre>\n\n"
            f"Working directory: <code>{html.escape(cwd)}</code>\n"
            f"Repeat-approval scope: <code>{html.escape(rule_label(pending.prefix_rule) or 'No safe prefix; allow once only')}</code>\n"
            "Session/permanent approval matches the prefix above. Compound or high-risk commands support one-time approval only.",
        )
        try:
            approval_message = await self.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception:
            approval_broker.discard(pending.approval_id)
            raise

        try:
            choice = await approval_broker.wait(pending, timeout)
        except asyncio.CancelledError:
            try:
                await approval_message.edit_text(
                    pick(lang, "🛑 当前请求已取消，命令未执行。", "🛑 The request was cancelled; the command was not run."),
                    reply_markup=None,
                )
            except Exception:
                pass
            raise
        if choice == "timeout":
            try:
                await approval_message.edit_text(
                    pick(lang, "⌛ 终端审批已超时，命令未执行。", "⌛ Terminal approval timed out; the command was not run."),
                    reply_markup=None,
                )
            except Exception:
                pass
        return choice
