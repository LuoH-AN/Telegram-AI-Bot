"""Platform-specific message delivery helpers for cron results."""

from __future__ import annotations

import asyncio
import logging

from .state import get_main_loop

logger = logging.getLogger(__name__)


def _detect_platform(bot) -> str:
    if hasattr(bot, "send_message"):
        return "Telegram"
    return "this platform"


def _send_telegram(bot, chat_id: int, text: str, loop) -> None:
    from telegram.constants import ParseMode
    from adapters.telegram.bot_api import send_rich_message
    from infrastructure.config import TELEGRAM_RICH_MESSAGES
    from shared.utils.format import (
        build_rich_message,
        markdown_to_telegram_html,
        should_use_rich_message,
        split_message,
    )

    if TELEGRAM_RICH_MESSAGES and should_use_rich_message(text):
        rich_message = build_rich_message(text)
        if rich_message:
            future = asyncio.run_coroutine_threadsafe(send_rich_message(chat_id, rich_message), loop)
            if future.result(timeout=60):
                return

    chunks = split_message(text, max_length=4096)
    for chunk in chunks:
        html_text = markdown_to_telegram_html(chunk)
        future = asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=chat_id, text=html_text, parse_mode=ParseMode.HTML),
            loop,
        )
        future.result(timeout=60)


def _send_message(bot, chat_id: int, text: str) -> None:
    loop = get_main_loop()
    if loop is None or loop.is_closed():
        logger.error("Main event loop not available, cannot send cron message")
        return

    if hasattr(bot, "send_message"):
        _send_telegram(bot, chat_id, text, loop)
    else:
        logger.error("Unsupported bot type for cron delivery: %s", type(bot).__name__)
