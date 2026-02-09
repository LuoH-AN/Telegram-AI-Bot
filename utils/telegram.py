"""Telegram API interaction utilities."""

import asyncio
import logging

from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter

from config import MAX_MESSAGE_LENGTH
from .formatters import markdown_to_telegram_html, split_message

logger = logging.getLogger(__name__)


async def send_message_safe(message, text: str, reply: bool = True, **kwargs) -> list:
    """Send a message with HTML formatting, fallback to plain text if failed."""
    chunks = split_message(text)
    sent_messages = []

    for i, chunk in enumerate(chunks):
        html_chunk = markdown_to_telegram_html(chunk)
        try:
            # Try sending with HTML
            if reply and i == 0:
                msg = await message.reply_text(
                    html_chunk, parse_mode=ParseMode.HTML, **kwargs
                )
            else:
                msg = await message.chat.send_message(
                    html_chunk, parse_mode=ParseMode.HTML, **kwargs
                )
            sent_messages.append(msg)
        except BadRequest as e:
            # Fallback to plain text if HTML parsing fails
            logger.warning(f"HTML parse failed, using plain text: {e}")
            try:
                if reply and i == 0:
                    msg = await message.reply_text(chunk, **kwargs)
                else:
                    msg = await message.chat.send_message(chunk, **kwargs)
                sent_messages.append(msg)
            except Exception as e2:
                logger.error(f"Failed to send message: {e2}")

    return sent_messages


async def edit_message_safe(message, text: str) -> bool:
    """Edit a message with HTML formatting, fallback to plain text if failed."""
    # Truncate if too long for single message
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[: MAX_MESSAGE_LENGTH - 3] + "..."

    html_text = markdown_to_telegram_html(text)

    for attempt in range(2):
        try:
            await message.edit_text(html_text, parse_mode=ParseMode.HTML)
            return True
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return True
            # Fallback to plain text
            try:
                await message.edit_text(text)
                return True
            except RetryAfter as e2:
                await asyncio.sleep(e2.retry_after)
            except BadRequest as e2:
                if "not modified" in str(e2).lower():
                    return True
                logger.warning(f"Failed to edit message: {e2}")
                return False
    return False
