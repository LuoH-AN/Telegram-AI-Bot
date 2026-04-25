"""Platform-specific message delivery helpers for cron results."""

from __future__ import annotations

import asyncio
import logging

from .state import get_main_loop

logger = logging.getLogger(__name__)


def _detect_platform(bot) -> str:
    if hasattr(bot, "send_message"):
        return "Telegram"
    if hasattr(bot, "send_wechat_text"):
        return "WeChat"
    return "this platform"


def _send_telegram(bot, chat_id: int, text: str, loop) -> None:
    from telegram.constants import ParseMode
    from utils.formatters import markdown_to_telegram_html, split_message

    html_text = markdown_to_telegram_html(text)
    chunks = split_message(html_text, max_length=4096)
    for chunk in chunks:
        future = asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML),
            loop,
        )
        future.result(timeout=60)


def _send_wechat(bot, chat_id: int, text: str, loop) -> None:
    future = asyncio.run_coroutine_threadsafe(bot.send_wechat_text(chat_id, text), loop)
    future.result(timeout=60)


def _send_message(bot, chat_id: int, text: str) -> None:
    loop = get_main_loop()
    if loop is None or loop.is_closed():
        logger.error("Main event loop not available, cannot send cron message")
        return

    if hasattr(bot, "send_message"):
        _send_telegram(bot, chat_id, text, loop)
    elif hasattr(bot, "send_wechat_text"):
        _send_wechat(bot, chat_id, text, loop)
    else:
        logger.error("Unsupported bot type for cron delivery: %s", type(bot).__name__)
