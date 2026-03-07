"""Shared DB-row-to-dict parse functions.

Both ``cache/sync.py`` (full load at startup) and
``services/state_sync_service.py`` (per-user refresh) need identical
logic for converting raw database rows into the in-memory dict
structures used by the cache layer.  Centralising the parse helpers
here avoids drift between the two code paths.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from config import (
    DEFAULT_TTS_VOICE,
    DEFAULT_TTS_STYLE,
    DEFAULT_TTS_ENDPOINT,
    DEFAULT_ENABLED_TOOLS,
    DEFAULT_REASONING_EFFORT,
)
from utils.tooling import normalize_tools_csv, resolve_cron_tools_csv


def parse_settings_row(row: Mapping) -> dict:
    """Convert a ``user_settings`` DB row into a cache-ready settings dict."""
    api_presets: dict = {}
    if row.get("api_presets"):
        try:
            api_presets = json.loads(row["api_presets"])
        except (json.JSONDecodeError, TypeError):
            pass

    enabled_tools = normalize_tools_csv(
        row.get("enabled_tools") or DEFAULT_ENABLED_TOOLS
    )
    cron_tools = normalize_tools_csv(
        row.get("cron_enabled_tools")
        or resolve_cron_tools_csv({"enabled_tools": enabled_tools})
    )

    return {
        "api_key": row.get("api_key") or "",
        "base_url": row.get("base_url") or "https://api.openai.com/v1",
        "model": row.get("model") or "gpt-4o",
        "temperature": row.get("temperature") or 0.7,
        "reasoning_effort": row.get("reasoning_effort") or DEFAULT_REASONING_EFFORT,
        "stream_mode": row.get("stream_mode") or "",
        "token_limit": row.get("token_limit") or 0,
        "current_persona": row.get("current_persona") or "default",
        "enabled_tools": enabled_tools,
        "cron_enabled_tools": cron_tools,
        "tts_voice": row.get("tts_voice") or DEFAULT_TTS_VOICE,
        "tts_style": row.get("tts_style") or DEFAULT_TTS_STYLE,
        "tts_endpoint": row.get("tts_endpoint") or DEFAULT_TTS_ENDPOINT,
        "api_presets": api_presets,
        "title_model": row.get("title_model") or "",
        "cron_model": row.get("cron_model") or "",
        "global_prompt": row.get("global_prompt") or "",
    }


def parse_persona_row(row: Mapping) -> dict:
    """Convert a ``user_personas`` DB row into a cache-ready persona dict."""
    return {
        "name": row["name"],
        "system_prompt": row["system_prompt"],
        "current_session_id": row.get("current_session_id"),
    }


def parse_session_row(row: Mapping, *, user_id: int | None = None) -> dict:
    """Convert a ``user_sessions`` DB row into a cache-ready session dict.

    If the row already contains ``user_id`` it is used directly; otherwise
    the caller-supplied *user_id* is filled in (needed by
    ``state_sync_service`` where the query doesn't return ``user_id``).
    """
    return {
        "id": row["id"],
        "user_id": row.get("user_id") or user_id,
        "persona_name": row["persona_name"],
        "title": row.get("title"),
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
    }


def parse_conversation_row(row: Mapping) -> dict:
    """Convert a ``user_conversations`` DB row into a message dict."""
    return {
        "role": row["role"],
        "content": row["content"],
    }


def parse_token_row(row: Mapping) -> dict:
    """Convert a ``user_persona_tokens`` DB row into a usage dict."""
    return {
        "prompt_tokens": row.get("prompt_tokens") or 0,
        "completion_tokens": row.get("completion_tokens") or 0,
        "total_tokens": row.get("total_tokens") or 0,
        "token_limit": row.get("token_limit") or 0,
    }


def parse_memory_row(row: Mapping) -> dict:
    """Convert a ``user_memories`` DB row into a memory dict."""
    embedding = None
    if row.get("embedding"):
        try:
            embedding = json.loads(row["embedding"])
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "content": row["content"],
        "source": row["source"],
        "embedding": embedding,
    }


def parse_cron_task_row(row: Mapping) -> dict:
    """Convert a ``user_cron_tasks`` DB row into a cron-task dict."""
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "cron_expression": row["cron_expression"],
        "prompt": row["prompt"],
        "enabled": row["enabled"],
        "last_run_at": row["last_run_at"],
    }
