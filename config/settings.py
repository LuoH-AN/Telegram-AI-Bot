"""Settings and environment variable management."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "").rstrip("/")
HEALTH_CHECK_PORT = int(os.getenv("PORT", "8080"))

# Default system prompt for new personas
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "OPENAI_SYSTEM_PROMPT", "You are a helpful assistant."
)


def get_default_settings() -> dict:
    """Get default settings from environment variables."""
    return {
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
        "token_limit": 0,
        "current_persona": "default",
        "enabled_tools": "memory,search,fetch,wikipedia",
    }


def get_default_persona() -> dict:
    """Get default persona structure."""
    return {
        "name": "default",
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
    }


def get_default_token_usage() -> dict:
    """Get default token usage structure."""
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
