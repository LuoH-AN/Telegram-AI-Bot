"""Settings command handlers: /settings, /set, model selection."""

import asyncio
import logging
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import MODELS_PER_PAGE, DEFAULT_TTS_VOICE, DEFAULT_TTS_STYLE, VALID_REASONING_EFFORTS
from services import (
    get_user_settings,
    update_user_setting,
    set_token_limit,
    get_token_limit,
    has_api_key,
    get_current_persona_name,
    get_current_persona,
    normalize_tts_endpoint,
)
from services.refresh import ensure_user_state
from ai import get_openai_client
from handlers.common import get_log_context
from utils.platform_parity import (
    build_api_key_required_message,
    build_api_key_verify_failed_message,
    build_api_key_verify_no_models_message,
    build_endpoint_invalid_message,
    build_prompt_per_persona_message,
    build_provider_list_usage_message,
    build_provider_no_saved_message,
    build_provider_not_found_available_message,
    build_provider_save_hint_message,
    build_provider_usage_message,
    build_set_usage_message,
    build_unknown_set_key_message,
)

logger = logging.getLogger(__name__)


def _mask_api_key(key: str) -> str:
    """Mask an API key for display, showing first 8 and last 4 chars."""
    if len(key) > 12:
        return key[:8] + "..." + key[-4:]
    return "***"


def _truncate_display(text: str, max_len: int = 80) -> str:
    """Truncate text for display with ellipsis."""
    return text[:max_len] + "..." if len(text) > max_len else text


