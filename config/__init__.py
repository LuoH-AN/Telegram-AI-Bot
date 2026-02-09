"""Configuration module."""

from .constants import (
    MAX_MESSAGE_LENGTH,
    STREAM_UPDATE_INTERVAL,
    DB_SYNC_INTERVAL,
    MODELS_PER_PAGE,
    TEXT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MIME_TYPE_MAP,
    MAX_FILE_SIZE,
    MAX_TEXT_CONTENT_LENGTH,
)
from .settings import (
    DATABASE_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_API_BASE,
    HEALTH_CHECK_PORT,
    DEFAULT_SYSTEM_PROMPT,
    get_default_settings,
    get_default_persona,
    get_default_token_usage,
)

__all__ = [
    # Constants
    "MAX_MESSAGE_LENGTH",
    "STREAM_UPDATE_INTERVAL",
    "DB_SYNC_INTERVAL",
    "MODELS_PER_PAGE",
    "TEXT_EXTENSIONS",
    "IMAGE_EXTENSIONS",
    "MIME_TYPE_MAP",
    "MAX_FILE_SIZE",
    "MAX_TEXT_CONTENT_LENGTH",
    # Settings
    "DATABASE_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_API_BASE",
    "HEALTH_CHECK_PORT",
    "DEFAULT_SYSTEM_PROMPT",
    "get_default_settings",
    "get_default_persona",
    "get_default_token_usage",
]
