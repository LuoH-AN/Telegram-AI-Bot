"""Cross-process state refresh from database.

This keeps Discord/Telegram/Web consistent when they run in separate processes.
"""

import json
import logging
import os
import threading
import time

from cache import cache, sync_to_database
from config import (
    DEFAULT_TTS_VOICE,
    DEFAULT_TTS_STYLE,
    DEFAULT_TTS_ENDPOINT,
    DEFAULT_ENABLED_TOOLS,
    DEFAULT_REASONING_EFFORT,
)
from database.connection import get_connection, get_dict_cursor
from utils.tooling import normalize_tools_csv, resolve_cron_tools_csv

logger = logging.getLogger(__name__)

STATE_REFRESH_INTERVAL = max(0.5, float(os.getenv("STATE_REFRESH_INTERVAL", "2.0")))

_refresh_lock = threading.Lock()
_last_refresh_ts: dict[int, float] = {}


def _has_local_dirty_state(user_id: int) -> bool:
    if user_id in cache._dirty_settings:
        return True
    if any(uid == user_id for uid, _ in cache._dirty_personas):
        return True
    if any(uid == user_id for uid, _ in cache._dirty_tokens):
        return True
    if any(uid == user_id for uid, _ in cache._deleted_personas):
        return True
    if cache._new_sessions or cache._dirty_session_titles or cache._deleted_sessions:
        return True
    if cache._dirty_conversations or cache._cleared_conversations:
        return True
    return False


def _should_refresh(user_id: int, force: bool) -> bool:
    if force:
        return True
    now = time.monotonic()
    with _refresh_lock:
        last = _last_refresh_ts.get(user_id, 0.0)
        if now - last < STATE_REFRESH_INTERVAL:
            return False
        _last_refresh_ts[user_id] = now
    return True


def refresh_user_state_from_db(user_id: int, *, force: bool = False) -> None:
    """Refresh one user's state from DB with throttling."""
    if not _should_refresh(user_id, force):
        return

    if _has_local_dirty_state(user_id):
        try:
            sync_to_database()
        except Exception:
            logger.exception("Failed to flush dirty state before refresh (user=%s)", user_id)
            return

    try:
        conn = get_connection()
        try:
            with get_dict_cursor(conn) as cur:
                cur.execute("SELECT * FROM user_settings WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    api_presets = {}
                    if row.get("api_presets"):
                        try:
                            api_presets = json.loads(row["api_presets"])
                        except (json.JSONDecodeError, TypeError):
                            api_presets = {}

                    enabled_tools = normalize_tools_csv(row.get("enabled_tools") or DEFAULT_ENABLED_TOOLS)
                    cron_tools = normalize_tools_csv(
                        row.get("cron_enabled_tools") or resolve_cron_tools_csv({"enabled_tools": enabled_tools})
                    )
                    settings = {
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
                    cache.set_settings(user_id, settings)

                cur.execute(
                    """
                    SELECT name, system_prompt, current_session_id
                    FROM user_personas
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                persona_rows = cur.fetchall() or []
                personas = []
                for persona in persona_rows:
                    personas.append({
                        "name": persona["name"],
                        "system_prompt": persona["system_prompt"],
                        "current_session_id": persona.get("current_session_id"),
                    })
                cache.replace_user_personas(user_id, personas)

                cur.execute(
                    """
                    SELECT id, persona_name, title, created_at
                    FROM user_sessions
                    WHERE user_id = %s
                    ORDER BY id
                    """,
                    (user_id,),
                )
                session_rows = cur.fetchall() or []
                sessions_by_persona: dict[str, list[dict]] = {}
                session_ids: set[int] = set()
                for row in session_rows:
                    session = {
                        "id": row["id"],
                        "user_id": user_id,
                        "persona_name": row["persona_name"],
                        "title": row.get("title"),
                        "created_at": str(row["created_at"]) if row.get("created_at") else None,
                    }
                    sessions_by_persona.setdefault(row["persona_name"], []).append(session)
                    session_ids.add(row["id"])
                cache.replace_user_sessions(user_id, sessions_by_persona)

                conversations_by_session: dict[int, list[dict]] = {session_id: [] for session_id in session_ids}
                if session_ids:
                    cur.execute(
                        """
                        SELECT c.session_id, c.role, c.content
                        FROM user_conversations c
                        JOIN user_sessions s ON s.id = c.session_id
                        WHERE s.user_id = %s AND c.session_id IS NOT NULL
                        ORDER BY c.id
                        """,
                        (user_id,),
                    )
                    for row in cur.fetchall() or []:
                        conversations_by_session.setdefault(row["session_id"], []).append({
                            "role": row["role"],
                            "content": row["content"],
                        })
                for session_id, messages in conversations_by_session.items():
                    cache.set_conversation_by_session(session_id, messages)

                cur.execute(
                    """
                    SELECT persona_name, prompt_tokens, completion_tokens, total_tokens, token_limit
                    FROM user_persona_tokens
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                token_rows = cur.fetchall() or []
                usage_by_persona: dict[str, dict] = {}
                for token_row in token_rows:
                    usage_by_persona[token_row["persona_name"]] = {
                        "prompt_tokens": token_row.get("prompt_tokens") or 0,
                        "completion_tokens": token_row.get("completion_tokens") or 0,
                        "total_tokens": token_row.get("total_tokens") or 0,
                        "token_limit": token_row.get("token_limit") or 0,
                    }
                cache.replace_user_token_usage(user_id, usage_by_persona)
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to refresh user state from DB (user=%s)", user_id)
