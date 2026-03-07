"""Common utilities for handlers."""

import asyncio
import threading
import time
from dataclasses import dataclass

from telegram import Message
from telegram import Update
from telegram.ext import ContextTypes

from services import has_api_key, get_current_persona_name, get_remaining_tokens, ensure_session
from utils.platform_parity import (
    build_api_key_required_message,
    build_retry_message,
    build_token_limit_reached_message,
    format_log_context,
)

_MEDIA_GROUP_WAIT_SECONDS = 1.0
_MEDIA_GROUP_COMPLETE_TTL_SECONDS = 10.0
_MEDIA_GROUP_LOCK = threading.Lock()
_MEDIA_GROUP_BUFFER: dict[tuple[int, str], list[Message]] = {}
_MEDIA_GROUP_COMPLETED: dict[tuple[int, str], float] = {}


@dataclass(frozen=True)
class MediaRequestContext:
    grouped_messages: list[Message]
    caption: str
    persona_name: str
    session_id: int


def _prune_completed_media_groups(now: float) -> None:
    expired = [key for key, expires_at in _MEDIA_GROUP_COMPLETED.items() if expires_at <= now]
    for key in expired:
        del _MEDIA_GROUP_COMPLETED[key]


def get_log_context(update: Update) -> str:
    """Return a log prefix string with user and optional group context."""
    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id if user else 0
    if chat and chat.type != "private":
        return format_log_context(platform="telegram", user_id=user_id, scope="group", chat_id=chat.id)
    chat_id = chat.id if chat else 0
    return format_log_context(platform="telegram", user_id=user_id, scope="private", chat_id=chat_id)


async def should_respond_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if bot should respond in a group chat.

    Returns True if:
    - It's a private chat (always respond)
    - Message is a reply to the bot's message
    - Bot is mentioned (@botusername) in the message
    """
    if update.effective_chat.type == "private":
        return True

    message = update.message
    bot_username = context.bot.username

    if message.reply_to_message:
        if message.reply_to_message.from_user.id == context.bot.id:
            return True

    if message.text and bot_username:
        if f"@{bot_username}" in message.text:
            return True

    if message.caption and bot_username:
        if f"@{bot_username}" in message.caption:
            return True

    entities = message.entities or message.caption_entities or []
    for entity in entities:
        if entity.type == "mention":
            text = message.text or message.caption or ""
            mention = text[entity.offset:entity.offset + entity.length]
            if mention == f"@{bot_username}":
                return True

    return False


async def collect_media_group_messages(message: Message) -> list[Message] | None:
    """Collect all messages in the same media group and return once for the leader update.

    Returns:
        - [message] for non-media-group updates
        - list[Message] for the first update of a media group (after a short wait)
        - None for follower updates that should be ignored
    """
    media_group_id = message.media_group_id
    if not media_group_id:
        return [message]

    key = (message.chat_id, media_group_id)
    is_leader = False
    now = time.monotonic()

    with _MEDIA_GROUP_LOCK:
        _prune_completed_media_groups(now)
        if key in _MEDIA_GROUP_COMPLETED:
            return None
        if key not in _MEDIA_GROUP_BUFFER:
            _MEDIA_GROUP_BUFFER[key] = [message]
            is_leader = True
        else:
            existing_ids = {msg.message_id for msg in _MEDIA_GROUP_BUFFER[key]}
            if message.message_id not in existing_ids:
                _MEDIA_GROUP_BUFFER[key].append(message)

    if not is_leader:
        return None

    await asyncio.sleep(_MEDIA_GROUP_WAIT_SECONDS)

    with _MEDIA_GROUP_LOCK:
        grouped = _MEDIA_GROUP_BUFFER.pop(key, [])
        _MEDIA_GROUP_COMPLETED[key] = time.monotonic() + _MEDIA_GROUP_COMPLETE_TTL_SECONDS

    grouped.sort(key=lambda msg: msg.message_id)
    return grouped


def build_media_caption(
    grouped_messages: list[Message],
    *,
    bot_username: str | None,
    reply_message: Message | None,
) -> str:
    """Build caption text from grouped media, mention cleanup, and quoted reply context."""
    caption = next((msg.caption for msg in grouped_messages if msg.caption), "") or ""

    if bot_username and f"@{bot_username}" in caption:
        caption = caption.replace(f"@{bot_username}", "").strip()

    if reply_message:
        quoted_text = reply_message.text or reply_message.caption or ""
        if quoted_text:
            sender = reply_message.from_user
            sender_name = sender.first_name if sender else "Unknown"
            prefix = f"[Quoted message from {sender_name}]:\n{quoted_text}"
            caption = f"{prefix}\n\n{caption}" if caption else prefix

    return caption


async def preflight_media_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> MediaRequestContext | None:
    """Validate and normalize media batch request before specific media processing."""
    if not await should_respond_in_group(update, context):
        return None

    grouped_messages = await collect_media_group_messages(update.message)
    if grouped_messages is None:
        return None

    if any(message.forward_origin for message in grouped_messages):
        return None

    user_id = update.effective_user.id
    if not has_api_key(user_id):
        await update.message.reply_text(build_api_key_required_message("/"))
        return None

    persona_name = get_current_persona_name(user_id)
    remaining = get_remaining_tokens(user_id, persona_name)
    if remaining is not None and remaining <= 0:
        await update.message.reply_text(build_token_limit_reached_message("/", persona_name))
        return None

    session_id = ensure_session(user_id, persona_name)
    if session_id is None:
        await update.message.reply_text(build_retry_message())
        return None

    caption = build_media_caption(
        grouped_messages,
        bot_username=context.bot.username,
        reply_message=update.message.reply_to_message,
    )
    return MediaRequestContext(
        grouped_messages=grouped_messages,
        caption=caption,
        persona_name=persona_name,
        session_id=session_id,
    )
