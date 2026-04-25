"""Chat/session message builders."""

from __future__ import annotations


def build_chat_no_sessions_message(persona_name: str, prefix: str) -> str:
    return f"Persona '{persona_name}' has no sessions yet.\nSend a message to auto-create, or use {prefix}chat new"


def build_chat_unknown_subcommand_message(prefix: str) -> str:
    return (
        "Unknown subcommand. Usage:\n\n"
        f"{prefix}chat - list sessions\n"
        f"{prefix}chat new [title] - create session\n"
        f"{prefix}chat <number> - switch session\n"
        f"{prefix}chat rename <title> - rename\n"
        f"{prefix}chat delete <number> - delete"
    )


def build_chat_commands_message(prefix: str) -> str:
    return (
        f"{prefix}chat <number> - switch\n"
        f"{prefix}chat new [title] - create session\n"
        f"{prefix}chat rename <title> - rename\n"
        f"{prefix}chat delete <number> - delete"
    )
