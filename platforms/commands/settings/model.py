"""Special `/set` handlers for provider-prefixed model keys."""

from __future__ import annotations

from services import update_user_setting
from utils.platform import build_provider_save_hint_message


async def handle_specialized_model_set(
    ctx,
    *,
    user_id: int,
    settings: dict,
    key: str,
    value: str,
    command_prefix: str,
) -> bool:
    val = value.strip()
    if not val or val.lower() in {"off", "clear", "none"}:
        update_user_setting(user_id, key, "")
        await ctx.reply_text(f"{key} cleared (will use current provider + model)")
        return True
    update_user_setting(user_id, key, val)
    if ":" not in val:
        await ctx.reply_text(f"{key} set to: {val}\n(uses current provider's API)")
        return True
    provider, model = val.split(":", 1)
    presets = settings.get("api_presets", {})
    found = any(name.lower() == provider.lower() for name in presets)
    if found:
        await ctx.reply_text(f"{key} set to: {val}\nProvider: {provider} | Model: {model}")
        return True
    available = ", ".join(presets.keys()) if presets else "(none)"
    await ctx.reply_text(
        f"{key} set to: {val}\nProvider '{provider}' not found in presets.\nAvailable: {available}\n{build_provider_save_hint_message(command_prefix)}"
    )
    return True
