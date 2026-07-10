"""Settings/usage text builders shared by platform runtimes."""

from domain.services import (
    get_current_persona,
    get_current_persona_name,
    get_last_turn_prompt,
    get_token_limit,
    get_token_usage,
    get_total_tokens_all_personas,
    get_user_settings,
)
from shared.utils.platform import build_settings_summary_message

from .app import mask_key


def build_settings_text(user_id: int, *, command_prefix: str, lang: str = "en") -> str:
    settings = get_user_settings(user_id)
    persona_name = get_current_persona_name(user_id)
    persona = get_current_persona(user_id)
    token_limit = get_token_limit(user_id, persona_name)
    prompt = persona["system_prompt"]
    prompt_display = prompt[:80] + "..." if len(prompt) > 80 else prompt
    global_prompt = settings.get("global_prompt", "") or ""
    none_text = "（无）" if lang == "zh" else "(none)"
    current_model_text = "（当前模型）" if lang == "zh" else "(current model)"
    if len(global_prompt) > 80:
        global_prompt_display = global_prompt[:80] + "..."
    else:
        global_prompt_display = global_prompt or none_text
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
        reasoning_effort=settings.get("reasoning_effort", "")
        or ("（提供商/模型默认）" if lang == "zh" else "(provider/model default)"),
        show_thinking="on" if settings.get("show_thinking") else "off",
        stream_mode=settings.get("stream_mode", "") or "default",
        title_model=settings.get("title_model", "") or current_model_text,
        cron_model=settings.get("cron_model", "") or current_model_text,
        persona_name=persona_name,
        token_limit_display=str(
            token_limit if token_limit > 0 else ("不限" if lang == "zh" else "unlimited")
        ),
        global_prompt=global_prompt_display,
        prompt=prompt_display,
        providers_info=", ".join(presets.keys()) if presets else none_text,
        timezone=settings.get("timezone", "Asia/Shanghai"),
        lang=lang,
    )


def _usage_bar(percent: float) -> str:
    """10-segment Unicode progress bar with a status emoji."""
    filled = round(percent / 10)
    bar = "🟩" * filled + "⬜" * (10 - filled)
    status = "🔴" if percent >= 80 else ("🟡" if percent >= 50 else "🟢")
    return f"{status} {bar}"


def build_usage_text(user_id: int, *, lang: str = "en") -> str:
    from infrastructure.ai.model_context import get_model_context_limit

    persona_name = get_current_persona_name(user_id)
    usage = get_token_usage(user_id, persona_name)
    last_prompt = get_last_turn_prompt(user_id, persona_name)

    # The context bar measures how full the model's context window is, using the
    # most recent turn's prompt size (the actual context in play). Falls back to
    # cumulative prompt tokens if no turn is recorded for this persona (e.g. a
    # process restart or persona switch) so the bar is still meaningful.
    model = (get_user_settings(user_id).get("model") or "").strip()
    model_ctx = get_model_context_limit(model)
    manual_limit = get_token_limit(user_id, persona_name)
    ceilings = [c for c in (model_ctx, manual_limit) if c and c > 0]

    from shared.utils.format import format_tokens

    if lang == "zh":
        message = (
            f"📊 **Token 用量**（角色：`{persona_name}`）\n\n"
            f"• **输入累计：** {format_tokens(usage['prompt_tokens'])}\n"
            f"• **输出累计：** {format_tokens(usage['completion_tokens'])}\n"
            f"• **总计：** {format_tokens(usage['total_tokens'])}"
        )
    else:
        message = (
            f"📊 **Token Usage** (Persona: `{persona_name}`)\n\n"
            f"• **Prompt (total):** {format_tokens(usage['prompt_tokens'])}\n"
            f"• **Completion (total):** {format_tokens(usage['completion_tokens'])}\n"
            f"• **Total:** {format_tokens(usage['total_tokens'])}"
        )

    if ceilings:
        ceiling = min(ceilings)
        source_label = "模型" if lang == "zh" else "model"
        source = f" · {source_label} `{model}`" if ceiling == model_ctx and model_ctx else ""
        used = last_prompt or usage["prompt_tokens"]
        if used > 0:
            if lang == "zh":
                note = "上轮输入" if last_prompt else "输入累计"
            else:
                note = "Last turn" if last_prompt else "Prompt (total)"
            percent = min(100.0, used / ceiling * 100) if ceiling else 0
            remaining_capacity = max(0, ceiling - used)
            if lang == "zh":
                message += (
                    f"\n\n{_usage_bar(percent)}  已使用上下文 **{percent:.1f}%**\n"
                    f"{note}：{format_tokens(used)} / {format_tokens(ceiling)}{source}\n"
                    f"剩余容量：{format_tokens(remaining_capacity)}"
                )
            else:
                message += (
                    f"\n\n{_usage_bar(percent)}  **{percent:.1f}%** of context\n"
                    f"{note}: {format_tokens(used)} / {format_tokens(ceiling)}{source}\n"
                    f"Remaining capacity: {format_tokens(remaining_capacity)}"
                )
            if percent >= 80:
                message += (
                    "\n⚠️ 上下文即将用满，建议尽快新建会话。"
                    if lang == "zh"
                    else "\n⚠️ Context is nearly full. Consider starting a new chat soon."
                )
            elif percent >= 60:
                message += (
                    "\n💡 上下文占用较高，新建会话可以释放空间。"
                    if lang == "zh"
                    else "\n💡 Context usage is growing; a new chat will improve headroom."
                )
        else:
            if lang == "zh":
                label = "上下文窗口" if ceiling == model_ctx else "限额"
            else:
                label = "Context window" if ceiling == model_ctx else "Limit"
            separator = "：" if lang == "zh" else ": "
            message += f"\n\n{label}{separator}{format_tokens(ceiling)}{source}"
    else:
        message += (
            "\n\n♾️ **暂无已知限额**（模型上下文未知，且未设置手动限额）"
            if lang == "zh"
            else "\n\n♾️ **No limit known** (model context unknown, no manual limit set)"
        )
    total_all = get_total_tokens_all_personas(user_id)
    if lang == "zh":
        return f"{message}\n\n━━ **全部角色** ━━\n**总计：** {format_tokens(total_all)}"
    return f"{message}\n\n━━ **All Personas** ━━\n**Total:** {format_tokens(total_all)}"
