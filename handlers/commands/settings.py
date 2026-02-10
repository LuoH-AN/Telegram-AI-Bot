"""Settings command handlers: /settings, /set, model selection."""

import asyncio
import logging
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import MODELS_PER_PAGE
from services import (
    get_user_settings,
    update_user_setting,
    set_token_limit,
    has_api_key,
    get_current_persona_name,
    get_current_persona,
)
from ai import get_openai_client

logger = logging.getLogger(__name__)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - show current settings."""
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    persona_name = get_current_persona_name(user_id)
    persona = get_current_persona(user_id)

    # Mask API key for security
    masked_key = (
        settings["api_key"][:8] + "..." + settings["api_key"][-4:]
        if len(settings["api_key"]) > 12
        else "***"
    )

    # Truncate prompt for display
    prompt = persona["system_prompt"]
    prompt_display = prompt[:80] + "..." if len(prompt) > 80 else prompt

    enabled_tools = settings.get("enabled_tools", "memory,search,fetch,wikipedia")

    await update.message.reply_text(
        f"Current Settings:\n\n"
        f"base_url: {settings['base_url']}\n"
        f"api_key: {masked_key}\n"
        f"model: {settings['model']}\n"
        f"temperature: {settings['temperature']}\n"
        f"persona: {persona_name}\n"
        f"prompt: {prompt_display}\n"
        f"tools: {enabled_tools}\n\n"
        f"Use /persona to manage personas and prompts.\n"
        f"Use /set tool <name> <on|off> to manage tools."
    )


async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /set command - set configuration."""
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)

    if not context.args or len(context.args) < 2:
        # Check if it's "/set model" without value
        if context.args and context.args[0].lower() == "model":
            await _show_model_list(update, context)
            return
        # Check if it's "/set tool" without value
        if context.args and context.args[0].lower() == "tool":
            enabled_tools = settings.get("enabled_tools", "")
            enabled_list = [t.strip().lower() for t in enabled_tools.split(",") if t.strip()]
            available_tools = ["memory", "search", "fetch", "wikipedia"]
            status = []
            for t in available_tools:
                icon = "✅" if t in enabled_list else "❌"
                status.append(f"{icon} {t}")
            await update.message.reply_text(
                f"Tool Settings:\n\n" + "\n".join(status) + "\n\n"
                "Usage: /set tool <name> <on|off>"
            )
            return

        await update.message.reply_text(
            "Usage: /set <key> <value>\n\n"
            "Available keys:\n"
            "- base_url\n"
            "- api_key\n"
            "- model (no value to browse list)\n"
            "- temperature\n"
            "- token_limit\n"
            "- tool <name> <on|off>\n\n"
            "For prompt, use /persona prompt <text>"
        )
        return

    key = context.args[0].lower()
    value = " ".join(context.args[1:])

    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        await update.message.reply_text(f"base_url set to: {value}")
    elif key == "api_key":
        update_user_setting(user_id, "api_key", value)
        masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
        # Validate key by listing models
        try:
            models = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _fetch_models(user_id)
            )
            if models:
                await update.message.reply_text(
                    f"api_key set to: {masked}\n✅ Verified ({len(models)} models available)"
                )
            else:
                await update.message.reply_text(
                    f"api_key set to: {masked}\n⚠️ Could not verify key (no models returned). Check your base_url."
                )
        except Exception:
            await update.message.reply_text(
                f"api_key set to: {masked}\n⚠️ Could not verify key. Check your base_url and api_key."
            )
    elif key == "model":
        update_user_setting(user_id, "model", value)
        await update.message.reply_text(f"model set to: {value}")
    elif key == "prompt":
        await update.message.reply_text(
            "Prompts are now per-persona.\n"
            "Use /persona prompt <text> to set the prompt for current persona."
        )
    elif key == "temperature":
        try:
            temp = float(value)
            if 0.0 <= temp <= 2.0:
                update_user_setting(user_id, "temperature", temp)
                await update.message.reply_text(f"temperature set to: {temp}")
            else:
                await update.message.reply_text(
                    "Temperature must be between 0.0 and 2.0"
                )
        except ValueError:
            await update.message.reply_text("Invalid temperature value")
    elif key == "token_limit":
        try:
            limit = int(value)
            if limit >= 0:
                set_token_limit(user_id, limit)
                await update.message.reply_text(f"token_limit set to: {limit:,}")
            else:
                await update.message.reply_text("Token limit must be non-negative")
        except ValueError:
            await update.message.reply_text("Invalid token limit value")
    elif key == "tool":
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /set tool <name> <on|off>")
            return
        
        tool_name = context.args[1].lower()
        action = context.args[2].lower()
        
        available_tools = ["memory", "search", "fetch", "wikipedia"]
        if tool_name not in available_tools:
            await update.message.reply_text(f"Unknown tool: {tool_name}. Available: {', '.join(available_tools)}")
            return
            
        enabled_tools = settings.get("enabled_tools", "memory,search,fetch,wikipedia")
        enabled_list = [t.strip().lower() for t in enabled_tools.split(",") if t.strip()]
        
        if action == "on":
            if tool_name not in enabled_list:
                enabled_list.append(tool_name)
        elif action == "off":
            if tool_name in enabled_list:
                enabled_list.remove(tool_name)
        else:
            await update.message.reply_text("Action must be 'on' or 'off'")
            return
            
        new_enabled = ",".join(enabled_list)
        update_user_setting(user_id, "enabled_tools", new_enabled)
        await update.message.reply_text(f"Tool {tool_name} set to {action}")
    else:
        await update.message.reply_text(
            f"Unknown key: {key}\n\n"
            "Available keys: base_url, api_key, model, temperature, token_limit, tool"
        )


def _fetch_models(user_id: int) -> list[str]:
    """Fetch available models from the API."""
    try:
        client = get_openai_client(user_id)
        return client.list_models()
    except Exception as e:
        logger.exception("Failed to fetch models")
        return []


def _build_model_keyboard(
    models: list[str], page: int, current_model: str
) -> InlineKeyboardMarkup:
    """Build inline keyboard for model selection with pagination."""
    total_pages = math.ceil(len(models) / MODELS_PER_PAGE)
    start = page * MODELS_PER_PAGE
    end = start + MODELS_PER_PAGE
    page_models = models[start:end]

    keyboard = []
    for model in page_models:
        prefix = "* " if model == current_model else ""
        keyboard.append(
            [InlineKeyboardButton(f"{prefix}{model}", callback_data=f"model:{model}")]
        )

    # Pagination row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("< Prev", callback_data=f"models_page:{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="models_noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton("Next >", callback_data=f"models_page:{page + 1}")
        )

    if nav_buttons:
        keyboard.append(nav_buttons)

    return InlineKeyboardMarkup(keyboard)


async def _show_model_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0
) -> None:
    """Show paginated model list."""
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)

    if not has_api_key(user_id):
        await update.message.reply_text(
            "Please set your API key first:\n/set api_key YOUR_API_KEY"
        )
        return

    msg = await update.message.reply_text("Fetching models...")

    models = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _fetch_models(user_id)
    )

    if not models:
        await msg.edit_text("Failed to fetch models. Check your API key and base_url.")
        return

    # Store models in context for pagination
    context.user_data["models"] = models

    keyboard = _build_model_keyboard(models, page, settings["model"])
    await msg.edit_text(
        f"Select a model (current: {settings['model']}):", reply_markup=keyboard
    )
