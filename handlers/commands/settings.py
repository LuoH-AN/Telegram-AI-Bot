"""Settings command handlers: /settings, /set, model selection."""

import asyncio
import logging
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import MODELS_PER_PAGE, DEFAULT_TTS_VOICE, DEFAULT_TTS_STYLE
from services import (
    get_user_settings,
    update_user_setting,
    set_token_limit,
    has_api_key,
    get_current_persona_name,
    get_current_persona,
    normalize_tts_endpoint,
)
from ai import get_openai_client
from handlers.common import get_log_context

logger = logging.getLogger(__name__)

AVAILABLE_TOOLS = ["memory", "search", "fetch", "wikipedia", "tts"]


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - show current settings."""
    user_id = update.effective_user.id
    logger.info("%s /settings", get_log_context(update))
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

    enabled_tools = settings.get("enabled_tools", "memory,search,fetch,wikipedia,tts")
    tts_voice = settings.get("tts_voice", DEFAULT_TTS_VOICE)
    tts_style = settings.get("tts_style", DEFAULT_TTS_STYLE)
    tts_endpoint = settings.get("tts_endpoint", "") or "auto"
    presets = settings.get("api_presets", {})
    presets_info = ", ".join(presets.keys()) if presets else "(none)"
    title_model_raw = settings.get("title_model", "")
    if not title_model_raw:
        title_model_display = "(current model)"
    elif ":" in title_model_raw:
        p, m = title_model_raw.split(":", 1)
        title_model_display = f"{p}:{m}"
    else:
        title_model_display = title_model_raw

    await update.message.reply_text(
        f"Current Settings:\n\n"
        f"base_url: {settings['base_url']}\n"
        f"api_key: {masked_key}\n"
        f"model: {settings['model']}\n"
        f"temperature: {settings['temperature']}\n"
        f"title_model: {title_model_display}\n"
        f"persona: {persona_name}\n"
        f"prompt: {prompt_display}\n"
        f"tools: {enabled_tools}\n\n"
        f"tts_voice: {tts_voice}\n"
        f"tts_style: {tts_style}\n"
        f"tts_endpoint: {tts_endpoint}\n\n"
        f"providers: {presets_info}\n\n"
        f"Use /persona to manage personas and prompts.\n"
        f"Use /chat to manage chat sessions.\n"
        f"Use /set tool <name> <on|off> to manage tools.\n"
        f"Use /set provider to manage API providers."
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
            status = []
            for t in AVAILABLE_TOOLS:
                icon = "✅" if t in enabled_list else "❌"
                status.append(f"{icon} {t}")
            await update.message.reply_text(
                f"Tool Settings:\n\n" + "\n".join(status) + "\n\n"
                "Usage: /set tool <name> <on|off>"
            )
            return

        if context.args and context.args[0].lower() in {"voice", "style", "endpoint"}:
            key = context.args[0].lower()
            setting_key = {
                "voice": "tts_voice",
                "style": "tts_style",
                "endpoint": "tts_endpoint",
            }[key]
            current = settings.get(setting_key, "") or "auto"
            await update.message.reply_text(
                f"Current {key}: {current}\n"
                f"Usage: /set {key} <value>"
            )
            return

        if context.args and context.args[0].lower() == "provider":
            await _show_provider_list(update, settings)
            return

        await update.message.reply_text(
            "Usage: /set <key> <value>\n\n"
            "Available keys:\n"
            "- base_url\n"
            "- api_key\n"
            "- model (no value to browse list)\n"
            "- temperature\n"
            "- token_limit\n"
            "- title_model [provider:]model\n"
            "- voice\n"
            "- style\n"
            "- endpoint\n"
            "- tool <name> <on|off>\n"
            "- provider save/load/delete/list\n\n"
            "For prompt, use /persona prompt <text>"
        )
        return

    key = context.args[0].lower()
    value = " ".join(context.args[1:])
    ctx = get_log_context(update)

    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        logger.info("%s set base_url = %s", ctx, value)
        await update.message.reply_text(f"base_url set to: {value}")
    elif key == "api_key":
        update_user_setting(user_id, "api_key", value)
        masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
        logger.info("%s set api_key = %s", ctx, masked)
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
        logger.info("%s set model = %s", ctx, value)
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
                logger.info("%s set temperature = %s", ctx, temp)
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
                logger.info("%s set token_limit = %s", ctx, limit)
                await update.message.reply_text(f"token_limit set to: {limit:,}")
            else:
                await update.message.reply_text("Token limit must be non-negative")
        except ValueError:
            await update.message.reply_text("Invalid token limit value")
    elif key == "voice":
        voice = value.strip()
        if not voice:
            await update.message.reply_text("Voice cannot be empty")
            return
        update_user_setting(user_id, "tts_voice", voice)
        logger.info("%s set voice = %s", ctx, voice)
        await update.message.reply_text(f"voice set to: {voice}")
    elif key == "style":
        style = value.strip().lower()
        if not style:
            await update.message.reply_text("Style cannot be empty")
            return
        update_user_setting(user_id, "tts_style", style)
        logger.info("%s set style = %s", ctx, style)
        await update.message.reply_text(f"style set to: {style}")
    elif key == "endpoint":
        endpoint = value.strip()
        if endpoint.lower() in {"auto", "default", "off"}:
            update_user_setting(user_id, "tts_endpoint", "")
            logger.info("%s set endpoint = auto", ctx)
            await update.message.reply_text("endpoint set to: auto")
            return

        normalized = normalize_tts_endpoint(endpoint)
        if not normalized:
            await update.message.reply_text(
                "Invalid endpoint. Example:\n"
                "/set endpoint southeastasia\n"
                "or /set endpoint southeastasia.tts.speech.microsoft.com"
            )
            return

        update_user_setting(user_id, "tts_endpoint", normalized)
        logger.info("%s set endpoint = %s", ctx, normalized)
        await update.message.reply_text(f"endpoint set to: {normalized}")
    elif key == "tool":
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /set tool <name> <on|off>")
            return

        tool_name = context.args[1].lower()
        action = context.args[2].lower()

        if tool_name not in AVAILABLE_TOOLS:
            await update.message.reply_text(f"Unknown tool: {tool_name}. Available: {', '.join(AVAILABLE_TOOLS)}")
            return

        enabled_tools = settings.get("enabled_tools", "memory,search,fetch,wikipedia,tts")
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
        logger.info("%s set tool %s = %s", ctx, tool_name, action)
        await update.message.reply_text(f"Tool {tool_name} set to {action}")
    elif key == "provider":
        await _handle_provider_command(update, context, user_id, settings, ctx)
    elif key == "title_model":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "title_model", "")
            await update.message.reply_text("title_model cleared (will use current provider + model)")
        else:
            update_user_setting(user_id, "title_model", val)
            logger.info("%s set title_model = %s", ctx, val)
            if ":" in val:
                provider, model = val.split(":", 1)
                presets = settings.get("api_presets", {})
                found = any(k.lower() == provider.lower() for k in presets)
                if found:
                    await update.message.reply_text(
                        f"title_model set to: {val}\n"
                        f"Provider: {provider} | Model: {model}"
                    )
                else:
                    available = ", ".join(presets.keys()) if presets else "(none)"
                    await update.message.reply_text(
                        f"title_model set to: {val}\n"
                        f"⚠️ Provider '{provider}' not found in presets.\n"
                        f"Available: {available}\n"
                        f"Use /set provider save <name> to save one first."
                    )
            else:
                await update.message.reply_text(
                    f"title_model set to: {val}\n"
                    f"(uses current provider's API)"
                )
    else:
        await update.message.reply_text(
            f"Unknown key: {key}\n\n"
            "Available keys: base_url, api_key, model, temperature, token_limit, title_model, voice, style, endpoint, tool, provider"
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


async def _show_provider_list(update: Update, settings: dict) -> None:
    """Show saved API provider presets."""
    presets = settings.get("api_presets", {})
    if not presets:
        await update.message.reply_text(
            "No saved providers.\n\n"
            "Usage:\n"
            "/set provider save <name> - Save current API config\n"
            "/set provider <name> - Load a saved config\n"
            "/set provider delete <name> - Delete a saved config"
        )
        return

    lines = ["Saved Providers:\n"]
    for name, preset in presets.items():
        masked_key = (
            preset["api_key"][:8] + "..." + preset["api_key"][-4:]
            if len(preset.get("api_key", "")) > 12
            else "***"
        )
        lines.append(
            f"[{name}]\n"
            f"  base_url: {preset.get('base_url', '')}\n"
            f"  api_key: {masked_key}\n"
            f"  model: {preset.get('model', '')}"
        )

    lines.append(
        "\nUsage:\n"
        "/set provider save <name>\n"
        "/set provider <name>\n"
        "/set provider delete <name>"
    )
    await update.message.reply_text("\n".join(lines))


async def _handle_provider_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    user_id: int, settings: dict, ctx: str,
) -> None:
    """Handle /set provider subcommands."""
    args = context.args  # ["provider", ...]
    presets = settings.get("api_presets", {})

    if len(args) < 2:
        await _show_provider_list(update, settings)
        return

    sub = args[1].lower()

    if sub == "list":
        await _show_provider_list(update, settings)

    elif sub == "save":
        if len(args) < 3:
            await update.message.reply_text("Usage: /set provider save <name>")
            return
        name = args[2]
        presets[name] = {
            "api_key": settings["api_key"],
            "base_url": settings["base_url"],
            "model": settings["model"],
        }
        update_user_setting(user_id, "api_presets", presets)
        masked_key = (
            settings["api_key"][:8] + "..." + settings["api_key"][-4:]
            if len(settings["api_key"]) > 12
            else "***"
        )
        logger.info("%s provider save %s", ctx, name)
        await update.message.reply_text(
            f"Provider '{name}' saved:\n"
            f"  base_url: {settings['base_url']}\n"
            f"  api_key: {masked_key}\n"
            f"  model: {settings['model']}"
        )

    elif sub == "delete":
        if len(args) < 3:
            await update.message.reply_text("Usage: /set provider delete <name>")
            return
        name = args[2]
        if name not in presets:
            await update.message.reply_text(f"Provider '{name}' not found.")
            return
        del presets[name]
        update_user_setting(user_id, "api_presets", presets)
        logger.info("%s provider delete %s", ctx, name)
        await update.message.reply_text(f"Provider '{name}' deleted.")

    else:
        # /set provider <name> — load a preset
        name = args[1]  # use original case
        if name not in presets:
            # Try case-insensitive match
            for k in presets:
                if k.lower() == sub:
                    name = k
                    break
            else:
                available = ", ".join(presets.keys()) if presets else "(none)"
                await update.message.reply_text(
                    f"Provider '{name}' not found.\n"
                    f"Available: {available}"
                )
                return

        preset = presets[name]
        update_user_setting(user_id, "api_key", preset["api_key"])
        update_user_setting(user_id, "base_url", preset["base_url"])
        update_user_setting(user_id, "model", preset["model"])

        masked_key = (
            preset["api_key"][:8] + "..." + preset["api_key"][-4:]
            if len(preset.get("api_key", "")) > 12
            else "***"
        )
        logger.info("%s provider load %s", ctx, name)
        await update.message.reply_text(
            f"Loaded provider '{name}':\n"
            f"  base_url: {preset['base_url']}\n"
            f"  api_key: {masked_key}\n"
            f"  model: {preset['model']}"
        )
