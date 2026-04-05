"""Render persona list text."""

from services import (
    ensure_session,
    get_current_persona_name,
    get_message_count,
    get_personas,
    get_session_count,
    get_token_usage,
)
from utils.platform_parity import build_persona_commands_message


def build_persona_list_text(user_id: int, *, command_prefix: str) -> str:
    personas = get_personas(user_id)
    current = get_current_persona_name(user_id)
    if not personas:
        return "No personas found."

    lines = ["Your personas:\n"]
    for name, persona in personas.items():
        marker = "> " if name == current else "  "
        usage = get_token_usage(user_id, name)
        session_id = ensure_session(user_id, name)
        msg_count = get_message_count(session_id)
        session_ct = get_session_count(user_id, name)
        prompt_preview = persona["system_prompt"][:30]
        if len(persona["system_prompt"]) > 30:
            prompt_preview += "..."

        lines.append(f"{marker}{name}")
        lines.append(f"    {msg_count} msgs | {session_ct} sessions | {usage['total_tokens']:,} tokens")
        lines.append(f"    {prompt_preview}")
        lines.append("")

    lines.append(build_persona_commands_message(command_prefix))
    return "\n".join(lines)

