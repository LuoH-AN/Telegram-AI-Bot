"""Shared constants for Telegram rate limiter."""

from __future__ import annotations

from typing import Any

QUEUED_ENDPOINTS = {
    "copyMessage",
    "deleteMessage",
    "editMessageCaption",
    "editMessageLiveLocation",
    "editMessageMedia",
    "editMessageReplyMarkup",
    "editMessageText",
    "forwardMessage",
    "sendAnimation",
    "sendAudio",
    "sendChatAction",
    "sendContact",
    "sendDice",
    "sendDocument",
    "sendInvoice",
    "sendLocation",
    "sendMediaGroup",
    "sendMessage",
    "sendPhoto",
    "sendPoll",
    "sendSticker",
    "sendVenue",
    "sendVideo",
    "sendVideoNote",
    "sendVoice",
    "stopMessageLiveLocation",
}

LOW_PRIORITY_ENDPOINTS = {"sendChatAction"}

EDIT_ENDPOINTS = {
    "editMessageCaption",
    "editMessageMedia",
    "editMessageReplyMarkup",
    "editMessageText",
}


def to_chat_key(chat_id: Any) -> int | str | None:
    """Normalize chat_id for per-chat throttling."""
    if chat_id is None:
        return None
    if isinstance(chat_id, int):
        return chat_id
    if isinstance(chat_id, str):
        try:
            return int(chat_id)
        except ValueError:
            return chat_id
    return str(chat_id)
