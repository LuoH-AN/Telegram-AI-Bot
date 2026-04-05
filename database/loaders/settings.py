"""Settings row parser."""

from __future__ import annotations

from collections.abc import Mapping

from config import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_SHOW_THINKING,
    DEFAULT_TTS_ENDPOINT,
    DEFAULT_TTS_STYLE,
    DEFAULT_TTS_VOICE,
)

from .json_utils import parse_json_object


def _parse_show_thinking(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return DEFAULT_SHOW_THINKING
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return DEFAULT_SHOW_THINKING


def parse_settings_row(row: Mapping) -> dict:
    return {
        "api_key": row.get("api_key") or "",
        "base_url": row.get("base_url") or "https://api.openai.com/v1",
        "model": row.get("model") or "gpt-4o",
        "temperature": row.get("temperature") or 0.7,
        "reasoning_effort": row.get("reasoning_effort") or DEFAULT_REASONING_EFFORT,
        "show_thinking": _parse_show_thinking(row.get("show_thinking")),
        "stream_mode": row.get("stream_mode") or "",
        "token_limit": row.get("token_limit") or 0,
        "current_persona": row.get("current_persona") or "default",
        "tts_voice": row.get("tts_voice") or DEFAULT_TTS_VOICE,
        "tts_style": row.get("tts_style") or DEFAULT_TTS_STYLE,
        "tts_endpoint": row.get("tts_endpoint") or DEFAULT_TTS_ENDPOINT,
        "api_presets": parse_json_object(row.get("api_presets")),
        "title_model": row.get("title_model") or "",
        "cron_model": row.get("cron_model") or "",
        "global_prompt": row.get("global_prompt") or "",
    }

