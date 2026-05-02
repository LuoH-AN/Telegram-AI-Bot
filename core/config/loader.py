"""Configuration loader with caching."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .schema import AppConfig

if TYPE_CHECKING:
    pass

_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get application configuration (cached)."""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
        _config.validate()
    return _config


def reload_config() -> AppConfig:
    """Force reload configuration from environment."""
    global _config
    _config = AppConfig.from_env()
    _config.validate()
    return _config


def clear_config() -> None:
    """Clear cached configuration (for testing)."""
    global _config
    _config = None
