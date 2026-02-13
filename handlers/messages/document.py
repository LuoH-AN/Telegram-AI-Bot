"""Document/file upload handler."""

import asyncio
import base64
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import (
    MAX_MESSAGE_LENGTH,
    STREAM_UPDATE_INTERVAL,
    MIME_TYPE_MAP,
    MAX_FILE_SIZE,
    MAX_TEXT_CONTENT_LENGTH,
)
from services import (
    get_user_settings,
    get_conversation,
    add_user_message,
    add_assistant_message,
    add_token_usage,
    has_api_key,
    get_system_prompt,
)
from ai import get_ai_client
from utils import (
    filter_thinking_content,
    send_message_safe,
    edit_message_safe,
    get_datetime_prompt,
    get_file_extension,
    is_text_file,
    is_image_file,
    is_likely_text,
    decode_file_content,
)
from handlers.common import should_respond_in_group, get_log_context

logger = logging.getLogger(__name__)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document/file uploads."""
    # In groups, only respond when replied to or mentioned
    if not await should_respond_in_group(update, context):
        return

    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    ctx = get_log_context(update)

    # Check if API key is set
    if not has_api_key(user_id):
        await update.message.reply_text(
            "Please set your OpenAI API key first:\n/set api_key YOUR_API_KEY"
        )
        return

    document = update.message.document
    file_name = document.file_name or "unknown"
    file_ext = get_file_extension(file_name)

    logger.info("%s document: %s (%s bytes)", ctx, file_name, document.file_size)

    # Skip forwarded messages
    if update.message.forward_origin:
        return

    # Get caption as user prompt (no default - just use file content)
    caption = update.message.caption or ""

    # Remove bot mention from caption if present
    bot_username = context.bot.username
    if bot_username and f"@{bot_username}" in caption:
        caption = caption.replace(f"@{bot_username}", "").strip()

    # Include quoted message content when replying to a message
    reply_msg = update.message.reply_to_message
    if reply_msg:
        quoted_text = reply_msg.text or reply_msg.caption or ""
        if quoted_text:
            sender = reply_msg.from_user
            sender_name = sender.first_name if sender else "Unknown"
            caption = f"[Quoted message from {sender_name}]:\n{quoted_text}\n\n{caption}" if caption else f"[Quoted message from {sender_name}]:\n{quoted_text}"

    # Check file size
    if document.file_size and document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text("File too large. Maximum size is 20MB.")
        return

    # Show typing indicator
    await update.message.chat.send_action(ChatAction.TYPING)

    # Send initial placeholder message
    bot_message = await update.message.reply_text("…")

    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()

        # Determine how to process the file
        if is_image_file(file_name):
            # Process as image (vision)
            await _process_image_file(
                update, bot_message, file_bytes, file_name, caption, settings
            )
        elif is_text_file(file_name) or is_likely_text(file_bytes):
            # Process as text file
            await _process_text_file(
                update, bot_message, file_bytes, file_name, caption, settings
            )
        else:
            await edit_message_safe(
                bot_message,
                f"Unsupported file type: {file_ext or 'unknown'}\n\n"
                "Supported types:\n"
                "- Text/code files (.txt, .py, .js, .json, .md, etc.)\n"
                "- Images (.jpg, .png, .gif, .webp)"
            )

    except Exception as e:
        logger.exception("%s error processing document", ctx)
        await edit_message_safe(bot_message, f"Error: {str(e)}")


async def _process_text_file(
    update: Update,
    bot_message,
    file_bytes: bytearray,
    file_name: str,
    caption: str,
    settings: dict,
) -> None:
    """Process a text file and send to AI."""
    user_id = update.effective_user.id

    # Decode file content
    file_content = decode_file_content(file_bytes)
    if file_content is None:
        await edit_message_safe(bot_message, "Unable to decode file content.")
        return

    # Truncate if too long
    truncated = False
    if len(file_content) > MAX_TEXT_CONTENT_LENGTH:
        file_content = file_content[:MAX_TEXT_CONTENT_LENGTH]
        truncated = True

    # Build user message - just include file content
    user_message = f"[File: {file_name}]"
    if truncated:
        user_message += " (truncated)"
    user_message += f"\n\n```\n{file_content}\n```"
    if caption:
        user_message += f"\n\n{caption}"

    conversation = get_conversation(user_id)
    system_prompt = get_system_prompt(user_id)
    system_prompt += "\n\n" + get_datetime_prompt()

    client = get_ai_client(user_id)

    # Build messages with system prompt
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation)
    messages.append({"role": "user", "content": user_message})

    # Call AI API with streaming
    stream = client.chat_completion(
        messages=messages,
        model=settings["model"],
        temperature=settings["temperature"],
        stream=True,
    )

    full_response = ""
    last_update_time = 0
    last_update_length = 0
    usage_info = None

    for chunk in stream:
        if chunk.usage is not None:
            usage_info = chunk.usage

        if chunk.content:
            full_response += chunk.content

            display_text = filter_thinking_content(full_response)

            current_time = asyncio.get_event_loop().time()
            if (
                current_time - last_update_time >= STREAM_UPDATE_INTERVAL
                and len(display_text) > last_update_length
                and display_text
            ):
                await edit_message_safe(bot_message, display_text + " ▌")
                last_update_time = current_time
                last_update_length = len(display_text)

    final_text = filter_thinking_content(full_response)

    if not final_text:
        final_text = "(Empty response)"

    if len(final_text) > MAX_MESSAGE_LENGTH:
        await bot_message.delete()
        await send_message_safe(update.message, final_text)
    else:
        await edit_message_safe(bot_message, final_text)

    # Save conversation - include caption if provided
    save_msg = f"[File: {file_name}]"
    if caption:
        save_msg += f" {caption}"
    add_user_message(user_id, save_msg)
    add_assistant_message(user_id, final_text)

    if usage_info:
        add_token_usage(
            user_id,
            usage_info.get("prompt_tokens", 0),
            usage_info.get("completion_tokens", 0),
        )


async def _process_image_file(
    update: Update,
    bot_message,
    file_bytes: bytearray,
    file_name: str,
    caption: str,
    settings: dict,
) -> None:
    """Process an image file and send to AI with vision."""
    user_id = update.effective_user.id

    # Convert to base64
    image_base64 = base64.b64encode(file_bytes).decode("utf-8")

    # Determine mime type
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "jpeg"
    mime_type = MIME_TYPE_MAP.get(ext, "jpeg")

    # Build message content with image
    # If no caption, just send the image without text prompt
    if caption:
        user_content = [
            {"type": "text", "text": caption},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime_type};base64,{image_base64}"},
            },
        ]
    else:
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime_type};base64,{image_base64}"},
            },
        ]

    system_prompt = get_system_prompt(user_id)
    system_prompt += "\n\n" + get_datetime_prompt()

    client = get_ai_client(user_id)

    # Build messages with system prompt
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # Call AI API with streaming
    stream = client.chat_completion(
        messages=messages,
        model=settings["model"],
        temperature=settings["temperature"],
        stream=True,
    )

    full_response = ""
    last_update_time = 0
    last_update_length = 0
    usage_info = None

    for chunk in stream:
        if chunk.usage is not None:
            usage_info = chunk.usage

        if chunk.content:
            full_response += chunk.content

            display_text = filter_thinking_content(full_response)

            current_time = asyncio.get_event_loop().time()
            if (
                current_time - last_update_time >= STREAM_UPDATE_INTERVAL
                and len(display_text) > last_update_length
                and display_text
            ):
                await edit_message_safe(bot_message, display_text + " ▌")
                last_update_time = current_time
                last_update_length = len(display_text)

    final_text = filter_thinking_content(full_response)

    if not final_text:
        final_text = "(Empty response)"

    if len(final_text) > MAX_MESSAGE_LENGTH:
        await bot_message.delete()
        await send_message_safe(update.message, final_text)
    else:
        await edit_message_safe(bot_message, final_text)

    # Save conversation
    save_msg = f"[Image: {file_name}]"
    if caption:
        save_msg += f" {caption}"
    add_user_message(user_id, save_msg)
    add_assistant_message(user_id, final_text)

    if usage_info:
        add_token_usage(
            user_id,
            usage_info.get("prompt_tokens", 0),
            usage_info.get("completion_tokens", 0),
        )
