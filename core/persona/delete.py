"""Persona deletion use case."""

from services import delete_persona


def delete_persona_text(
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    if len(args) < 2:
        return f"Usage: {command_prefix}persona delete <name>"

    name = args[1]
    if name == "default":
        return "Cannot delete the default persona."
    if delete_persona(user_id, name):
        return f"Deleted persona: {name}"
    return f"Persona '{name}' not found."

