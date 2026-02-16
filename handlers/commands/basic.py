"""Basic command handlers: /start, /help, /clear."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context

from services import (
    clear_conversation,
    get_current_persona_name,
    reset_token_usage,
    has_api_key,
)

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - show different welcome messages based on user state."""
    user_id = update.effective_user.id
    ctx = get_log_context(update)
    logger.info("%s /start", ctx)

    if not has_api_key(user_id):
        # New user: guide to set API key
        await update.message.reply_text(
            "Welcome to AI Bot! 👋\n\n"
            "To get started, set your API key:\n"
            "/set api_key YOUR_API_KEY\n\n"
            "Optionally configure:\n"
            "/set base_url <url> - Custom API endpoint\n"
            "/set model <name> - Choose a model\n\n"
            "Voice options:\n"
            "/set voice <name> - Default TTS voice\n"
            "/set style <style> - Default TTS style\n\n"
            "Type /help for all commands."
        )
    else:
        # Returning user
        persona = get_current_persona_name(user_id)
        await update.message.reply_text(
            f"Welcome back! Current persona: {persona}\n\n"
            "Send a message to start chatting, or /help for commands."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - show brief overview with inline keyboard for details."""
    logger.info("%s /help", get_log_context(update))
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Personas", callback_data="help:personas"),
            InlineKeyboardButton("Settings", callback_data="help:settings"),
        ],
        [
            InlineKeyboardButton("Memory", callback_data="help:memory"),
            InlineKeyboardButton("Advanced", callback_data="help:advanced"),
        ],
    ])
    await update.message.reply_text(
        "AI Bot Help\n\n"
        "Send text, image, or file to chat with AI.\n"
        "In groups: reply to bot or @mention.\n\n"
        "Quick commands:\n"
        "/clear - Clear conversation\n"
        "/chat - Manage sessions\n"
        "/settings - Show settings\n"
        "/usage - Token usage\n\n"
        "Tap a button for more details:",
        reply_markup=keyboard,
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command - clear conversation history and reset usage for current persona."""
    user_id = update.effective_user.id
    persona_name = get_current_persona_name(user_id)
    ctx = get_log_context(update)
    logger.info("%s /clear (persona=%s)", ctx, persona_name)
    clear_conversation(user_id, persona_name)
    reset_token_usage(user_id)
    await update.message.reply_text(f"Conversation cleared and usage reset for persona '{persona_name}'.")
