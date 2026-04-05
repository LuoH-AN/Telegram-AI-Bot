"""Persona/session/chat related message builders."""

from __future__ import annotations


def build_persona_new_usage_message(prefix: str) -> str:
    return f"Usage: {prefix}persona new <name> [system prompt]\n\nExample:\n{prefix}persona new coder You are a coding assistant."


def build_persona_created_message(name: str, prefix: str) -> str:
    return f"Created and switched to persona: {name}\n\nUse {prefix}persona prompt <text> to set system prompt."


def build_persona_prompt_overview_message(name: str, prompt: str, prefix: str) -> str:
    return f"Current persona: {name}\n\nPrompt: {prompt}\n\nUsage: {prefix}persona prompt <new prompt>"


def build_persona_not_found_message(name: str, prefix: str) -> str:
    return f"Persona '{name}' does not exist. Use {prefix}persona new {name} to create."


def build_persona_commands_message(prefix: str) -> str:
    return (
        "Commands:\n"
        f"{prefix}persona <name> - switch\n"
        f"{prefix}persona new <name> - create\n"
        f"{prefix}persona delete <name> - delete\n"
        f"{prefix}persona prompt <text> - set prompt"
    )


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
