"""Basic command handlers: /start, /help, /clear."""

from telegram import Update
from telegram.ext import ContextTypes

from services import (
    clear_conversation,
    get_current_persona_name,
    reset_token_usage,
    has_api_key,
    get_conversation,
    pop_last_exchange,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - show different welcome messages based on user state."""
    user_id = update.effective_user.id

    if not has_api_key(user_id):
        # New user: guide to set API key
        await update.message.reply_text(
            "Welcome to AI Bot! 👋\n\n"
            "To get started, set your API key:\n"
            "/set api_key YOUR_API_KEY\n\n"
            "Optionally configure:\n"
            "/set base_url <url> - Custom API endpoint\n"
            "/set model <name> - Choose a model\n\n"
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
        "/settings - Show settings\n"
        "/usage - Token usage\n"
        "/retry - Retry last message\n\n"
        "Tap a button for more details:",
        reply_markup=keyboard,
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command - clear conversation history and reset usage for current persona."""
    user_id = update.effective_user.id
    persona_name = get_current_persona_name(user_id)
    clear_conversation(user_id, persona_name)
    reset_token_usage(user_id)
    await update.message.reply_text(f"Conversation cleared and usage reset for persona '{persona_name}'.")


async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /retry command - replay last user message after removing previous exchange."""
    last_message = context.user_data.get("last_message")
    if not last_message:
        await update.message.reply_text("No previous message to retry.")
        return

    user_id = update.effective_user.id
    # Remove last user+assistant exchange from conversation history
    pop_last_exchange(user_id)

    # Replay by injecting the text into the update and calling chat()
    from handlers.messages.text import chat

    # Temporarily set message text to the last message
    update.message.text = last_message
    await chat(update, context)
