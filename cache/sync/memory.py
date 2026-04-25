"""Memory cache sync."""

from __future__ import annotations

import json

from database.loaders import parse_memory_row


def load(cur, cache) -> None:
    cur.execute("SELECT id, user_id, content, source, embedding FROM user_memories ORDER BY id")
    memories: dict[int, list] = {}
    for row in cur.fetchall():
        memories.setdefault(row["user_id"], []).append(parse_memory_row(row))
    for user_id, items in memories.items():
        cache.set_memories(user_id, items)


def sync(cur, dirty: dict) -> None:
    for user_id in dirty["cleared_memories"]:
        cur.execute("DELETE FROM user_memories WHERE user_id = %s", (user_id,))
    for memory_id in dirty["deleted_memory_ids"]:
        cur.execute("DELETE FROM user_memories WHERE id = %s", (memory_id,))
    for memory in dirty["new_memories"]:
        embedding = json.dumps(memory["embedding"]) if memory.get("embedding") else None
        cur.execute(
            "INSERT INTO user_memories (user_id, content, source, embedding) VALUES (%s, %s, %s, %s) RETURNING id",
            (memory["user_id"], memory["content"], memory["source"], embedding),
        )
        memory["id"] = cur.fetchone()[0]
