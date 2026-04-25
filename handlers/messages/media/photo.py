"""Photo message handler with vision model."""

import base64
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from handlers.common import (
    get_log_context,
    preflight_media_request,
)
from utils.platform import (
    build_retry_message,
)

logger = logging.getLogger(__name__)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages with vision model."""
    media_ctx = await preflight_media_request(update, context)
    if not media_ctx:
        return

    grouped_messages = media_ctx.grouped_messages
    caption = media_ctx.caption
    persona_name = media_ctx.persona_name
    session_id = media_ctx.session_id

    ctx = get_log_context(update)

    logger.info(
        "%s photo batch (%d item(s), caption: %s)",
        ctx,
        len(grouped_messages),
        (next((m.caption for m in grouped_messages if m.caption), "") or "")[:50],
    )

    await update.message.chat.send_action(ChatAction.TYPING)

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
            await update.message.reply_text(build_retry_message())
            return

        user_content = list(image_parts)
        if caption:
            user_content.insert(0, {"type": "text", "text": caption})

        save_msg = "[Image]" if len(image_parts) == 1 else f"[Images x{len(image_parts)}]"
        if caption:
            save_msg += f" {caption}"

        from handlers.messages.chat import chat
        await chat(
            update,
            context,
            user_content=user_content,
            save_msg=save_msg,
            frozen_persona_name=persona_name,
            frozen_session_id=session_id,
        )

    except Exception:
        logger.exception("%s error processing image", ctx)
        await update.message.reply_text(build_retry_message())
