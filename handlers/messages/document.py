"""Document/file upload handler."""
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from handlers.common import get_log_context, preflight_media_request
from handlers.messages.document_payload import build_document_payload
from utils.platform_parity import build_retry_message

logger = logging.getLogger(__name__)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    media_ctx = await preflight_media_request(update, context)
    if not media_ctx:
        return

    grouped_messages = media_ctx.grouped_messages
    caption = media_ctx.caption
    persona_name = media_ctx.persona_name
    session_id = media_ctx.session_id

    ctx = get_log_context(update)

    documents = [msg.document for msg in grouped_messages if msg.document]
    if not documents:
        return

    logger.info(
        "%s document batch (%d item(s))",
        ctx,
        len(documents),
    )

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        payload = await build_document_payload(grouped_messages, context, caption=caption)

        from handlers.messages.text import chat

        await chat(
            update,
            context,
            user_content=payload.user_content,
            save_msg=payload.save_message,
            frozen_persona_name=persona_name,
            frozen_session_id=session_id,
        )

    except Exception:
        logger.exception("%s error processing document", ctx)
        await update.message.reply_text(build_retry_message())
