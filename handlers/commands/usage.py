"""Usage and export command handlers: /usage, /export."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context
from utils.platform_parity import build_usage_reset_message

from services import (
    get_token_usage,
    export_to_markdown,
    get_current_persona_name,
    get_current_session_id,
    get_total_tokens_all_personas,
    get_token_limit,
    get_remaining_tokens,
    get_usage_percentage,
    reset_token_usage,
)

logger = logging.getLogger(__name__)


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /usage command - show token usage statistics."""
    user_id = update.effective_user.id
    args = context.args or []
    logger.info("%s /usage %s", get_log_context(update), " ".join(args) if args else "")
    persona_name = get_current_persona_name(user_id)

    if args and args[0].lower() == "reset":
        reset_token_usage(user_id, persona_name)
        await update.message.reply_text(build_usage_reset_message(persona_name))
        return

    # Get current persona usage
    usage = get_token_usage(user_id, persona_name)
    token_limit = get_token_limit(user_id, persona_name)

    prompt_tokens = usage["prompt_tokens"]
    completion_tokens = usage["completion_tokens"]
    total_tokens = usage["total_tokens"]

    message = f"Token Usage (Persona: {persona_name}):\n\n"
    message += f"Prompt tokens:     {prompt_tokens:,}\n"
    message += f"Completion tokens: {completion_tokens:,}\n"
    message += f"Total tokens:      {total_tokens:,}\n"

    if token_limit > 0:
        remaining = get_remaining_tokens(user_id, persona_name)
        percentage = get_usage_percentage(user_id, persona_name) or 0

        message += f"\nLimit:     {token_limit:,}\n"
        message += f"Remaining: {remaining:,}\n"
        message += f"Usage:     {percentage:.1f}%\n\n"

        # Progress bar (20 characters wide)
        filled = int(percentage / 5)
        empty = 20 - filled
        bar = "[" + "#" * filled + "-" * empty + "]"
        message += f"{bar} {percentage:.1f}%"
    else:
        message += f"\nLimit: Unlimited"

    # Show total across all personas
    total_all = get_total_tokens_all_personas(user_id)
    message += f"\n\n--- All Personas ---\n"
    message += f"Total tokens: {total_all:,}"

    await update.message.reply_text(message)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /export command - export current session chat history as markdown file."""
    user_id = update.effective_user.id
    logger.info("%s /export", get_log_context(update))
    persona_name = get_current_persona_name(user_id)
    session_id = get_current_session_id(user_id, persona_name)

    file_buffer = export_to_markdown(user_id, persona_name)

    if file_buffer is None:
        await update.message.reply_text(
            f"No conversation history to export in current session (persona: '{persona_name}')."
        )
        return

    caption = f"Chat history export (Persona: {persona_name})"
    if session_id is not None:
        caption += f"\nSession ID: {session_id}"

    await update.message.reply_document(
        document=file_buffer,
        filename=file_buffer.name,
        caption=caption,
    )
