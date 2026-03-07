"""Persona management service."""

from config import DEFAULT_SYSTEM_PROMPT
from cache import cache


def get_personas(user_id: int) -> dict[str, dict]:
    """Get all personas for a user."""
    return cache.get_personas(user_id)


def get_persona(user_id: int, name: str) -> dict | None:
    """Get a specific persona by name."""
    return cache.get_persona(user_id, name)


def get_current_persona(user_id: int) -> dict:
    """Get the current active persona for a user."""
    return cache.get_current_persona(user_id)


def get_current_persona_name(user_id: int) -> str:
    """Get the name of the current persona."""
    return cache.get_current_persona_name(user_id)


def get_system_prompt(user_id: int, persona_name: str | None = None) -> str:
    """Get a persona's system prompt combined with the global prompt."""
    if persona_name is None:
        persona = cache.get_current_persona(user_id)
    else:
        persona = cache.get_persona(user_id, persona_name) or cache.get_current_persona(user_id)
    settings = cache.get_settings(user_id)
    global_prompt = settings.get("global_prompt", "") or ""
    persona_prompt = persona.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
    if global_prompt:
        return f"{global_prompt}\n\n{persona_prompt}"
    return persona_prompt


def switch_persona(user_id: int, name: str) -> bool:
    """Switch to a persona by name. Creates it if doesn't exist.

    Returns True if switched to existing persona, False if created new one.
    """
    personas = cache.get_personas(user_id)
    exists = name in personas

    if not exists:
        cache.create_persona(user_id, name, DEFAULT_SYSTEM_PROMPT)

    cache.set_current_persona(user_id, name)
    return exists


def create_persona(user_id: int, name: str, system_prompt: str = None) -> bool:
    """Create a new persona. Returns False if already exists."""
    if system_prompt is None:
        system_prompt = DEFAULT_SYSTEM_PROMPT
    return cache.create_persona(user_id, name, system_prompt)


def delete_persona(user_id: int, name: str) -> bool:
    """Delete a persona. Cannot delete 'default'. Returns False if failed."""
    return cache.delete_persona(user_id, name)


def update_persona_prompt(user_id: int, name: str, prompt: str) -> bool:
    """Update a persona's system prompt. Returns False if persona not found."""
    return cache.update_persona_prompt(user_id, name, prompt)


def update_current_prompt(user_id: int, prompt: str) -> bool:
    """Update the current persona's system prompt."""
    name = cache.get_current_persona_name(user_id)
    return cache.update_persona_prompt(user_id, name, prompt)


def persona_exists(user_id: int, name: str) -> bool:
    """Check if a persona exists."""
    return name in cache.get_personas(user_id)
