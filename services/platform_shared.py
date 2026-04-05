"""Shared helpers for platform entrypoints."""

from __future__ import annotations

import logging

import uvicorn

from ai import get_ai_client
from config import HEALTH_CHECK_PORT, DEFAULT_TTS_STYLE, DEFAULT_TTS_VOICE
from services import (
    get_current_persona,
    get_current_persona_name,
    get_token_limit,
    get_total_tokens_all_personas,
    get_token_usage,
    get_usage_percentage,
    get_remaining_tokens,
    get_user_settings,
    update_user_setting,
)
from utils.platform_parity import (
    build_provider_list_usage_message,
    build_provider_no_saved_message,
    build_provider_not_found_available_message,
    build_provider_usage_message,
    build_settings_summary_message,
)
from web.app import create_app

VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


def start_web_server(logger: logging.Logger, *, port: int = HEALTH_CHECK_PORT) -> None:
    """Start the shared FastAPI application."""
    app = create_app()
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("Web server started on port %d", port)
    server.run()


def mask_key(api_key: str) -> str:
    if not api_key:
        return "(empty)"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}...{api_key[-4:]}"


def normalize_stream_mode(mode: str | None) -> str:
    current = (mode or "").strip().lower()
    if current in {"default", "time", "chars", "off"}:
        return current
    return "default"


def normalize_reasoning_effort(value: str | None) -> str:
    current = (value or "").strip().lower()
    if current in VALID_REASONING_EFFORTS:
        return current
    return ""


def fetch_models_for_user(user_id: int) -> list[str]:
    try:
        client = get_ai_client(user_id)
        return client.list_models()
    except Exception:
        return []


def build_settings_text(user_id: int, *, command_prefix: str) -> str:
    settings = get_user_settings(user_id)
    persona_name = get_current_persona_name(user_id)
    persona = get_current_persona(user_id)
    token_limit = get_token_limit(user_id, persona_name)

    prompt = persona["system_prompt"]
    prompt_display = prompt[:80] + "..." if len(prompt) > 80 else prompt
    global_prompt = settings.get("global_prompt", "") or ""
    global_prompt_display = (
        global_prompt[:80] + "..."
        if len(global_prompt) > 80
        else global_prompt if global_prompt else "(none)"
    )

    tts_voice = settings.get("tts_voice", DEFAULT_TTS_VOICE)
    tts_style = settings.get("tts_style", DEFAULT_TTS_STYLE)
    tts_endpoint = settings.get("tts_endpoint", "") or "auto"
    stream_mode = settings.get("stream_mode", "") or "default"
    presets = settings.get("api_presets", {})
    presets_info = ", ".join(presets.keys()) if presets else "(none)"
    title_model_display = settings.get("title_model", "") or "(current model)"
    cron_model_display = settings.get("cron_model", "") or "(current model)"
    show_thinking = "on" if settings.get("show_thinking") else "off"

    return build_settings_summary_message(
        command_prefix,
        base_url=settings["base_url"],
        masked_api_key=mask_key(settings["api_key"]),
        model=settings["model"],
        temperature=settings["temperature"],
        reasoning_effort=settings.get("reasoning_effort", "") or "(provider/model default)",
        show_thinking=show_thinking,
        stream_mode=stream_mode,
        title_model=title_model_display,
        cron_model=cron_model_display,
        persona_name=persona_name,
        token_limit_display=str(token_limit if token_limit > 0 else "unlimited"),
        global_prompt=global_prompt_display,
        prompt=prompt_display,
        tts_voice=tts_voice,
        tts_style=tts_style,
        tts_endpoint=tts_endpoint,
        providers_info=presets_info,
    )


def build_provider_list_text(settings: dict, *, command_prefix: str) -> str:
    presets = settings.get("api_presets", {})
    if not presets:
        return build_provider_no_saved_message(command_prefix)

    lines = ["Saved Providers:\n"]
    for name, preset in presets.items():
        lines.append(
            f"[{name}]\n"
            f"  base_url: {preset.get('base_url', '')}\n"
            f"  api_key: {mask_key(preset.get('api_key', ''))}\n"
            f"  model: {preset.get('model', '')}"
        )
    lines.append(build_provider_list_usage_message(command_prefix))
    return "\n".join(lines)


def apply_provider_command(user_id: int, settings: dict, args: list[str], *, command_prefix: str) -> str:
    presets = settings.get("api_presets", {})
    if not args:
        return build_provider_list_text(settings, command_prefix=command_prefix)

    sub = args[0].lower()
    if sub == "list":
        return build_provider_list_text(settings, command_prefix=command_prefix)

    if sub == "save":
        if len(args) < 2:
            return f"Usage: {command_prefix}set provider save <name>"
        name = args[1]
        presets[name] = {
            "api_key": settings["api_key"],
            "base_url": settings["base_url"],
            "model": settings["model"],
        }
        update_user_setting(user_id, "api_presets", presets)
        return (
            f"Provider '{name}' saved:\n"
            f"  base_url: {settings['base_url']}\n"
            f"  api_key: {mask_key(settings['api_key'])}\n"
            f"  model: {settings['model']}"
        )

    if sub == "delete":
        if len(args) < 2:
            return f"Usage: {command_prefix}set provider delete <name>"
        name = args[1]
        if name not in presets:
            return f"Provider '{name}' not found."
        del presets[name]
        update_user_setting(user_id, "api_presets", presets)
        return f"Provider '{name}' deleted."

    if sub == "load":
        if len(args) < 2:
            return f"Usage: {command_prefix}set provider load <name>"
        name = args[1]
        if name not in presets:
            matched = next((key for key in presets if key.lower() == name.lower()), None)
            if matched is None:
                available = ", ".join(presets.keys()) if presets else "(none)"
                return build_provider_not_found_available_message(name, available)
            name = matched
        preset = presets[name]
        update_user_setting(user_id, "api_key", preset["api_key"])
        update_user_setting(user_id, "base_url", preset["base_url"])
        update_user_setting(user_id, "model", preset["model"])
        return (
            f"Loaded provider '{name}':\n"
            f"  base_url: {preset['base_url']}\n"
            f"  api_key: {mask_key(preset.get('api_key', ''))}\n"
            f"  model: {preset['model']}"
        )

    return build_provider_usage_message(command_prefix)


def build_usage_text(user_id: int) -> str:
    persona_name = get_current_persona_name(user_id)
    usage = get_token_usage(user_id, persona_name)
    token_limit = get_token_limit(user_id, persona_name)

    prompt_tokens = usage["prompt_tokens"]
    completion_tokens = usage["completion_tokens"]
    total_tokens = usage["total_tokens"]
    message = (
        f"Token Usage (Persona: {persona_name}):\n\n"
        f"Prompt tokens:     {prompt_tokens:,}\n"
        f"Completion tokens: {completion_tokens:,}\n"
        f"Total tokens:      {total_tokens:,}\n"
    )

    if token_limit > 0:
        remaining = get_remaining_tokens(user_id, persona_name)
        percentage = get_usage_percentage(user_id, persona_name) or 0
        message += (
            f"\nLimit:     {token_limit:,}\n"
            f"Remaining: {remaining:,}\n"
            f"Usage:     {percentage:.1f}%\n"
        )
    else:
        message += "\nLimit: Unlimited"

    total_all = get_total_tokens_all_personas(user_id)
    message += f"\n\n--- All Personas ---\nTotal tokens: {total_all:,}"
    return message
