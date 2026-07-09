"""Telegram-side delivery for cron results — registered as the cron delivery port.

Lives in the adapter layer (knows Telegram). domain.services.cron is wired to
its generic port via set_delivery_port, keeping the cross-ring dependency
adapters -> domain only (never domain -> adapters).
"""

from __future__ import annotations

import asyncio
import logging

from telegram.constants import ParseMode

from adapters.telegram.bot_api import send_rich_message
from infrastructure.config import TELEGRAM_RICH_MESSAGES
from shared.utils.format import (
    build_rich_message,
    markdown_to_telegram_html,
    should_use_rich_message,
    split_message,
)

logger = logging.getLogger(__name__)
PLATFORM = "Telegram"


def _get_loop():
    from domain.services.cron import get_main_loop

    return get_main_loop()


def send_cron_message(bot, chat_id: int, text: str) -> None:
    loop = _get_loop()
    if loop is None or loop.is_closed():
        logger.error("Main event loop not available, cannot send cron message")
        return

    if TELEGRAM_RICH_MESSAGES and should_use_rich_message(text):
        rich_message = build_rich_message(text)
        if rich_message:
            future = asyncio.run_coroutine_threadsafe(send_rich_message(chat_id, rich_message), loop)
            if future.result(timeout=60):
                return

    for chunk in split_message(text, max_length=4096):
        html_text = markdown_to_telegram_html(chunk)
        future = asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=chat_id, text=html_text, parse_mode=ParseMode.HTML),
            loop,
        )
        future.result(timeout=60)


def register(bot) -> None:
    """Register this Telegram delivery as the cron port."""
    from domain.services.cron.state import set_delivery_port

    set_delivery_port(lambda chat_id, text: send_cron_message(bot, chat_id, text), PLATFORM)
