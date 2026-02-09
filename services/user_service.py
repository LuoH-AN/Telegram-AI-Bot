"""User settings service."""

from cache import cache


def get_user_settings(user_id: int) -> dict:
    """Get global settings for a specific user."""
    return cache.get_settings(user_id)


def update_user_setting(user_id: int, key: str, value) -> None:
    """Update a specific setting for a user."""
    cache.update_settings(user_id, key, value)


def get_api_key(user_id: int) -> str:
    """Get API key for a user."""
    return cache.get_settings(user_id)["api_key"]


def get_base_url(user_id: int) -> str:
    """Get base URL for a user."""
    return cache.get_settings(user_id)["base_url"]


def get_model(user_id: int) -> str:
    """Get model for a user."""
    return cache.get_settings(user_id)["model"]


def get_temperature(user_id: int) -> float:
    """Get temperature for a user."""
    return cache.get_settings(user_id)["temperature"]


def has_api_key(user_id: int) -> bool:
    """Check if user has an API key configured."""
    return bool(cache.get_settings(user_id)["api_key"])
