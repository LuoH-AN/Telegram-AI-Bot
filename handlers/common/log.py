"""Logging and group-response helpers."""

from telegram import Update
from telegram.ext import ContextTypes

from utils.platform import format_log_context


def get_log_context(update: Update) -> str:
    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id if user else 0
    if chat and chat.type != "private":
        return format_log_context(platform="telegram", user_id=user_id, scope="group", chat_id=chat.id)
    chat_id = chat.id if chat else 0
    return format_log_context(platform="telegram", user_id=user_id, scope="private", chat_id=chat_id)


async def should_respond_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat.type == "private":
        return True

    message = update.message
    bot_username = context.bot.username
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        return True
    if message.text and bot_username and f"@{bot_username}" in message.text:
        return True
    if message.caption and bot_username and f"@{bot_username}" in message.caption:
        return True

    entities = message.entities or message.caption_entities or []
    raw_text = message.text or message.caption or ""
    for entity in entities:
        if entity.type != "mention":
            continue
        mention = raw_text[entity.offset:entity.offset + entity.length]
        if mention == f"@{bot_username}":
            return True
    return False

