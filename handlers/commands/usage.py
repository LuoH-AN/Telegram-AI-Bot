"""Usage and export command handlers: /usage, /export."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context

from services import (
    get_token_usage,
    export_to_markdown,
    get_current_persona_name,
    get_total_tokens_all_personas,
    get_token_limit,
)

logger = logging.getLogger(__name__)


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /usage command - show token usage statistics."""
    user_id = update.effective_user.id
    logger.info("%s /usage", get_log_context(update))
    persona_name = get_current_persona_name(user_id)

    # Get current persona usage
    usage = get_token_usage(user_id, persona_name)
    total_all = get_total_tokens_all_personas(user_id)
    token_limit = get_token_limit(user_id)

    prompt_tokens = usage["prompt_tokens"]
    completion_tokens = usage["completion_tokens"]
    total_tokens = usage["total_tokens"]

    message = f"Token Usage (Persona: {persona_name}):\n\n"
    message += f"Prompt tokens:     {prompt_tokens:,}\n"
    message += f"Completion tokens: {completion_tokens:,}\n"
    message += f"Total tokens:      {total_tokens:,}\n"

    message += f"\n--- All Personas ---\n"
    message += f"Total tokens: {total_all:,}\n"

    if token_limit > 0:
        remaining = max(0, token_limit - total_all)
        percentage = min(100.0, (total_all / token_limit) * 100)

        message += f"\nGlobal Limit: {token_limit:,}\n"
        message += f"Remaining:    {remaining:,}\n"
        message += f"Usage:        {percentage:.1f}%\n\n"

        # Progress bar (20 characters wide)
        filled = int(percentage / 5)
        empty = 20 - filled
        bar = "[" + "#" * filled + "-" * empty + "]"
        message += f"{bar} {percentage:.1f}%"

    await update.message.reply_text(message)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /export command - export chat history as markdown file."""
    user_id = update.effective_user.id
    logger.info("%s /export", get_log_context(update))
    persona_name = get_current_persona_name(user_id)

    file_buffer = export_to_markdown(user_id, persona_name)

    if file_buffer is None:
        await update.message.reply_text(
            f"No conversation history to export for persona '{persona_name}'."
        )
        return

    await update.message.reply_document(
        document=file_buffer,
        filename=file_buffer.name,
        caption=f"Chat history export (Persona: {persona_name})"
    )
