"""Persona prompt update use case."""

from services import get_current_persona, get_current_persona_name, update_current_prompt
from utils.platform import build_persona_prompt_overview_message


def update_persona_prompt_text(
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    if len(args) < 2:
        persona = get_current_persona(user_id)
        return build_persona_prompt_overview_message(
            persona["name"],
            persona["system_prompt"],
            command_prefix,
        )

    prompt = " ".join(args[1:])
    update_current_prompt(user_id, prompt)
    name = get_current_persona_name(user_id)
    return f"Updated prompt for '{name}'."

