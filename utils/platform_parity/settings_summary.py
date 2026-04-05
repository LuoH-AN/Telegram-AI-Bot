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
) -> str:
    return (
        "Current Settings:\n\n"
        f"base_url: {base_url}\n"
        f"api_key: {masked_api_key}\n"
        f"model: {model}\n"
        f"temperature: {temperature}\n"
        f"reasoning_effort: {reasoning_effort}\n"
        f"show_thinking: {show_thinking}\n"
        f"stream_mode: {stream_mode}\n"
        f"title_model: {title_model}\n"
        f"cron_model: {cron_model}\n"
        f"persona: {persona_name}\n"
        f"token_limit({persona_name}): {token_limit_display}\n"
        f"global_prompt: {global_prompt}\n"
        f"prompt: {prompt}\n\n"
        f"providers: {providers_info}\n\n"
        f"Use {prefix}persona to manage personas and prompts.\n"
        f"Use {prefix}chat to manage chat sessions.\n"
        f"Use {prefix}set provider to manage API providers."
    )


def build_api_key_verify_no_models_message(masked_key: str) -> str:
    return f"api_key set to: {masked_key}\nCannot verify key (no model list returned). Please check base_url."


def build_api_key_verify_failed_message(masked_key: str) -> str:
    return f"api_key set to: {masked_key}\nCannot verify key. Please check base_url and api_key."
