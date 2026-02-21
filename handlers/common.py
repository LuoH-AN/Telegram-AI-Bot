"""Common utilities for handlers."""

import asyncio
import threading

from telegram import Message
from telegram import Update
from telegram.ext import ContextTypes

_MEDIA_GROUP_WAIT_SECONDS = 1.0
_MEDIA_GROUP_LOCK = threading.Lock()
_MEDIA_GROUP_BUFFER: dict[tuple[int, str], list[Message]] = {}


def get_log_context(update: Update) -> str:
    """Return a log prefix string with user and optional group context."""
    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id if user else 0
    if chat and chat.type != "private":
        return f"[user={user_id} group={chat.id}]"
    return f"[user={user_id}]"


async def should_respond_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if bot should respond in a group chat.

    Returns True if:
    - It's a private chat (always respond)
    - Message is a reply to the bot's message
    - Bot is mentioned (@botusername) in the message
    """
    # Always respond in private chats
    if update.effective_chat.type == "private":
        return True

    # In group chats, check if bot is mentioned or replied to
    message = update.message
    bot_username = context.bot.username

    # Check if this is a reply to the bot's message
    if message.reply_to_message:
        if message.reply_to_message.from_user.id == context.bot.id:
            return True

    # Check if bot is mentioned in message text
    if message.text and bot_username:
        if f"@{bot_username}" in message.text:
            return True

    # Check if bot is mentioned in caption (for photos)
    if message.caption and bot_username:
        if f"@{bot_username}" in message.caption:
            return True

    # Check entities for mentions
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

    with _MEDIA_GROUP_LOCK:
        if key not in _MEDIA_GROUP_BUFFER:
            _MEDIA_GROUP_BUFFER[key] = [message]
            is_leader = True
        else:
            _MEDIA_GROUP_BUFFER[key].append(message)

    if not is_leader:
        return None

    await asyncio.sleep(_MEDIA_GROUP_WAIT_SECONDS)

    with _MEDIA_GROUP_LOCK:
        grouped = _MEDIA_GROUP_BUFFER.pop(key, [])

    grouped.sort(key=lambda m: m.message_id)
    return grouped
