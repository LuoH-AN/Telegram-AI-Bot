"""Settings and environment variable management."""

import os
import threading
from pathlib import Path

from dotenv import load_dotenv

from .util import (
    apply_env_text,
    build_default_jwt_secret,
    build_default_settings,
    normalize_bool,
)
from .app import normalize_reasoning_effort

_ENV_LOADED = False
_LOAD_LOCK = threading.Lock()


def load_env(*, force: bool = False) -> None:
    """Populate os.environ from .env and ENV_TEXT exactly once (idempotent).

    Runs at import time so module-level constants below see configured values.
    `force=True` re-applies (used by tests to reset isolation). Neither call
    overwrites keys already present in os.environ except via an explicit reset.
    """
    global _ENV_LOADED
    with _LOAD_LOCK:
        if _ENV_LOADED and not force:
            return
        load_dotenv()
        apply_env_text()
        _ENV_LOADED = True


load_env()

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_int_set(raw: str) -> set[int]:
    out: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


ADMIN_IDS = _parse_int_set(os.getenv("ADMIN_IDS", ""))
_owner_raw = os.getenv("OWNER_ID", "").strip()
OWNER_ID = int(_owner_raw) if _owner_raw.lstrip("-").isdigit() else None


def is_admin(user_id) -> bool:
    if user_id is None:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    return uid in ADMIN_IDS or (OWNER_ID is not None and uid == OWNER_ID)


def _parse_roots(raw: str, fallback: list[Path]) -> list[Path]:
    if not (raw or "").strip():
        return fallback
    roots: list[Path] = []
    for part in raw.replace(":", ",").split(","):
        part = part.strip()
        if part:
            roots.append(Path(part))
    return roots or fallback


TOOL_FILE_ROOTS = _parse_roots(os.getenv("TOOL_FILE_ROOTS", ""), [REPO_ROOT, Path("/data")])

DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "").rstrip("/")
TELEGRAM_NATIVE_DRAFTS = normalize_bool(os.getenv("TELEGRAM_NATIVE_DRAFTS", "1"), default=True)
TELEGRAM_RICH_MESSAGES = normalize_bool(os.getenv("TELEGRAM_RICH_MESSAGES", "1"), default=True)

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
STREAM_FORCE_UPDATE_INTERVAL = max(STREAM_UPDATE_INTERVAL, float(os.getenv("STREAM_FORCE_UPDATE_INTERVAL", "1.2")))
STREAM_UPDATE_MODE = os.getenv("STREAM_UPDATE_MODE", "default").lower()
STREAM_TIME_MODE_INTERVAL = max(0.5, float(os.getenv("STREAM_TIME_MODE_INTERVAL", "1.0")))
STREAM_CHARS_MODE_INTERVAL = max(10, int(os.getenv("STREAM_CHARS_MODE_INTERVAL", "100")))
HEALTH_CHECK_PORT = int(os.getenv("PORT", "8080"))

JWT_SECRET = os.getenv("JWT_SECRET", "").strip() or build_default_jwt_secret()

DEFAULT_SYSTEM_PROMPT = os.getenv("OPENAI_SYSTEM_PROMPT", "You are a helpful assistant.")
DEFAULT_TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoMultilingualNeural")
DEFAULT_TTS_STYLE = os.getenv("TTS_STYLE", "general")
DEFAULT_TTS_ENDPOINT = os.getenv("TTS_ENDPOINT", "")
DEFAULT_TTS_OUTPUT_FORMAT = os.getenv("TTS_OUTPUT_FORMAT", "ogg-24khz-16bit-mono-opus")
DEFAULT_REASONING_EFFORT = normalize_reasoning_effort(
    os.getenv("OPENAI_REASONING_EFFORT", ""),
)
DEFAULT_SHOW_THINKING = normalize_bool(os.getenv("SHOW_THINKING", "0"), default=False)
SHOW_THINKING_MAX_CHARS = max(200, int(os.getenv("SHOW_THINKING_MAX_CHARS", "1200")))


def get_default_settings() -> dict:
    return build_default_settings(
        default_reasoning_effort=DEFAULT_REASONING_EFFORT,
        default_show_thinking=DEFAULT_SHOW_THINKING,
        default_tts_voice=DEFAULT_TTS_VOICE,
        default_tts_style=DEFAULT_TTS_STYLE,
        default_tts_endpoint=DEFAULT_TTS_ENDPOINT,
    )


def get_default_persona() -> dict:
    return {"name": "default", "system_prompt": DEFAULT_SYSTEM_PROMPT}


def get_default_token_usage() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "token_limit": 0}
