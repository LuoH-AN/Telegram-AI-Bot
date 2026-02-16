"""Callback query handlers."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from services import get_user_settings, update_user_setting
from handlers.common import get_log_context
from handlers.commands.settings import _build_model_keyboard

logger = logging.getLogger(__name__)

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
        "/set token_limit <number>\n"
        "/set voice <name>\n"
        "/set style <style>\n"
        "/set endpoint <region|host>\n"
        "/set tool tts <on|off>\n\n"
        "API Provider Presets:\n"
        "/set provider - List saved providers\n"
        "/set provider save <name> - Save current config\n"
        "/set provider <name> - Load a saved config\n"
        "/set provider delete <name> - Delete"
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
        "/chat - Manage chat sessions\n"
        "/export - Export current session's chat history\n"
        "/usage - Show token usage\n"
        "/clear - Clear current session's conversation\n\n"
        "Session Commands:\n"
        "/chat - List sessions\n"
        "/chat new [title] - New session\n"
        "/chat <num> - Switch session\n"
        "/chat rename <title> - Rename session\n"
        "/chat delete <num> - Delete session\n\n"
        "Features:\n"
        "- Token limit is global across all personas\n"
        "- Send images or files for AI analysis\n"
        "- In groups: reply to bot or @mention\n"
        "- /set title_model [provider:]model - Auto-title model"
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
        logger.info("%s model page %d", get_log_context(update), page)
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
        logger.info("%s set model = %s (callback)", get_log_context(update), model)
        await query.edit_message_text(f"Model set to: {model}")
