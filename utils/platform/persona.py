"""Persona message builders."""

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
