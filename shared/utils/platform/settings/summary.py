"""Settings summary and API verification message builders."""

from __future__ import annotations


def build_settings_summary_message(
    prefix: str,
    *,
    base_url: str,
    masked_api_key: str,
    model: str,
    temperature: float,
    reasoning_effort: str,
    show_thinking: str,
    stream_mode: str,
    title_model: str,
    cron_model: str,
    persona_name: str,
    token_limit_display: str,
    global_prompt: str,
    prompt: str,
    providers_info: str,
    timezone: str = "Asia/Shanghai",
    lang: str = "en",
) -> str:
    on, off = "🟢", "⚪"
    thinking_icon = on if show_thinking == "on" else off
    if lang == "zh":
        thinking_text = "显示" if show_thinking == "on" else "隐藏"
        return (
            "⚙️ **当前设置**\n\n"
            "🔌 **连接**\n"
            f"• `base_url`：{base_url}\n"
            f"• `api_key`：{masked_api_key}\n"
            f"• `providers`：{providers_info}\n\n"
            "🤖 **模型**\n"
            f"• `model`：{model}\n"
            f"• `title_model`：{title_model}\n"
            f"• `cron_model`：{cron_model}\n\n"
            "🎨 **生成**\n"
            f"• `temperature`：{temperature}\n"
            f"• `reasoning_effort`：{reasoning_effort}\n"
            f"• `stream_mode`：{stream_mode}\n"
            f"• `show_thinking`：{thinking_icon} {thinking_text}\n\n"
            "🕐 **时间**\n"
            f"• `timezone`：{timezone}\n\n"
            "🎭 **角色**\n"
            f"• 当前角色：{persona_name}\n"
            f"• Token 限额：{token_limit_display}\n"
            f"• 全局提示词：{global_prompt}\n"
            f"• 角色提示词：{prompt}\n\n"
            f"💡 `{prefix}persona` · `{prefix}chat` · `{prefix}set provider`"
        )
    thinking_text = "shown" if show_thinking == "on" else "hidden"
    return (
        "⚙️ **Current Settings**\n\n"
        "🔌 **Connection**\n"
        f"• `base_url`: {base_url}\n"
        f"• `api_key`: {masked_api_key}\n"
        f"• `providers`: {providers_info}\n\n"
        "🤖 **Models**\n"
        f"• `model`: {model}\n"
        f"• `title_model`: {title_model}\n"
        f"• `cron_model`: {cron_model}\n\n"
        "🎨 **Generation**\n"
        f"• `temperature`: {temperature}\n"
        f"• `reasoning_effort`: {reasoning_effort}\n"
        f"• `stream_mode`: {stream_mode}\n"
        f"• `show_thinking`: {thinking_icon} {thinking_text}\n\n"
        "🕐 **Time**\n"
        f"• `timezone`: {timezone}\n\n"
        "🎭 **Persona**\n"
        f"• `current`: {persona_name}\n"
        f"• `token_limit`: {token_limit_display}\n"
        f"• `global_prompt`: {global_prompt}\n"
        f"• `prompt`: {prompt}\n\n"
        f"💡 `{prefix}persona` · `{prefix}chat` · `{prefix}set provider`"
    )


def build_api_key_verify_no_models_message(masked_key: str, *, lang: str = "en") -> str:
    if lang == "zh":
        return f"🔑 `api_key` 已设置为：`{masked_key}`\n\n⚠️ 未返回模型列表，暂时无法验证密钥。请检查 `base_url`。"
    return f"🔑 `api_key` set to: `{masked_key}`\n\n⚠️ Cannot verify key (no model list returned). Please check `base_url`."


def build_api_key_verify_failed_message(masked_key: str, *, lang: str = "en") -> str:
    if lang == "zh":
        return f"🔑 `api_key` 已设置为：`{masked_key}`\n\n❌ 无法验证密钥，请检查 `base_url` 和 `api_key`。"
    return f"🔑 `api_key` set to: `{masked_key}`\n\n❌ Cannot verify key. Please check `base_url` and `api_key`."
