"""Settings and environment variable management."""

import hashlib
import os
import re
import secrets
from dotenv import load_dotenv


_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _apply_env_content() -> None:
    """Hydrate env vars from ENV_CONTENT using KEY=VALUE lines.

    Explicit environment variables keep higher priority and are not overwritten.
    """
    raw = os.getenv("ENV_CONTENT", "")
    if not raw:
        return

    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Allow one-line secret payloads that encode newlines as "\n".
    if "\n" not in text and "\\n" in text:
        text = text.replace("\\n", "\n")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_NAME_RE.match(key):
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if key not in os.environ:
            os.environ[key] = value


# Load environment variables
load_dotenv()
_apply_env_content()

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_COMMAND_PREFIX = os.getenv("DISCORD_COMMAND_PREFIX", "!")
DISCORD_API_BASE = os.getenv("DISCORD_API_BASE", "").rstrip("/")
DISCORD_GATEWAY_BASE = os.getenv("DISCORD_GATEWAY_BASE", "").rstrip("/")
DISCORD_CDN_BASE = os.getenv("DISCORD_CDN_BASE", "").rstrip("/")
DISCORD_INVITE_BASE = os.getenv("DISCORD_INVITE_BASE", "").rstrip("/")
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
def _build_default_jwt_secret() -> str:
    """Build a stable default JWT secret when JWT_SECRET env is missing.

    Random-per-process secrets break auth when web/bot run in separate processes.
    """
    seed = (
        os.getenv("JWT_SECRET_SEED", "").strip()
        or
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("WEB_BASE_URL", "").strip()
        or TELEGRAM_BOT_TOKEN
        or DISCORD_BOT_TOKEN
        or os.getenv("OPENAI_API_KEY", "").strip()
        or "gemen-local-dev-secret"
    )
    return hashlib.sha256(f"gemen:{seed}".encode("utf-8")).hexdigest()


JWT_SECRET = os.getenv("JWT_SECRET", "").strip() or _build_default_jwt_secret()
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
        # Empty means "follow global default STREAM_UPDATE_MODE".
        "stream_mode": "",
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
        "global_prompt": "",
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
