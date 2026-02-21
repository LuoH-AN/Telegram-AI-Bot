"""Database synchronization logic."""

import json
import logging
import threading
import time

from config import (
    DB_SYNC_INTERVAL,
    DEFAULT_TTS_VOICE,
    DEFAULT_TTS_STYLE,
    DEFAULT_TTS_ENDPOINT,
    DEFAULT_ENABLED_TOOLS,
)
from database import get_connection, get_dict_cursor
from database.schema import create_tables
from .manager import cache

logger = logging.getLogger(__name__)


def load_from_database() -> None:
    """Load all data from database into cache."""
    try:
        with get_connection() as conn:
            with get_dict_cursor(conn) as cur:
                # Load settings
                cur.execute("SELECT * FROM user_settings")
                for row in cur.fetchall():
                    # Parse api_presets from JSON
                    api_presets = {}
                    if row.get("api_presets"):
                        try:
                            api_presets = json.loads(row["api_presets"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    settings = {
                        "api_key": row["api_key"] or "",
                        "base_url": row["base_url"] or "https://api.openai.com/v1",
                        "model": row["model"] or "gpt-4o",
                        "temperature": row["temperature"] or 0.7,
                        "token_limit": row.get("token_limit") or 0,
                        "current_persona": row.get("current_persona") or "default",
                        "enabled_tools": row.get("enabled_tools") or DEFAULT_ENABLED_TOOLS,
                        "tts_voice": row.get("tts_voice") or DEFAULT_TTS_VOICE,
                        "tts_style": row.get("tts_style") or DEFAULT_TTS_STYLE,
                        "tts_endpoint": row.get("tts_endpoint") or DEFAULT_TTS_ENDPOINT,
                        "api_presets": api_presets,
                        "title_model": row.get("title_model") or "",
                    }
                    cache.set_settings(row["user_id"], settings)

                # Load personas
                cur.execute("SELECT user_id, name, system_prompt, current_session_id FROM user_personas")
                for row in cur.fetchall():
                    cache.set_persona(row["user_id"], {
                        "name": row["name"],
                        "system_prompt": row["system_prompt"],
                        "current_session_id": row.get("current_session_id"),
                    })

                # Ensure users with settings have at least a default persona
                cur.execute("""
                    SELECT s.user_id
                    FROM user_settings s
                    LEFT JOIN user_personas p ON s.user_id = p.user_id
                    WHERE p.id IS NULL
                """)
                for row in cur.fetchall():
                    # User has no personas, will be created with default on first access
                    pass

                # Load sessions
                max_session_id = 0
                cur.execute("SELECT id, user_id, persona_name, title, created_at FROM user_sessions ORDER BY id")
                sessions_by_key: dict[tuple[int, str], list[dict]] = {}
                for row in cur.fetchall():
                    key = (row["user_id"], row["persona_name"])
                    if key not in sessions_by_key:
                        sessions_by_key[key] = []
                    session = {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "persona_name": row["persona_name"],
                        "title": row["title"],
                        "created_at": str(row["created_at"]) if row["created_at"] else None,
                    }
                    sessions_by_key[key].append(session)
                    if row["id"] > max_session_id:
                        max_session_id = row["id"]
                for key, sessions in sessions_by_key.items():
                    cache.set_sessions(key[0], key[1], sessions)

                # Initialize session ID counter
                cache._session_id_counter = max_session_id

                # Load conversations grouped by session_id
                cur.execute("""
                    SELECT session_id, role, content
                    FROM user_conversations
                    WHERE session_id IS NOT NULL
                    ORDER BY id
                """)
                conversations_by_session: dict[int, list] = {}

                for row in cur.fetchall():
                    sid = row["session_id"]
                    if sid not in conversations_by_session:
                        conversations_by_session[sid] = []
                    conversations_by_session[sid].append({
                        "role": row["role"],
                        "content": row["content"],
                    })

                for session_id, messages in conversations_by_session.items():
                    cache.set_conversation_by_session(session_id, messages)

                # Load persona token usage
                cur.execute("SELECT * FROM user_persona_tokens")
                for row in cur.fetchall():
                    cache.set_token_usage(row["user_id"], row["persona_name"], {
                        "prompt_tokens": row["prompt_tokens"] or 0,
                        "completion_tokens": row["completion_tokens"] or 0,
                        "total_tokens": row["total_tokens"] or 0,
                    })

                # Load memories
                cur.execute("SELECT id, user_id, content, source, embedding FROM user_memories ORDER BY id")
                memories: dict[int, list] = {}
                for row in cur.fetchall():
                    uid = row["user_id"]
                    if uid not in memories:
                        memories[uid] = []
                    # Parse embedding from JSON string
                    embedding = None
                    if row.get("embedding"):
                        try:
                            embedding = json.loads(row["embedding"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    memories[uid].append({
                        "id": row["id"],
                        "user_id": uid,
                        "content": row["content"],
                        "source": row["source"],
                        "embedding": embedding,
                    })
                for uid, mem_list in memories.items():
                    cache.set_memories(uid, mem_list)

    except Exception as e:
        logger.exception("Failed to load from database")


def sync_to_database() -> None:
    """Sync all dirty data to database."""
    dirty = cache.get_and_clear_dirty()

    if not any(dirty.values()):
        return

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Sync settings
                for user_id in dirty["settings"]:
                    s = cache.get_settings(user_id)
                    api_presets_json = json.dumps(s.get("api_presets", {}), ensure_ascii=False) if s.get("api_presets") else None
                    cur.execute("""
                        INSERT INTO user_settings (
                            user_id, api_key, base_url, model, temperature,
                            token_limit, current_persona, enabled_tools,
                            tts_voice, tts_style, tts_endpoint, api_presets, title_model
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET
                            api_key = EXCLUDED.api_key,
                            base_url = EXCLUDED.base_url,
                            model = EXCLUDED.model,
                            temperature = EXCLUDED.temperature,
                            token_limit = EXCLUDED.token_limit,
                            current_persona = EXCLUDED.current_persona,
                            enabled_tools = EXCLUDED.enabled_tools,
                            tts_voice = EXCLUDED.tts_voice,
                            tts_style = EXCLUDED.tts_style,
                            tts_endpoint = EXCLUDED.tts_endpoint,
                            api_presets = EXCLUDED.api_presets,
                            title_model = EXCLUDED.title_model
                    """, (
                        user_id, s["api_key"], s["base_url"],
                        s["model"], s["temperature"], s["token_limit"], s["current_persona"],
                        s["enabled_tools"], s.get("tts_voice", DEFAULT_TTS_VOICE),
                        s.get("tts_style", DEFAULT_TTS_STYLE),
                        s.get("tts_endpoint", DEFAULT_TTS_ENDPOINT),
                        api_presets_json,
                        s.get("title_model", ""),
                    ))

                # Sync deleted personas (cascade: delete sessions + conversations + tokens)
                for user_id, persona_name in dirty["deleted_personas"]:
                    # Delete conversations belonging to sessions of this persona
                    cur.execute("""
                        DELETE FROM user_conversations WHERE session_id IN (
                            SELECT id FROM user_sessions WHERE user_id = %s AND persona_name = %s
                        )
                    """, (user_id, persona_name))
                    cur.execute(
                        "DELETE FROM user_sessions WHERE user_id = %s AND persona_name = %s",
                        (user_id, persona_name)
                    )
                    cur.execute(
                        "DELETE FROM user_personas WHERE user_id = %s AND name = %s",
                        (user_id, persona_name)
                    )
                    cur.execute(
                        "DELETE FROM user_persona_tokens WHERE user_id = %s AND persona_name = %s",
                        (user_id, persona_name)
                    )

                # Sync personas (with current_session_id)
                for user_id, persona_name in dirty["personas"]:
                    p = cache.get_persona(user_id, persona_name)
                    if p:
                        cur.execute("""
                            INSERT INTO user_personas (user_id, name, system_prompt, current_session_id)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (user_id, name) DO UPDATE SET
                                system_prompt = EXCLUDED.system_prompt,
                                current_session_id = EXCLUDED.current_session_id
                        """, (user_id, persona_name, p["system_prompt"], p.get("current_session_id")))

                # Sync new sessions
                for session in dirty["new_sessions"]:
                    cur.execute(
                        "INSERT INTO user_sessions (user_id, persona_name, title) VALUES (%s, %s, %s) RETURNING id",
                        (session["user_id"], session["persona_name"], session["title"])
                    )
                    db_id = cur.fetchone()[0]
                    # Update the session dict with the real DB id
                    old_id = session["id"]
                    session["id"] = db_id

                    # Update cache references: conversations, current_session_id, sessions list
                    if old_id in cache._conversations_cache:
                        cache._conversations_cache[db_id] = cache._conversations_cache.pop(old_id)
                    # Update dirty conversations references
                    if old_id in dirty["conversations"]:
                        dirty["conversations"].discard(old_id)
                        dirty["conversations"].add(db_id)
                    if old_id in dirty["cleared_conversations"]:
                        dirty["cleared_conversations"].discard(old_id)
                        dirty["cleared_conversations"].add(db_id)
                    # Update deleted sessions references
                    if old_id in dirty["deleted_sessions"]:
                        dirty["deleted_sessions"].discard(old_id)
                        dirty["deleted_sessions"].add(db_id)
                    # Update dirty session title references
                    if old_id in dirty["dirty_session_titles"]:
                        dirty["dirty_session_titles"][db_id] = dirty["dirty_session_titles"].pop(old_id)

                    # Update persona's current_session_id if it points to the old id
                    persona = cache.get_persona(session["user_id"], session["persona_name"])
                    if persona and persona.get("current_session_id") == old_id:
                        persona["current_session_id"] = db_id

                    # Update the session in the sessions cache list
                    key = (session["user_id"], session["persona_name"])
                    sessions_list = cache._sessions_cache.get(key, [])
                    for s in sessions_list:
                        if s["id"] == old_id:
                            s["id"] = db_id
                            break

                    # Update session ID counter if needed
                    if db_id > cache._session_id_counter:
                        cache._session_id_counter = db_id

                # Sync session title updates
                for session_id, title in dirty["dirty_session_titles"].items():
                    cur.execute(
                        "UPDATE user_sessions SET title = %s WHERE id = %s",
                        (title, session_id)
                    )

                # Sync deleted sessions (cascade delete conversations)
                for session_id in dirty["deleted_sessions"]:
                    cur.execute(
                        "DELETE FROM user_conversations WHERE session_id = %s",
                        (session_id,)
                    )
                    cur.execute(
                        "DELETE FROM user_sessions WHERE id = %s",
                        (session_id,)
                    )

                # Sync cleared conversations (by session_id)
                for session_id in dirty["cleared_conversations"]:
                    cur.execute(
                        "DELETE FROM user_conversations WHERE session_id = %s",
                        (session_id,)
                    )

                # Sync new conversation messages (by session_id)
                for session_id in dirty["conversations"]:
                    # Get session info to fill user_id and persona_name
                    session = cache.get_session_by_id(session_id)
                    if not session:
                        continue

                    cur.execute(
                        "SELECT COUNT(*) FROM user_conversations WHERE session_id = %s",
                        (session_id,)
                    )
                    db_count = cur.fetchone()[0]
                    cached = cache.get_conversation_by_session(session_id)

                    for msg in cached[db_count:]:
                        cur.execute(
                            "INSERT INTO user_conversations (user_id, persona_name, session_id, role, content) VALUES (%s, %s, %s, %s, %s)",
                            (session["user_id"], session["persona_name"], session_id, msg["role"], msg["content"])
                        )

                # Sync token usage
                for user_id, persona_name in dirty["tokens"]:
                    t = cache.get_token_usage(user_id, persona_name)
                    cur.execute("""
                        INSERT INTO user_persona_tokens (user_id, persona_name, prompt_tokens, completion_tokens, total_tokens)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, persona_name) DO UPDATE SET
                            prompt_tokens = EXCLUDED.prompt_tokens,
                            completion_tokens = EXCLUDED.completion_tokens,
                            total_tokens = EXCLUDED.total_tokens
                    """, (
                        user_id, persona_name, t["prompt_tokens"], t["completion_tokens"], t["total_tokens"],
                    ))

                # Sync cleared memories
                for user_id in dirty["cleared_memories"]:
                    cur.execute("DELETE FROM user_memories WHERE user_id = %s", (user_id,))

                # Sync deleted memories
                for memory_id in dirty["deleted_memory_ids"]:
                    cur.execute("DELETE FROM user_memories WHERE id = %s", (memory_id,))

                # Sync new memories
                for mem in dirty["new_memories"]:
                    embedding_json = (
                        json.dumps(mem["embedding"]) if mem.get("embedding") else None
                    )
                    cur.execute(
                        "INSERT INTO user_memories (user_id, content, source, embedding) VALUES (%s, %s, %s, %s) RETURNING id",
                        (mem["user_id"], mem["content"], mem["source"], embedding_json)
                    )
                    mem["id"] = cur.fetchone()[0]

            conn.commit()

            # Log sync summary
            parts = []
            if dirty["settings"]:
                parts.append(f"{len(dirty['settings'])} settings")
            if dirty["personas"]:
                parts.append(f"{len(dirty['personas'])} personas")
            if dirty["deleted_personas"]:
                parts.append(f"{len(dirty['deleted_personas'])} deleted personas")
            if dirty["new_sessions"]:
                parts.append(f"{len(dirty['new_sessions'])} new sessions")
            if dirty["dirty_session_titles"]:
                parts.append(f"{len(dirty['dirty_session_titles'])} session titles")
            if dirty["deleted_sessions"]:
                parts.append(f"{len(dirty['deleted_sessions'])} deleted sessions")
            if dirty["conversations"]:
                parts.append(f"{len(dirty['conversations'])} conversations")
            if dirty["cleared_conversations"]:
                parts.append(f"{len(dirty['cleared_conversations'])} cleared convs")
            if dirty["tokens"]:
                parts.append(f"{len(dirty['tokens'])} token records")
            if dirty["new_memories"]:
                parts.append(f"{len(dirty['new_memories'])} new memories")
            if dirty["deleted_memory_ids"]:
                parts.append(f"{len(dirty['deleted_memory_ids'])} deleted memories")
            if dirty["cleared_memories"]:
                parts.append(f"{len(dirty['cleared_memories'])} cleared memories")
            if parts:
                logger.info(f"Synced to DB: {', '.join(parts)}")

    except Exception as e:
        cache.restore_dirty(dirty)
        logger.exception("Failed to sync to database")


def _sync_loop() -> None:
    """Background loop that periodically syncs dirty data to database."""
    while True:
        time.sleep(DB_SYNC_INTERVAL)
        try:
            sync_to_database()
        except Exception as e:
            logger.exception("Sync error")


def init_database() -> None:
    """Initialize database tables and load cache."""
    with get_connection() as conn:
        create_tables(conn)

    load_from_database()

    # Start background sync thread
    sync_thread = threading.Thread(target=_sync_loop, daemon=True)
    sync_thread.start()

    logger.info("Database initialized, cache loaded")
