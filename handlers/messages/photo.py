"""Photo message handler with vision model."""

import asyncio
import base64
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import MAX_MESSAGE_LENGTH, STREAM_UPDATE_INTERVAL
from services import (
    get_user_settings,
    add_user_message,
    add_assistant_message,
    add_token_usage,
    has_api_key,
    get_system_prompt,
)
from ai import get_ai_client
from utils import filter_thinking_content, send_message_safe, edit_message_safe
from handlers.common import should_respond_in_group

logger = logging.getLogger(__name__)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages with vision model."""
    # In groups, only respond when replied to or mentioned
    if not await should_respond_in_group(update, context):
        return

    user_id = update.effective_user.id
    settings = get_user_settings(user_id)

    # Check if API key is set
    if not has_api_key(user_id):
        await update.message.reply_text(
            "Please set your OpenAI API key first:\n/set api_key YOUR_API_KEY"
        )
        return

    # Get caption as prompt (no default - just send image)
    caption = update.message.caption or ""

    # Remove bot mention from caption if present
    bot_username = context.bot.username
    if bot_username and f"@{bot_username}" in caption:
        caption = caption.replace(f"@{bot_username}", "").strip()

    # Show typing indicator
    await update.message.chat.send_action(ChatAction.TYPING)

    # Send initial placeholder message
    bot_message = await update.message.reply_text("Processing image...")

    try:
        # Get the largest photo (best quality)
        photo = update.message.photo[-1]

        # Download photo
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        # Convert to base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Build message content with image
        if caption:
            user_content = [
                {"type": "text", "text": caption},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                },
            ]
        else:
            user_content = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                },
            ]

        system_prompt = get_system_prompt(user_id)
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
            # Check for usage info
            if chunk.usage is not None:
                usage_info = chunk.usage

            if chunk.content:
                full_response += chunk.content

                # Filter thinking content in real-time
                display_text = filter_thinking_content(full_response)

                # Update message periodically to avoid rate limiting
                current_time = asyncio.get_event_loop().time()
                if (
                    current_time - last_update_time >= STREAM_UPDATE_INTERVAL
                    and len(display_text) > last_update_length
                    and display_text
                ):
                    await edit_message_safe(bot_message, display_text + " ▌")
                    last_update_time = current_time
                    last_update_length = len(display_text)

        # Final update with complete response
        final_text = filter_thinking_content(full_response)

        if not final_text:
            final_text = "(Empty response)"

        # Check if response exceeds single message limit
        if len(final_text) > MAX_MESSAGE_LENGTH:
            await bot_message.delete()
            await send_message_safe(update.message, final_text)
        else:
            await edit_message_safe(bot_message, final_text)

        # Save conversation to database
        save_msg = "[Image]"
        if caption:
            save_msg += f" {caption}"
        add_user_message(user_id, save_msg)
        add_assistant_message(user_id, final_text)

        # Record token usage if available
        if usage_info:
            add_token_usage(
                user_id,
                usage_info.get("prompt_tokens", 0),
                usage_info.get("completion_tokens", 0),
            )

    except Exception as e:
        logger.exception("Error processing image")
        await edit_message_safe(bot_message, f"Error: {str(e)}")
