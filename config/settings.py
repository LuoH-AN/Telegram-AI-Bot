"""Settings and environment variable management."""

import os
import secrets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_COMMAND_PREFIX = os.getenv("DISCORD_COMMAND_PREFIX", "!")
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "").rstrip("/")
TELEGRAM_SEND_GLOBAL_RATE = float(os.getenv("TELEGRAM_SEND_GLOBAL_RATE", "25"))
TELEGRAM_SEND_GLOBAL_PERIOD = float(os.getenv("TELEGRAM_SEND_GLOBAL_PERIOD", "1"))
TELEGRAM_SEND_PER_CHAT_RATE = float(os.getenv("TELEGRAM_SEND_PER_CHAT_RATE", "1"))
TELEGRAM_SEND_PER_CHAT_PERIOD = float(os.getenv("TELEGRAM_SEND_PER_CHAT_PERIOD", "1"))
TELEGRAM_SEND_PER_CHAT_EDIT_RATE = float(os.getenv("TELEGRAM_SEND_PER_CHAT_EDIT_RATE", "3"))
TELEGRAM_SEND_PER_CHAT_EDIT_PERIOD = float(os.getenv("TELEGRAM_SEND_PER_CHAT_EDIT_PERIOD", "1"))
TELEGRAM_SEND_MAX_RETRIES = int(os.getenv("TELEGRAM_SEND_MAX_RETRIES", "8"))
TELEGRAM_SEND_RETRY_JITTER = float(os.getenv("TELEGRAM_SEND_RETRY_JITTER", "0.4"))
TELEGRAM_SEND_QUEUE_WARN_THRESHOLD = int(os.getenv("TELEGRAM_SEND_QUEUE_WARN_THRESHOLD", "100"))

STREAM_UPDATE_INTERVAL = max(0.1, float(os.getenv("STREAM_UPDATE_INTERVAL", "0.35")))
STREAM_MIN_UPDATE_CHARS = max(1, int(os.getenv("STREAM_MIN_UPDATE_CHARS", "24")))
STREAM_FORCE_UPDATE_INTERVAL = max(
    STREAM_UPDATE_INTERVAL,
    float(os.getenv("STREAM_FORCE_UPDATE_INTERVAL", "1.2")),
)
# Stream update mode: "default" (time + chars), "time" (time only), "chars" (chars only)
STREAM_UPDATE_MODE = os.getenv("STREAM_UPDATE_MODE", "default").lower()
# Settings for time/chars mode
STREAM_TIME_MODE_INTERVAL = max(0.5, float(os.getenv("STREAM_TIME_MODE_INTERVAL", "1.0")))
STREAM_CHARS_MODE_INTERVAL = max(10, int(os.getenv("STREAM_CHARS_MODE_INTERVAL", "100")))
HEALTH_CHECK_PORT = int(os.getenv("PORT", "8080"))

# JWT / Web dashboard
JWT_SECRET = os.getenv("JWT_SECRET", "") or secrets.token_urlsafe(32)
WEB_BASE_URL = os.getenv("WEB_BASE_URL", f"http://localhost:{HEALTH_CHECK_PORT}")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

# Default system prompt for new personas
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "OPENAI_SYSTEM_PROMPT", "You are a helpful assistant."
)

DEFAULT_TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoMultilingualNeural")
DEFAULT_TTS_STYLE = os.getenv("TTS_STYLE", "general")
DEFAULT_TTS_ENDPOINT = os.getenv("TTS_ENDPOINT", "")
DEFAULT_ENABLED_TOOLS = os.getenv(
    "ENABLED_TOOLS", "memory,search,fetch,wikipedia,tts"
)
DEFAULT_CRON_ENABLED_TOOLS = os.getenv(
    "CRON_ENABLED_TOOLS", "search,fetch,wikipedia,tts"
)
DEFAULT_TTS_OUTPUT_FORMAT = os.getenv("TTS_OUTPUT_FORMAT", "ogg-24khz-16bit-mono-opus")


def get_default_settings() -> dict:
    """Get default settings from environment variables."""
    return {
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
        "token_limit": 0,
        "current_persona": "default",
        "enabled_tools": DEFAULT_ENABLED_TOOLS,
        "cron_enabled_tools": DEFAULT_CRON_ENABLED_TOOLS,
        "tts_voice": DEFAULT_TTS_VOICE,
        "tts_style": DEFAULT_TTS_STYLE,
        "tts_endpoint": DEFAULT_TTS_ENDPOINT,
        "api_presets": {},
        "title_model": "",
        "cron_model": "",
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
        "token_limit": 0,
    }
