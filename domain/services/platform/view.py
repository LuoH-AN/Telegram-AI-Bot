"""Settings/usage text builders shared by platform runtimes."""

from domain.services import (
    get_current_persona,
    get_current_persona_name,
    get_remaining_tokens,
    get_token_limit,
    get_token_usage,
    get_total_tokens_all_personas,
    get_usage_percentage,
    get_user_settings,
)
from shared.utils.platform import build_settings_summary_message

from .app import mask_key


def build_settings_text(user_id: int, *, command_prefix: str) -> str:
    settings = get_user_settings(user_id)
    persona_name = get_current_persona_name(user_id)
    persona = get_current_persona(user_id)
    token_limit = get_token_limit(user_id, persona_name)
    prompt = persona["system_prompt"]
    prompt_display = prompt[:80] + "..." if len(prompt) > 80 else prompt
    global_prompt = settings.get("global_prompt", "") or ""
    global_prompt_display = global_prompt[:80] + "..." if len(global_prompt) > 80 else global_prompt if global_prompt else "(none)"
    presets = settings.get("api_presets", {})
    return build_settings_summary_message(
        command_prefix,
        base_url=settings["base_url"],
        masked_api_key=mask_key(settings["api_key"]),
        model=settings["model"],
        temperature=settings["temperature"],
        reasoning_effort=settings.get("reasoning_effort", "") or "(provider/model default)",
        show_thinking="on" if settings.get("show_thinking") else "off",
        stream_mode=settings.get("stream_mode", "") or "default",
        title_model=settings.get("title_model", "") or "(current model)",
        cron_model=settings.get("cron_model", "") or "(current model)",
        persona_name=persona_name,
        token_limit_display=str(token_limit if token_limit > 0 else "unlimited"),
        global_prompt=global_prompt_display,
        prompt=prompt_display,
        providers_info=", ".join(presets.keys()) if presets else "(none)",
    )


def _usage_bar(percent: float) -> str:
    """10-segment Unicode progress bar with a status emoji."""
    filled = round(percent / 10)
    bar = "🟩" * filled + "⬜" * (10 - filled)
    status = "🔴" if percent >= 80 else ("🟡" if percent >= 50 else "🟢")
    return f"{status} {bar}"


def build_usage_text(user_id: int) -> str:
    persona_name = get_current_persona_name(user_id)
    usage = get_token_usage(user_id, persona_name)
    token_limit = get_token_limit(user_id, persona_name)
    message = (
        f"📊 **Token Usage** (Persona: `{persona_name}`)\n\n"
        f"• **Prompt:** {usage['prompt_tokens']:,}\n"
        f"• **Completion:** {usage['completion_tokens']:,}\n"
        f"• **Total:** {usage['total_tokens']:,}"
    )
    if token_limit > 0:
        percent = get_usage_percentage(user_id, persona_name) or 0
        message += (
            f"\n\n{_usage_bar(percent)}  **{percent:.1f}%**\n"
            f"Limit: {token_limit:,} · Remaining: {get_remaining_tokens(user_id, persona_name):,}"
        )
    else:
        message += "\n\n♾️ **Unlimited** (no limit set)"
    total_all = get_total_tokens_all_personas(user_id)
    return f"{message}\n\n━━ **All Personas** ━━\n**Total:** {total_all:,}"
