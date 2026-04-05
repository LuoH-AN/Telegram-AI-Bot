"""Persona creation use case."""

from services import create_persona, switch_persona
from utils.platform_parity import build_persona_created_message, build_persona_new_usage_message


def create_persona_text(
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    if len(args) < 2:
        return build_persona_new_usage_message(command_prefix)

    name = args[1]
    prompt = " ".join(args[2:]) if len(args) > 2 else None
    if create_persona(user_id, name, prompt):
        switch_persona(user_id, name)
        return build_persona_created_message(name, command_prefix)
    return f"Persona '{name}' already exists."

