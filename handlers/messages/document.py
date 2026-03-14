"""Document/file upload handler."""

import base64
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import (
    MIME_TYPE_MAP,
    MAX_FILE_SIZE,
    MAX_TEXT_CONTENT_LENGTH,
)
from utils import (
    edit_message_safe,
    get_file_extension,
    is_text_file,
    is_image_file,
    is_likely_text,
    decode_file_content,
)
from handlers.common import (
    get_log_context,
    preflight_media_request,
)
from utils.platform_parity import (
    build_analyze_uploaded_files_message,
    build_retry_message,
)

logger = logging.getLogger(__name__)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document/file uploads."""
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
    bot_message = await update.message.reply_text("Thinking...")

    try:
        text_blocks: list[str] = []
        image_parts: list[dict] = []
        unsupported_files: list[str] = []
        oversized_files: list[str] = []
        file_names: list[str] = []

        for msg in grouped_messages:
            doc = msg.document
            if not doc:
                continue

            file_name = doc.file_name or "unknown"
            file_names.append(file_name)
            file_ext = get_file_extension(file_name)

            if doc.file_size and doc.file_size > MAX_FILE_SIZE:
                oversized_files.append(file_name)
                continue

            tg_file = await context.bot.get_file(doc.file_id)
            file_bytes = await tg_file.download_as_bytearray()

            if is_image_file(file_name):
                image_base64 = base64.b64encode(file_bytes).decode("utf-8")
                ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "jpeg"
                mime_type = MIME_TYPE_MAP.get(ext, "jpeg")
                image_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime_type};base64,{image_base64}"},
                    }
                )
                continue

            if is_text_file(file_name) or is_likely_text(file_bytes):
                file_content = decode_file_content(file_bytes)
                if file_content is None:
                    unsupported_files.append(file_name)
                    continue

                truncated = False
                if len(file_content) > MAX_TEXT_CONTENT_LENGTH:
                    file_content = file_content[:MAX_TEXT_CONTENT_LENGTH]
                    truncated = True

                label = f"[File: {file_name}]"
                if truncated:
                    label += " (truncated)"
                text_blocks.append(f"{label}\n\n```\n{file_content}\n```")
                continue

            unsupported_files.append(file_name if file_ext else f"{file_name}(unknown)")

        text_sections = []
        if caption:
            text_sections.append(caption)
        if text_blocks:
            text_sections.append("\n\n".join(text_blocks))
        if oversized_files:
            blocked = ", ".join(oversized_files[:5])
            if len(oversized_files) > 5:
                blocked += ", ..."
            text_sections.append(f"Skipped oversized files (max 20MB): {blocked}")
        if unsupported_files:
            skipped = ", ".join(unsupported_files[:5])
            if len(unsupported_files) > 5:
                skipped += ", ..."
            text_sections.append(f"Skipped unsupported files: {skipped}")
        text_prompt = "\n\n".join(text_sections).strip()

        if image_parts:
            user_content = list(image_parts)
            if text_prompt:
                user_content.insert(0, {"type": "text", "text": text_prompt})
        else:
            user_content = text_prompt or build_analyze_uploaded_files_message()

        if len(file_names) == 1:
            save_msg = f"[File: {file_names[0]}]"
        else:
            preview = ", ".join(file_names[:3])
            if len(file_names) > 3:
                preview += ", ..."
            save_msg = f"[Files x{len(file_names)}] {preview}"
        if caption:
            save_msg += f" {caption}"

        from handlers.messages.text import chat
        await chat(
            update,
            context,
            user_content=user_content,
            save_msg=save_msg,
            bot_message=bot_message,
            frozen_persona_name=persona_name,
            frozen_session_id=session_id,
        )

    except Exception:
        logger.exception("%s error processing document", ctx)
        await edit_message_safe(bot_message, build_retry_message())
