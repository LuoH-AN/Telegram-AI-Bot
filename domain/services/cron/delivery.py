"""Delivery of cron results via the injected platform port (no adapter dependency)."""

from __future__ import annotations

import logging

from .state import get_delivery_send, get_delivery_platform

logger = logging.getLogger(__name__)


def platform_label(bot) -> str:
    """Platform hint for the system prompt. Prefers the registered port."""
    if get_delivery_send() is not None:
        return get_delivery_platform()
    if hasattr(bot, "send_message"):
        return "Telegram"
    return "this platform"


def _send_message(bot, chat_id: int, text: str) -> None:
    send = get_delivery_send()
    if send is not None:
        send(chat_id, text)
        return
    logger.error("No delivery port registered; cannot send cron message to chat=%s", chat_id)
