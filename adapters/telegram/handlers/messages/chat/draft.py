"""Native Telegram draft streaming helpers."""

from __future__ import annotations

from telegram.constants import ChatType
from telegram.constants import ParseMode

from adapters.telegram.bot_api import send_message_draft as raw_send_message_draft
from adapters.telegram.bot_api import send_rich_message_draft
from shared.utils.format import build_rich_message, markdown_to_telegram_html, should_use_rich_message


def can_use_native_draft(update) -> bool:
    message = update.effective_message
    if not update.effective_chat or not message:
        return False
    if getattr(message, "business_connection_id", None):
        return False
    return update.effective_chat.type == ChatType.PRIVATE


def build_draft_id(update) -> int:
    chat_id = int(update.effective_chat.id)
    message_id = int(update.effective_message.message_id or 0)
    draft_id = abs((chat_id * 1_000_003 + message_id) % 2_147_483_647)
    return draft_id or 1


async def send_native_draft(update, context, draft_id: int, text: str) -> bool:
    if not can_use_native_draft(update):
        return False
    thread_id = getattr(update.effective_message, "message_thread_id", None)
    rich_message = build_rich_message(text) if should_use_rich_message(text) else None
    if rich_message and await send_rich_message_draft(
        update.effective_chat.id,
        draft_id,
        rich_message,
        message_thread_id=thread_id,
    ):
        return True
    draft_text = _draft_html(text)
    sdk_method = getattr(context.bot, "send_message_draft", None)
    if sdk_method:
        try:
            return bool(await sdk_method(
                chat_id=update.effective_chat.id,
                draft_id=draft_id,
                text=draft_text,
                message_thread_id=thread_id,
                parse_mode=ParseMode.HTML,
            ))
        except Exception:
            return False
    return await raw_send_message_draft(
        update.effective_chat.id,
        draft_id,
        draft_text,
        message_thread_id=thread_id,
    )


def _draft_html(text: str) -> str:
    raw = (text or "").rstrip()
    if len(raw) > 3900:
        raw = raw[:3900].rstrip() + "\n..."
    return markdown_to_telegram_html(raw)
