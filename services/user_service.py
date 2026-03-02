"""User settings service."""

from cache import cache
from .state_sync_service import refresh_user_state_from_db


def get_user_settings(user_id: int) -> dict:
    """Get global settings for a specific user."""
    refresh_user_state_from_db(user_id)
    return cache.get_settings(user_id)


def update_user_setting(user_id: int, key: str, value) -> None:
    """Update a specific setting for a user."""
    cache.update_settings(user_id, key, value)


def has_api_key(user_id: int) -> bool:
    """Check if user has an API key configured."""
    return bool(cache.get_settings(user_id)["api_key"])
