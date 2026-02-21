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
from services import (
    has_api_key,
    get_remaining_tokens,
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
    should_respond_in_group,
    get_log_context,
    collect_media_group_messages,
)

logger = logging.getLogger(__name__)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document/file uploads."""
    if not await should_respond_in_group(update, context):
        return

    grouped_messages = await collect_media_group_messages(update.message)
    if grouped_messages is None:
        return

    if any(msg.forward_origin for msg in grouped_messages):
        return

    user_id = update.effective_user.id
    ctx = get_log_context(update)

    documents = [msg.document for msg in grouped_messages if msg.document]
    if not documents:
        return

    logger.info(
        "%s document batch (%d item(s))",
        ctx,
        len(documents),
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

    oversized = [
        (doc.file_name or "unknown")
        for doc in documents
        if doc.file_size and doc.file_size > MAX_FILE_SIZE
    ]
    if oversized:
        joined = ", ".join(oversized[:5])
        suffix = "..." if len(oversized) > 5 else ""
        await update.message.reply_text(
            f"File too large. Maximum size is 20MB.\nBlocked: {joined}{suffix}"
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
        text_blocks: list[str] = []
        image_parts: list[dict] = []
        unsupported_files: list[str] = []
        file_names: list[str] = []

        for msg in grouped_messages:
            doc = msg.document
            if not doc:
                continue

            file_name = doc.file_name or "unknown"
            file_names.append(file_name)
            file_ext = get_file_extension(file_name)

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

        if not text_blocks and not image_parts:
            await edit_message_safe(
                bot_message,
                "Unsupported file type.\n\n"
                "Supported types:\n"
                "- Text/code files (.txt, .py, .js, .json, .md, etc.)\n"
                "- Images (.jpg, .png, .gif, .webp)",
            )
            return

        text_sections = []
        if caption:
            text_sections.append(caption)
        if text_blocks:
            text_sections.append("\n\n".join(text_blocks))
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
            user_content = text_prompt or "Please analyze the uploaded file(s)."

        if len(file_names) == 1:
            save_msg = f"[File: {file_names[0]}]"
        else:
            preview = ", ".join(file_names[:3])
            if len(file_names) > 3:
                preview += ", ..."
            save_msg = f"[Files x{len(file_names)}] {preview}"
        if caption:
            save_msg += f" {caption}"

        # Delegate to chat handler for full streaming, thinking display, and tool support
        from handlers.messages.text import chat
        await chat(update, context, user_content=user_content, save_msg=save_msg, bot_message=bot_message)

    except Exception:
        logger.exception("%s error processing document", ctx)
        await edit_message_safe(bot_message, "Error. Please retry.")
