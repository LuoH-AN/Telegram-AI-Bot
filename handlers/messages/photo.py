"""Photo message handler with vision model."""

import base64
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from services import (
    has_api_key,
    get_remaining_tokens,
)
from utils import edit_message_safe
from handlers.common import (
    should_respond_in_group,
    get_log_context,
    collect_media_group_messages,
)

logger = logging.getLogger(__name__)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages with vision model."""
    if not await should_respond_in_group(update, context):
        return

    grouped_messages = await collect_media_group_messages(update.message)
    if grouped_messages is None:
        return

    if any(msg.forward_origin for msg in grouped_messages):
        return

    user_id = update.effective_user.id
    ctx = get_log_context(update)

    logger.info(
        "%s photo batch (%d item(s), caption: %s)",
        ctx,
        len(grouped_messages),
        (next((m.caption for m in grouped_messages if m.caption), "") or "")[:50],
    )

    if not has_api_key(user_id):
        await update.message.reply_text(
            "Please set your OpenAI API key first:\n/set api_key YOUR_API_KEY"
        )
        return

    remaining = get_remaining_tokens(user_id)
    if remaining is not None and remaining <= 0:
        await update.message.reply_text(
            "You've reached your token limit. "
            "Use /usage to check usage or /set token_limit <number> to increase it."
        )
        return

    caption = next((m.caption for m in grouped_messages if m.caption), "") or ""

    bot_username = context.bot.username
    if bot_username and f"@{bot_username}" in caption:
        caption = caption.replace(f"@{bot_username}", "").strip()

    reply_msg = update.message.reply_to_message
    if reply_msg:
        quoted_text = reply_msg.text or reply_msg.caption or ""
        if quoted_text:
            sender = reply_msg.from_user
            sender_name = sender.first_name if sender else "Unknown"
            prefix = f"[Quoted message from {sender_name}]:\n{quoted_text}"
            caption = f"{prefix}\n\n{caption}" if caption else prefix

    await update.message.chat.send_action(ChatAction.TYPING)
    bot_message = await update.message.reply_text("…")

    try:
        image_parts = []
        for msg in grouped_messages:
            if not msg.photo:
                continue
            photo = msg.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            image_bytes = await tg_file.download_as_bytearray()
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                }
            )

        if not image_parts:
            await edit_message_safe(bot_message, "Error. Please retry.")
            return

        user_content = list(image_parts)
        if caption:
            user_content.insert(0, {"type": "text", "text": caption})

        save_msg = "[Image]" if len(image_parts) == 1 else f"[Images x{len(image_parts)}]"
        if caption:
            save_msg += f" {caption}"

        # Delegate to chat handler for full streaming, thinking display, and tool support
        from handlers.messages.text import chat
        await chat(update, context, user_content=user_content, save_msg=save_msg, bot_message=bot_message)

    except Exception:
        logger.exception("%s error processing image", ctx)
        await edit_message_safe(bot_message, "Error. Please retry.")
