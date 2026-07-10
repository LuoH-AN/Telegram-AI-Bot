"""Settings infrastructure.cache sync."""

from __future__ import annotations

import json

from infrastructure.config import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_SHOW_THINKING,
    DEFAULT_TELEGRAM_BUSY_MODE,
    DEFAULT_TELEGRAM_TOOL_PROGRESS,
    DEFAULT_TTS_ENDPOINT,
    DEFAULT_TTS_STYLE,
    DEFAULT_TTS_VOICE,
    normalize_telegram_busy_mode,
    normalize_telegram_tool_progress,
)
from infrastructure.database.loaders import parse_settings_row

SETTINGS_COLUMNS = [
    "user_id", "api_key", "base_url", "model", "temperature", "reasoning_effort", "show_thinking",
    "token_limit", "current_persona", "stream_mode", "busy_mode", "tool_progress",
    "tts_voice", "tts_style", "tts_endpoint",
    "api_presets", "title_model", "cron_model", "global_prompt", "timezone",
]
_PLACEHOLDERS = ", ".join(["%s"] * len(SETTINGS_COLUMNS))
_UPDATE = ", ".join(f"{col} = EXCLUDED.{col}" for col in SETTINGS_COLUMNS[1:])
UPSERT_SQL = (
    f"INSERT INTO user_settings ({', '.join(SETTINGS_COLUMNS)}) "
    f"VALUES ({_PLACEHOLDERS}) "
    f"ON CONFLICT (user_id) DO UPDATE SET {_UPDATE}"
)


def values(user_id: int, settings: dict) -> tuple:
    presets = settings.get("api_presets")
    presets_json = json.dumps(presets, ensure_ascii=False) if presets else None
    return (
        user_id,
        settings["api_key"],
        settings["base_url"],
        settings["model"],
        settings["temperature"],
        settings.get("reasoning_effort", DEFAULT_REASONING_EFFORT),
        bool(settings.get("show_thinking", DEFAULT_SHOW_THINKING)),
        settings["token_limit"],
        settings["current_persona"],
        settings.get("stream_mode", ""),
        normalize_telegram_busy_mode(
            settings.get("busy_mode"),
            default=DEFAULT_TELEGRAM_BUSY_MODE,
        ),
        normalize_telegram_tool_progress(
            settings.get("tool_progress"),
            default=DEFAULT_TELEGRAM_TOOL_PROGRESS,
        ),
        settings.get("tts_voice", DEFAULT_TTS_VOICE),
        settings.get("tts_style", DEFAULT_TTS_STYLE),
        settings.get("tts_endpoint", DEFAULT_TTS_ENDPOINT),
        presets_json,
        settings.get("title_model", ""),
        settings.get("cron_model", ""),
        settings.get("global_prompt", ""),
        settings.get("timezone", "Asia/Shanghai"),
    )


def load(cur, cache) -> None:
    cur.execute("SELECT * FROM user_settings")
    for row in cur.fetchall():
        cache.set_settings(row["user_id"], parse_settings_row(row))


def sync(cur, cache, dirty: dict) -> None:
    for user_id in dirty["settings"]:
        cur.execute(UPSERT_SQL, values(user_id, cache.get_settings(user_id)))
