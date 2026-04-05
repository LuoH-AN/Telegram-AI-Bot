"""Persona switching use case."""

from services import (
    ensure_session,
    get_current_persona,
    get_current_session,
    get_message_count,
    get_session_count,
    get_token_usage,
    persona_exists,
    switch_persona,
)
from utils.platform_parity import build_persona_not_found_message


def switch_persona_text(
    user_id: int,
    name: str,
    *,
    command_prefix: str,
) -> str:
    if not persona_exists(user_id, name):
        return build_persona_not_found_message(name, command_prefix)

    switch_persona(user_id, name)
    persona = get_current_persona(user_id)
    usage = get_token_usage(user_id, name)
    session_id = ensure_session(user_id, name)
    msg_count = get_message_count(session_id)
    session_ct = get_session_count(user_id, name)
    current_session = get_current_session(user_id, name)
    session_title = (current_session.get("title") or "New Chat") if current_session else "New Chat"
    prompt_text = persona["system_prompt"]
    if len(prompt_text) > 100:
        prompt_text = prompt_text[:100] + "..."

    return (
        f"Switched to: {name}\n\n"
        f"Messages: {msg_count}\n"
        f"Sessions: {session_ct}\n"
        f"Current session: {session_title}\n"
        f"Tokens: {usage['total_tokens']:,}\n\n"
        f"Prompt: {prompt_text}"
    )

