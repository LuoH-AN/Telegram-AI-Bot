"""Token cache sync."""

from __future__ import annotations

from database.loaders import parse_token_row


def load(cur, cache) -> None:
    cur.execute("SELECT * FROM user_persona_tokens")
    for row in cur.fetchall():
        cache.set_token_usage(row["user_id"], row["persona_name"], parse_token_row(row))


def sync(cur, cache, dirty: dict) -> None:
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
