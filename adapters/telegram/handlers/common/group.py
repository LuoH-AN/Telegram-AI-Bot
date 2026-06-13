"""Media-group buffering and caption helpers."""

import asyncio
import threading
import time

from telegram import Message

_MEDIA_GROUP_WAIT_SECONDS = 1.0
_MEDIA_GROUP_COMPLETE_TTL_SECONDS = 10.0
_MEDIA_GROUP_LOCK = threading.Lock()
_MEDIA_GROUP_BUFFER: dict[tuple[int, str], list[Message]] = {}
_MEDIA_GROUP_COMPLETED: dict[tuple[int, str], float] = {}


def _prune_completed_media_groups(now: float) -> None:
    expired = [key for key, expires_at in _MEDIA_GROUP_COMPLETED.items() if expires_at <= now]
    for key in expired:
        del _MEDIA_GROUP_COMPLETED[key]


async def collect_media_group_messages(message: Message) -> list[Message] | None:
    media_group_id = message.media_group_id
    if not media_group_id:
        return [message]

    key = (message.chat_id, media_group_id)
    is_leader = False
    with _MEDIA_GROUP_LOCK:
        _prune_completed_media_groups(time.monotonic())
        if key in _MEDIA_GROUP_COMPLETED:
            return None
        if key not in _MEDIA_GROUP_BUFFER:
            _MEDIA_GROUP_BUFFER[key] = [message]
            is_leader = True
        else:
            existing_ids = {item.message_id for item in _MEDIA_GROUP_BUFFER[key]}
            if message.message_id not in existing_ids:
                _MEDIA_GROUP_BUFFER[key].append(message)

    if not is_leader:
        return None
    await asyncio.sleep(_MEDIA_GROUP_WAIT_SECONDS)

    with _MEDIA_GROUP_LOCK:
        grouped = _MEDIA_GROUP_BUFFER.pop(key, [])
        _MEDIA_GROUP_COMPLETED[key] = time.monotonic() + _MEDIA_GROUP_COMPLETE_TTL_SECONDS

    grouped.sort(key=lambda item: item.message_id)
    return grouped


def build_media_caption(
    grouped_messages: list[Message],
    *,
    bot_username: str | None,
    reply_message: Message | None,
) -> str:
    caption = next((msg.caption for msg in grouped_messages if msg.caption), "") or ""
    if bot_username and f"@{bot_username}" in caption:
        caption = caption.replace(f"@{bot_username}", "").strip()
    if not reply_message:
        return caption

    quoted_text = reply_message.text or reply_message.caption or ""
    if not quoted_text:
        return caption
    sender = reply_message.from_user
    sender_name = sender.first_name if sender else "Unknown"
    prefix = f"[Quoted message from {sender_name}]:\n{quoted_text}"
    return f"{prefix}\n\n{caption}" if caption else prefix

