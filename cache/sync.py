"""Database synchronization logic."""

import json
import logging
import threading
import time

from config import DB_SYNC_INTERVAL, DEFAULT_SYSTEM_PROMPT
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
                    settings = {
                        "api_key": row["api_key"] or "",
                        "base_url": row["base_url"] or "https://api.openai.com/v1",
                        "model": row["model"] or "gpt-4o",
                        "temperature": row["temperature"] or 0.7,
                        "token_limit": row.get("token_limit") or 0,
                        "current_persona": row.get("current_persona") or "default",
                        "enabled_tools": row.get("enabled_tools") or "memory,search,fetch,wikipedia",
                    }
                    cache.set_settings(row["user_id"], settings)

                # Migrate token_limit from old table if needed
                cur.execute("SELECT user_id, token_limit FROM user_token_usage WHERE token_limit > 0")
                for row in cur.fetchall():
                    user_id = row["user_id"]
                    if user_id in cache._settings_cache:
                        if cache._settings_cache[user_id].get("token_limit", 0) == 0:
                            cache._settings_cache[user_id]["token_limit"] = row["token_limit"]

                # Load personas
                cur.execute("SELECT user_id, name, system_prompt FROM user_personas")
                for row in cur.fetchall():
                    cache.set_persona(row["user_id"], {
                        "name": row["name"],
                        "system_prompt": row["system_prompt"],
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

                # Load conversations (now with persona_name)
                cur.execute("""
                    SELECT user_id, persona_name, role, content
                    FROM user_conversations
                    ORDER BY id
                """)
                conversations: dict[tuple[int, str], list] = {}
                for row in cur.fetchall():
                    key = (row["user_id"], row["persona_name"] or "default")
                    if key not in conversations:
                        conversations[key] = []
                    conversations[key].append({
                        "role": row["role"],
                        "content": row["content"],
                    })
                for (user_id, persona_name), messages in conversations.items():
                    cache.set_conversation(user_id, persona_name, messages)

                # Load persona token usage
                cur.execute("SELECT * FROM user_persona_tokens")
                for row in cur.fetchall():
                    cache.set_token_usage(row["user_id"], row["persona_name"], {
                        "prompt_tokens": row["prompt_tokens"] or 0,
                        "completion_tokens": row["completion_tokens"] or 0,
                        "total_tokens": row["total_tokens"] or 0,
                    })

                # Migrate old token usage to default persona
                cur.execute("""
                    SELECT u.user_id, u.prompt_tokens, u.completion_tokens, u.total_tokens
                    FROM user_token_usage u
                    LEFT JOIN user_persona_tokens p ON u.user_id = p.user_id AND p.persona_name = 'default'
                    WHERE p.user_id IS NULL AND u.total_tokens > 0
                """)
                for row in cur.fetchall():
                    cache.set_token_usage(row["user_id"], "default", {
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
                    cur.execute("""
                        INSERT INTO user_settings (user_id, api_key, base_url, model, temperature, token_limit, current_persona, enabled_tools)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET
                            api_key = EXCLUDED.api_key,
                            base_url = EXCLUDED.base_url,
                            model = EXCLUDED.model,
                            temperature = EXCLUDED.temperature,
                            token_limit = EXCLUDED.token_limit,
                            current_persona = EXCLUDED.current_persona,
                            enabled_tools = EXCLUDED.enabled_tools
                    """, (
                        user_id, s["api_key"], s["base_url"],
                        s["model"], s["temperature"], s["token_limit"], s["current_persona"],
                        s["enabled_tools"]
                    ))

                # Sync deleted personas
                for user_id, persona_name in dirty["deleted_personas"]:
                    cur.execute(
                        "DELETE FROM user_personas WHERE user_id = %s AND name = %s",
                        (user_id, persona_name)
                    )
                    cur.execute(
                        "DELETE FROM user_conversations WHERE user_id = %s AND persona_name = %s",
                        (user_id, persona_name)
                    )
                    cur.execute(
                        "DELETE FROM user_persona_tokens WHERE user_id = %s AND persona_name = %s",
                        (user_id, persona_name)
                    )

                # Sync personas
                for user_id, persona_name in dirty["personas"]:
                    p = cache.get_persona(user_id, persona_name)
                    if p:
                        cur.execute("""
                            INSERT INTO user_personas (user_id, name, system_prompt)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (user_id, name) DO UPDATE SET
                                system_prompt = EXCLUDED.system_prompt
                        """, (user_id, persona_name, p["system_prompt"]))

                # Sync cleared conversations
                for user_id, persona_name in dirty["cleared_conversations"]:
                    cur.execute(
                        "DELETE FROM user_conversations WHERE user_id = %s AND persona_name = %s",
                        (user_id, persona_name)
                    )

                # Sync new conversation messages
                for user_id, persona_name in dirty["conversations"]:
                    cur.execute(
                        "SELECT COUNT(*) FROM user_conversations WHERE user_id = %s AND persona_name = %s",
                        (user_id, persona_name)
                    )
                    db_count = cur.fetchone()[0]
                    cached = cache.get_conversation(user_id, persona_name)

                    for msg in cached[db_count:]:
                        cur.execute(
                            "INSERT INTO user_conversations (user_id, persona_name, role, content) VALUES (%s, %s, %s, %s)",
                            (user_id, persona_name, msg["role"], msg["content"])
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
