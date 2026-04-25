"""Provider preset text/action helpers for shared platform commands."""

from services import update_user_setting
from utils.platform import (
    build_provider_list_usage_message,
    build_provider_no_saved_message,
    build_provider_not_found_available_message,
    build_provider_usage_message,
)

from .app import mask_key


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
    if not args or args[0].lower() == "list":
        return build_provider_list_text(settings, command_prefix=command_prefix)
    sub = args[0].lower()
    if sub == "save":
        if len(args) < 2:
            return f"Usage: {command_prefix}set provider save <name>"
        name = args[1]
        presets[name] = {"api_key": settings["api_key"], "base_url": settings["base_url"], "model": settings["model"]}
        update_user_setting(user_id, "api_presets", presets)
        return f"Provider '{name}' saved:\n  base_url: {settings['base_url']}\n  api_key: {mask_key(settings['api_key'])}\n  model: {settings['model']}"
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
            match = next((key for key in presets if key.lower() == name.lower()), None)
            if match is None:
                available = ", ".join(presets.keys()) if presets else "(none)"
                return build_provider_not_found_available_message(name, available)
            name = match
        preset = presets[name]
        update_user_setting(user_id, "api_key", preset["api_key"])
        update_user_setting(user_id, "base_url", preset["base_url"])
        update_user_setting(user_id, "model", preset["model"])
        return f"Loaded provider '{name}':\n  base_url: {preset['base_url']}\n  api_key: {mask_key(preset.get('api_key', ''))}\n  model: {preset['model']}"
    return build_provider_usage_message(command_prefix)
