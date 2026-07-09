"""Settings/usage text builders shared by platform runtimes."""

from domain.services import (
    get_current_persona,
    get_current_persona_name,
    get_last_turn_prompt,
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
    from infrastructure.ai.model_context import format_context_window_note

    model_display = settings["model"]
    ctx_note = format_context_window_note(settings["model"])
    if ctx_note:
        model_display = f"{settings['model']}  ({ctx_note})"
    return build_settings_summary_message(
        command_prefix,
        base_url=settings["base_url"],
        masked_api_key=mask_key(settings["api_key"]),
        model=model_display,
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
    from infrastructure.ai.model_context import get_model_context_limit

    persona_name = get_current_persona_name(user_id)
    usage = get_token_usage(user_id, persona_name)
    last_prompt = get_last_turn_prompt(user_id, persona_name)

    # The context bar measures how full the model's context window is right now,
    # using the most recent turn's prompt size (the actual context in play) vs
    # the current model's window. A manual token_limit, if tighter, caps it.
    model = (get_user_settings(user_id).get("model") or "").strip()
    model_ctx = get_model_context_limit(model)
    manual_limit = get_token_limit(user_id, persona_name)
    ceilings = [c for c in (model_ctx, manual_limit) if c and c > 0]

    message = (
        f"📊 **Token Usage** (Persona: `{persona_name}`)\n\n"
        f"• **Prompt (total):** {usage['prompt_tokens']:,}\n"
        f"• **Completion (total):** {usage['completion_tokens']:,}\n"
        f"• **Total:** {usage['total_tokens']:,}"
    )

    if ceilings and last_prompt:
        ceiling = min(ceilings)
        percent = min(100.0, last_prompt / ceiling * 100)
        label = "Context window" if ceiling == model_ctx else "Limit"
        source = f" · model `{model}`" if ceiling == model_ctx and model_ctx else ""
        message += (
            f"\n\n{_usage_bar(percent)}  **{percent:.1f}%** of context\n"
            f"Last turn: {last_prompt:,} / {ceiling:,}{source}"
        )
    elif ceilings:
        # No turn recorded yet (fresh session); just show the ceiling.
        ceiling = min(ceilings)
        label = "Context window" if ceiling == model_ctx else "Limit"
        source = f" · model `{model}`" if ceiling == model_ctx and model_ctx else ""
        message += f"\n\n{label}: {ceiling:,}{source}"
    else:
        message += "\n\n♾️ **No limit known** (model context unknown, no manual limit set)"
    total_all = get_total_tokens_all_personas(user_id)
    return f"{message}\n\n━━ **All Personas** ━━\n**Total:** {total_all:,}"
