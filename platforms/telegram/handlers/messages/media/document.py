"""Document/file upload handler."""
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from platforms.shared import apply_prompt_upload, parse_prompt_upload_caption
from platforms.telegram.handlers.common import get_log_context, preflight_media_request
from platforms.telegram.handlers.messages.media.payload import build_document_payload
from platforms.telegram.handlers.messages.media.prompt_upload import (
    extract_first_text_file,
)
from utils.platform import build_retry_message

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

    logger.info("%s document batch (%d item(s))", ctx, len(documents))

    await update.message.chat.send_action(ChatAction.TYPING)

    prompt_cmd = parse_prompt_upload_caption(caption)
    if prompt_cmd is not None:
        try:
            text = await extract_first_text_file(grouped_messages, context)
        except Exception:
            logger.exception("%s error extracting prompt file", ctx)
            await update.message.reply_text(build_retry_message())
            return
        if text is None:
            await update.message.reply_text(
                "No readable .txt file found. Attach a UTF-8 text file with this command."
            )
            return
        reply = apply_prompt_upload(prompt_cmd, update.effective_user.id, text)
        await update.message.reply_text(reply)
        return

    try:
        payload = await build_document_payload(grouped_messages, context, caption=caption)

        from platforms.telegram.handlers.messages.chat import chat

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
