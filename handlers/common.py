"""Common utilities for handlers."""

from telegram import Update
from telegram.ext import ContextTypes


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
