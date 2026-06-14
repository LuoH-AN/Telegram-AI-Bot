"""Telegram rich text helpers."""

from __future__ import annotations

from telegram.constants import ParseMode

from adapters.telegram.bot_api import send_rich_message
from infrastructure.config import TELEGRAM_RICH_MESSAGES
from shared.utils.format import build_rich_message, should_use_rich_message
from shared.utils.format import markdown_to_telegram_html


def telegram_html(text: str) -> str:
    return markdown_to_telegram_html(text)


async def reply_rich_text(message, text: str, **kwargs):
    return await message.reply_text(telegram_html(text), parse_mode=ParseMode.HTML, **kwargs)


async def edit_rich_text(message, text: str, **kwargs):
    return await message.edit_text(telegram_html(text), parse_mode=ParseMode.HTML, **kwargs)


async def edit_query_rich_text(query, text: str, **kwargs):
    return await query.edit_message_text(telegram_html(text), parse_mode=ParseMode.HTML, **kwargs)


async def send_rich_text(message, text: str, *, reply: bool = True) -> bool:
    if not TELEGRAM_RICH_MESSAGES or not should_use_rich_message(text):
        return False
    rich_message = build_rich_message(text)
    if not rich_message:
        return False
    reply_parameters = None
    if reply:
        reply_parameters = {"message_id": message.message_id, "allow_sending_without_reply": True}
    topic = getattr(message, "direct_messages_topic", None)
    result = await send_rich_message(
        message.chat.id,
        rich_message,
        business_connection_id=getattr(message, "business_connection_id", None),
        direct_messages_topic_id=getattr(topic, "topic_id", None),
        message_thread_id=getattr(message, "message_thread_id", None),
        reply_parameters=reply_parameters,
    )
    return bool(result)
