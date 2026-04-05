"""Sync token usage and memories."""

from __future__ import annotations

import json


def sync_tokens(cur, cache, dirty: dict) -> None:
    for user_id, persona_name in dirty["tokens"]:
        token = cache.get_token_usage(user_id, persona_name)
        cur.execute(
            """
            INSERT INTO user_persona_tokens (user_id, persona_name, prompt_tokens, completion_tokens, total_tokens, token_limit)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, persona_name) DO UPDATE SET
                prompt_tokens = EXCLUDED.prompt_tokens,
                completion_tokens = EXCLUDED.completion_tokens,
                total_tokens = EXCLUDED.total_tokens,
                token_limit = EXCLUDED.token_limit
            """,
            (
                user_id,
                persona_name,
                token["prompt_tokens"],
                token["completion_tokens"],
                token["total_tokens"],
                token.get("token_limit", 0),
            ),
        )


def sync_memories(cur, dirty: dict) -> None:
    for user_id in dirty["cleared_memories"]:
        cur.execute("DELETE FROM user_memories WHERE user_id = %s", (user_id,))
    for memory_id in dirty["deleted_memory_ids"]:
        cur.execute("DELETE FROM user_memories WHERE id = %s", (memory_id,))
    for mem in dirty["new_memories"]:
        embedding = json.dumps(mem["embedding"]) if mem.get("embedding") else None
        cur.execute(
            "INSERT INTO user_memories (user_id, content, source, embedding) VALUES (%s, %s, %s, %s) RETURNING id",
            (mem["user_id"], mem["content"], mem["source"], embedding),
        )
        mem["id"] = cur.fetchone()[0]
