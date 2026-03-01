"""Persona management service."""

from config import DEFAULT_SYSTEM_PROMPT
from cache import cache
from .state_sync_service import refresh_user_state_from_db


def get_personas(user_id: int) -> dict[str, dict]:
    """Get all personas for a user."""
    refresh_user_state_from_db(user_id)
    return cache.get_personas(user_id)


def get_persona(user_id: int, name: str) -> dict | None:
    """Get a specific persona by name."""
    refresh_user_state_from_db(user_id)
    return cache.get_persona(user_id, name)


def get_current_persona(user_id: int) -> dict:
    """Get the current active persona for a user."""
    refresh_user_state_from_db(user_id)
    return cache.get_current_persona(user_id)


def get_current_persona_name(user_id: int) -> str:
    """Get the name of the current persona."""
    refresh_user_state_from_db(user_id)
    return cache.get_current_persona_name(user_id)


def get_system_prompt(user_id: int) -> str:
    """Get the system prompt of the current persona (combined with global prompt)."""
    refresh_user_state_from_db(user_id)
    persona = cache.get_current_persona(user_id)
    settings = cache.get_settings(user_id)
    global_prompt = settings.get("global_prompt", "") or ""
    persona_prompt = persona.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
    # Combine global_prompt with persona's system_prompt
    if global_prompt:
        return f"{global_prompt}\n\n{persona_prompt}"
    return persona_prompt


def get_global_prompt(user_id: int) -> str:
    """Get the global prompt for a user."""
    refresh_user_state_from_db(user_id)
    settings = cache.get_settings(user_id)
    return settings.get("global_prompt", "") or ""


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


def get_persona_count(user_id: int) -> int:
    """Get the number of personas for a user."""
    return len(cache.get_personas(user_id))
