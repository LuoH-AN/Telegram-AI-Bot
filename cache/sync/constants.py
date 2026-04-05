"""Shared sync constants and helpers."""

from __future__ import annotations

import json

from config import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_SHOW_THINKING,
    DEFAULT_TTS_ENDPOINT,
    DEFAULT_TTS_STYLE,
    DEFAULT_TTS_VOICE,
)

SETTINGS_COLUMNS = [
    "user_id", "api_key", "base_url", "model", "temperature", "reasoning_effort", "show_thinking",
    "token_limit", "current_persona", "stream_mode", "tts_voice", "tts_style", "tts_endpoint",
    "api_presets", "title_model", "cron_model", "global_prompt",
]
_SETTINGS_PLACEHOLDERS = ", ".join(["%s"] * len(SETTINGS_COLUMNS))
_SETTINGS_UPDATE = ", ".join(f"{col} = EXCLUDED.{col}" for col in SETTINGS_COLUMNS[1:])
SETTINGS_UPSERT_SQL = (
    f"INSERT INTO user_settings ({', '.join(SETTINGS_COLUMNS)}) "
    f"VALUES ({_SETTINGS_PLACEHOLDERS}) "
    f"ON CONFLICT (user_id) DO UPDATE SET {_SETTINGS_UPDATE}"
)

SYNC_LOG_LABELS = {
    "settings": "settings",
    "personas": "personas",
    "deleted_personas": "deleted personas",
    "new_sessions": "new sessions",
    "dirty_session_titles": "session titles",
    "deleted_sessions": "deleted sessions",
    "conversations": "conversations",
    "cleared_conversations": "cleared convs",
    "tokens": "token records",
    "new_memories": "new memories",
    "deleted_memory_ids": "deleted memories",
    "cleared_memories": "cleared memories",
    "new_cron_tasks": "new cron tasks",
    "updated_cron_tasks": "updated cron tasks",
    "deleted_cron_tasks": "deleted cron tasks",
    "new_skills": "new skills",
    "updated_skills": "updated skills",
    "deleted_skills": "deleted skills",
    "updated_skill_states": "updated skill states",
}


def settings_upsert_values(user_id: int, settings: dict) -> tuple:
    api_presets = settings.get("api_presets")
    presets_json = json.dumps(api_presets, ensure_ascii=False) if api_presets else None
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
        settings.get("tts_voice", DEFAULT_TTS_VOICE),
        settings.get("tts_style", DEFAULT_TTS_STYLE),
        settings.get("tts_endpoint", DEFAULT_TTS_ENDPOINT),
        presets_json,
        settings.get("title_model", ""),
        settings.get("cron_model", ""),
        settings.get("global_prompt", ""),
    )