def _format_model_display(raw: str) -> str:
    """Format a model spec (e.g. provider:model) for display."""
    if not raw:
        return "(current model)"
    return raw


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - show current settings."""
    user_id = update.effective_user.id
    logger.info("%s /settings", get_log_context(update))
    ensure_user_state(user_id)
    settings = get_user_settings(user_id)
    persona_name = get_current_persona_name(user_id)
    persona = get_current_persona(user_id)
    token_limit = get_token_limit(user_id, persona_name)

    # Mask API key for security
    masked_key = _mask_api_key(settings["api_key"])

    # Truncate prompt for display
    prompt = persona["system_prompt"]
    prompt_display = _truncate_display(prompt)

    # Get global prompt for display
    global_prompt = settings.get("global_prompt", "") or ""
    global_prompt_display = _truncate_display(global_prompt) if global_prompt else "(none)"

    tts_voice = settings.get("tts_voice", DEFAULT_TTS_VOICE)
    tts_style = settings.get("tts_style", DEFAULT_TTS_STYLE)
    tts_endpoint = settings.get("tts_endpoint", "") or "auto"
    stream_mode = settings.get("stream_mode", "") or "default"
    show_thinking = "on" if settings.get("show_thinking") else "off"
    presets = settings.get("api_presets", {})
    presets_info = ", ".join(presets.keys()) if presets else "(none)"
    title_model_display = _format_model_display(settings.get("title_model", ""))
    cron_model_display = _format_model_display(settings.get("cron_model", ""))

    await update.message.reply_text(
        f"Current Settings:\n\n"
        f"base_url: {settings['base_url']}\n"
        f"api_key: {masked_key}\n"
        f"model: {settings['model']}\n"
        f"temperature: {settings['temperature']}\n"
        f"reasoning_effort: {settings.get('reasoning_effort', '') or '(provider/model default)'}\n"
        f"show_thinking: {show_thinking}\n"
        f"stream_mode: {stream_mode}\n"
        f"title_model: {title_model_display}\n"
        f"cron_model: {cron_model_display}\n"
        f"persona: {persona_name}\n"
        f"token_limit({persona_name}): {token_limit if token_limit > 0 else 'unlimited'}\n"
        f"global_prompt: {global_prompt_display}\n"
        f"prompt: {prompt_display}\n"
        f"tts_voice: {tts_voice}\n"
        f"tts_style: {tts_style}\n"
        f"tts_endpoint: {tts_endpoint}\n\n"
        f"providers: {presets_info}\n\n"
        f"Use /persona to manage personas and prompts.\n"
        f"Use /chat to manage chat sessions.\n"
        f"Use /set provider to manage API providers."
    )



async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /set command - set configuration."""
    user_id = update.effective_user.id
    ensure_user_state(user_id)
    settings = get_user_settings(user_id)
    ctx = get_log_context(update)
    logger.info("%s /set %s", ctx, " ".join(context.args)[:120] if context.args else "")

    if not context.args or len(context.args) < 2:
        if context.args and context.args[0].lower() == "model":
            await _show_model_list(update, context)
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

        if context.args and context.args[0].lower() == "stream_mode":
            current = settings.get("stream_mode", "") or "default"
            await update.message.reply_text(
                f"Current stream_mode: {current}\n"
                "Usage: /set stream_mode <mode>\n\n"
                "Available modes:\n"
                "- default: time + chars combined\n"
                "- time: update by time interval\n"
                "- chars: update by character interval\n"
                "- off: non-streaming, wait for full response (reduces rate limits)"
            )
            return
        if context.args and context.args[0].lower() == "show_thinking":
            current = "on" if settings.get("show_thinking") else "off"
            await update.message.reply_text(
                f"Current show_thinking: {current}\n"
                "Usage: /set show_thinking <on|off>"
            )
            return
        if context.args and context.args[0].lower() == "reasoning_effort":
            current = settings.get("reasoning_effort", "") or "(provider/model default)"
            await update.message.reply_text(
                f"Current reasoning_effort: {current}\n"
                "Usage: /set reasoning_effort <value>\n\n"
                "Available values:\n"
                "- none\n"
                "- minimal\n"
                "- low\n"
                "- medium\n"
                "- high\n"
                "- xhigh\n\n"
                "Use /set reasoning_effort clear to follow provider/model default."
            )
            return
        if context.args and context.args[0].lower() == "global_prompt":
            current = settings.get("global_prompt", "") or "(none)"
            display = _truncate_display(current, 100)
            await update.message.reply_text(
                f"Current global_prompt: {display}\n\n"
                "Usage: /set global_prompt <prompt>\n"
                "Use /set global_prompt clear to remove."
            )
            return

        await update.message.reply_text(build_set_usage_message("/"))
        return

    key = context.args[0].lower()
    value = " ".join(context.args[1:])

    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        logger.info("%s set base_url = %s", ctx, value)
        await update.message.reply_text(f"base_url set to: {value}")
    elif key == "api_key":
        update_user_setting(user_id, "api_key", value)
        masked = _mask_api_key(value)
        logger.info("%s set api_key = %s", ctx, masked)
        # Validate key by listing models
        try:
            models = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _fetch_models(user_id)
            )
            if models:
                await update.message.reply_text(
                    f"api_key set to: {masked}\nVerified ({len(models)} models available)"
                )
            else:
                await update.message.reply_text(build_api_key_verify_no_models_message(masked))
        except Exception:
            await update.message.reply_text(build_api_key_verify_failed_message(masked))
    elif key == "model":
        update_user_setting(user_id, "model", value)
        logger.info("%s set model = %s", ctx, value)
        await update.message.reply_text(f"model set to: {value}")
    elif key == "prompt":
        await update.message.reply_text(build_prompt_per_persona_message("/"))
    elif key == "global_prompt":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "global_prompt", "")
            logger.info("%s cleared global_prompt", ctx)
            await update.message.reply_text(
                "global_prompt cleared.\n"
                "Now personas will use their own system prompts only."
            )
            return
        update_user_setting(user_id, "global_prompt", val)
        logger.info("%s set global_prompt = %s", ctx, _truncate_display(val, 50))
        await update.message.reply_text(
            f"global_prompt set to: {_truncate_display(val, 100)}\n\n"
            "This prompt will be prepended to all personas' system prompts.\n"
            "Use /set global_prompt clear to remove."
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
    elif key == "reasoning_effort":
        val = value.strip().lower()
        if not val or val in {"off", "clear"}:
            update_user_setting(user_id, "reasoning_effort", "")
            logger.info("%s cleared reasoning_effort", ctx)
            await update.message.reply_text(
                "reasoning_effort cleared (follow provider/model default)."
            )
            return
        if val not in VALID_REASONING_EFFORTS:
            await update.message.reply_text(
                "Invalid reasoning_effort. Available: none, minimal, low, medium, high, xhigh."
            )
            return
        update_user_setting(user_id, "reasoning_effort", val)
        logger.info("%s set reasoning_effort = %s", ctx, val)
        await update.message.reply_text(f"reasoning_effort set to: {val}")
    elif key == "token_limit":
        try:
            limit = int(value)
            if limit >= 0:
                persona_name = get_current_persona_name(user_id)
                set_token_limit(user_id, limit, persona_name)
                logger.info("%s set token_limit = %s (persona=%s)", ctx, limit, persona_name)
                await update.message.reply_text(
                    f"Persona '{persona_name}' token_limit set to: {limit:,}"
                    + (" (unlimited)" if limit == 0 else "")
                )
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
            await update.message.reply_text(build_endpoint_invalid_message("/"))
            return

        update_user_setting(user_id, "tts_endpoint", normalized)
        logger.info("%s set endpoint = %s", ctx, normalized)
        await update.message.reply_text(f"endpoint set to: {normalized}")
    elif key == "provider":
        await _handle_provider_command(update, context, user_id, settings, ctx)
    elif key in ("title_model", "cron_model"):
        await _handle_specialized_model_set(update, user_id, settings, ctx, key, value)
    elif key == "stream_mode":
        val = value.strip().lower()
        if val in {"default", "time", "chars", "off"}:
            update_user_setting(user_id, "stream_mode", val)
            logger.info("%s set stream_mode = %s", ctx, val)
            mode_desc = {
                "default": "time + chars combined",
                "time": "update by time interval",
                "chars": "update by character interval",
                "off": "non-streaming (full response at once)",
            }
            await update.message.reply_text(
                f"stream_mode set to: {val} ({mode_desc.get(val, '')})\n"
                "Applies to both Telegram and Discord streaming output."
            )
        elif not val or val in {"off", "clear", "none"}:
            update_user_setting(user_id, "stream_mode", "")
            await update.message.reply_text(
                "stream_mode cleared (will use default mode)\n"
                "Default mode: time + chars combined"
            )
        else:
            current = settings.get("stream_mode", "") or "default"
            await update.message.reply_text(
                f"Current stream_mode: {current}\n"
                "Usage: /set stream_mode <mode>\n\n"
                "Available modes:\n"
                "- default: time + chars combined\n"
                "- time: update by time interval\n"
                "- chars: update by character interval\n"
                "- off: non-streaming, wait for full response (reduces rate limits)"
            )
    elif key == "show_thinking":
        val = value.strip().lower()
        if val in {"on", "true", "1", "yes", "y"}:
            update_user_setting(user_id, "show_thinking", True)
            logger.info("%s set show_thinking = on", ctx)
            await update.message.reply_text("show_thinking enabled.")
        elif val in {"off", "false", "0", "no", "n", "clear"}:
            update_user_setting(user_id, "show_thinking", False)
            logger.info("%s set show_thinking = off", ctx)
            await update.message.reply_text("show_thinking disabled.")
        else:
            await update.message.reply_text("Usage: /set show_thinking <on|off>")
    else:
        await update.message.reply_text(build_unknown_set_key_message(key))


async def _handle_specialized_model_set(
    update: Update, user_id: int, settings: dict, ctx: str, key: str, value: str,
) -> None:
    """Handle /set title_model or /set cron_model (shared logic)."""
    val = value.strip()
    if not val or val.lower() in {"off", "clear", "none"}:
        update_user_setting(user_id, key, "")
        await update.message.reply_text(f"{key} cleared (will use current provider + model)")
        return

    update_user_setting(user_id, key, val)
    logger.info("%s set %s = %s", ctx, key, val)

    if ":" in val:
        provider, model = val.split(":", 1)
        presets = settings.get("api_presets", {})
        found = any(k.lower() == provider.lower() for k in presets)
        if found:
            await update.message.reply_text(
                f"{key} set to: {val}\n"
                f"Provider: {provider} | Model: {model}"
            )
        else:
            available = ", ".join(presets.keys()) if presets else "(none)"
            await update.message.reply_text(
                f"{key} set to: {val}\n"
                f"Provider '{provider}' not found in presets.\n"
                f"Available: {available}\n"
                f"{build_provider_save_hint_message('/')}"
            )
    else:
        await update.message.reply_text(
            f"{key} set to: {val}\n"
            f"(uses current provider's API)"
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
        await update.message.reply_text(build_api_key_required_message("/"))
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
    p = "/"
    presets = settings.get("api_presets", {})
    if not presets:
        await update.message.reply_text(build_provider_no_saved_message(p))
        return

    lines = ["Saved Providers:\n"]
    for name, preset in presets.items():
        masked_key = _mask_api_key(preset.get("api_key", ""))
        lines.append(
            f"[{name}]\n"
            f"  base_url: {preset.get('base_url', '')}\n"
            f"  api_key: {masked_key}\n"
            f"  model: {preset.get('model', '')}"
        )

    lines.append(build_provider_list_usage_message(p))
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
        masked_key = _mask_api_key(settings["api_key"])
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

    elif sub == "load":
        if len(args) < 3:
            await update.message.reply_text("Usage: /set provider load <name>")
            return
        name = args[2]  # use original case
        if name not in presets:
            # Try case-insensitive match
            for k in presets:
                if k.lower() == name.lower():
                    name = k
                    break
            else:
                available = ", ".join(presets.keys()) if presets else "(none)"
                await update.message.reply_text(build_provider_not_found_available_message(name, available))
                return

        preset = presets[name]
        update_user_setting(user_id, "api_key", preset["api_key"])
        update_user_setting(user_id, "base_url", preset["base_url"])
        update_user_setting(user_id, "model", preset["model"])

        masked_key = _mask_api_key(preset.get("api_key", ""))
        logger.info("%s provider load %s", ctx, name)
        await update.message.reply_text(
            f"Loaded provider '{name}':\n"
            f"  base_url: {preset['base_url']}\n"
            f"  api_key: {masked_key}\n"
            f"  model: {preset['model']}"
        )

    else:
        await update.message.reply_text(build_provider_usage_message("/"))
