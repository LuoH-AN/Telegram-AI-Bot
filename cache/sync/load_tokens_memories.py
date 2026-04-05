"""Load token usage and memories."""

from __future__ import annotations

from database.loaders import parse_memory_row, parse_token_row


def load_tokens(cur, cache) -> None:
    cur.execute("SELECT * FROM user_persona_tokens")
    for row in cur.fetchall():
        cache.set_token_usage(row["user_id"], row["persona_name"], parse_token_row(row))


def load_memories(cur, cache) -> None:
    cur.execute("SELECT id, user_id, content, source, embedding FROM user_memories ORDER BY id")
    memories: dict[int, list] = {}
    for row in cur.fetchall():
        memories.setdefault(row["user_id"], []).append(parse_memory_row(row))
    for user_id, mem_list in memories.items():
        cache.set_memories(user_id, mem_list)


def run_tokens_memories_load(cur, cache) -> None:
    load_tokens(cur, cache)
    load_memories(cur, cache)
