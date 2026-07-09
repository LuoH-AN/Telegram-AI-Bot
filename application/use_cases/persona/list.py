"""Render persona list text."""

from domain.services import (
    ensure_session,
    get_current_persona_name,
    get_message_count,
    get_personas,
    get_session_count,
    get_token_limit,
    get_token_usage,
)
from shared.utils.platform import build_persona_commands_message


def _mini_bar(used: int, limit: int) -> str:
    if limit <= 0:
        return ""
    percent = min(100.0, used / limit * 100)
    filled = round(percent / 10)
    status = "🔴" if percent >= 80 else ("🟡" if percent >= 50 else "🟢")
    return f" {status} {'🟩' * filled}{'⬜' * (10 - filled)} {percent:.0f}%"


def build_persona_list_text(user_id: int, *, command_prefix: str) -> str:
    personas = get_personas(user_id)
    current = get_current_persona_name(user_id)
    if not personas:
        return "📝 **No personas found.**"

    lines = ["👤 **Your personas:**\n"]
    for name, persona in personas.items():
        marker = "✅ " if name == current else "🔹 "
        usage = get_token_usage(user_id, name)
        session_id = ensure_session(user_id, name)
        msg_count = get_message_count(session_id)
        session_ct = get_session_count(user_id, name)
        bar = _mini_bar(usage["total_tokens"], get_token_limit(user_id, name))
        prompt_preview = persona["system_prompt"][:30]
        if len(persona["system_prompt"]) > 30:
            prompt_preview += "..."

        lines.append(f"{marker}**{name}**")
        from shared.utils.format import format_tokens

        lines.append(f"   💬 {msg_count} · 🗂️ {session_ct} · 🪙 {format_tokens(usage['total_tokens'])}{bar}")
        lines.append(f"   _{prompt_preview}_")
        lines.append("")

    lines.append(build_persona_commands_message(command_prefix))
    return "\n".join(lines)

