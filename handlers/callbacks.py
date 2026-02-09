"""Callback query handlers."""

from telegram import Update
from telegram.ext import ContextTypes

from services import get_user_settings, update_user_setting
from handlers.commands.settings import _build_model_keyboard

HELP_SECTIONS = {
    "help:personas": (
        "Persona Commands\n\n"
        "/persona - List all personas\n"
        "/persona <name> - Switch to persona\n"
        "/persona new <name> [prompt] - Create persona\n"
        "/persona delete <name> - Delete persona\n"
        "/persona prompt <text> - Set current persona's prompt\n\n"
        "Each persona has independent conversation and token tracking."
    ),
    "help:settings": (
        "Settings Commands\n\n"
        "/settings - Show current settings\n"
        "/set base_url <url>\n"
        "/set api_key <key>\n"
        "/set model (browse list)\n"
        "/set model <name>\n"
        "/set temperature <0.0-2.0>\n"
        "/set token_limit <number>"
    ),
    "help:memory": (
        "Memory Commands\n\n"
        "/remember <text> - Add a memory\n"
        "/memories - List all memories\n"
        "/forget <num|all> - Delete memories\n\n"
        "Memories are shared across all personas.\n"
        "AI can also learn and remember things automatically."
    ),
    "help:advanced": (
        "Advanced\n\n"
        "/export - Export current persona's chat history\n"
        "/usage - Show token usage\n"
        "/retry - Retry last message\n"
        "/clear - Clear conversation and reset usage\n\n"
        "Features:\n"
        "- Token limit is global across all personas\n"
        "- Send images or files for AI analysis\n"
        "- In groups: reply to bot or @mention"
    ),
}


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle help section callbacks."""
    query = update.callback_query
    await query.answer()

    text = HELP_SECTIONS.get(query.data)
    if text:
        await query.edit_message_text(text)


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle model selection and pagination callbacks."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data == "models_noop":
        return

    if data.startswith("models_page:"):
        page = int(data.split(":")[1])
        models = context.user_data.get("models", [])
        if not models:
            await query.edit_message_text("Session expired. Use /set model again.")
            return

        settings = get_user_settings(user_id)
        keyboard = _build_model_keyboard(models, page, settings["model"])
        await query.edit_message_reply_markup(reply_markup=keyboard)

    elif data.startswith("model:"):
        model = data.split(":", 1)[1]
        update_user_setting(user_id, "model", model)
        await query.edit_message_text(f"Model set to: {model}")
