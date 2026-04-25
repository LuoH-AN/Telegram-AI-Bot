"""Persona cache sync."""

from __future__ import annotations

from database.loaders import parse_persona_row


def load(cur, cache) -> None:
    cur.execute("SELECT user_id, name, system_prompt, current_session_id FROM user_personas")
    for row in cur.fetchall():
        cache.set_persona(row["user_id"], parse_persona_row(row))


def purge(cur, user_id: int, persona_name: str) -> None:
    cur.execute(
        """
        DELETE FROM user_conversations WHERE session_id IN (
            SELECT id FROM user_sessions WHERE user_id = %s AND persona_name = %s
        )
        """,
        (user_id, persona_name),
    )
    cur.execute("DELETE FROM user_sessions WHERE user_id = %s AND persona_name = %s", (user_id, persona_name))
    cur.execute("DELETE FROM user_personas WHERE user_id = %s AND name = %s", (user_id, persona_name))
    cur.execute("DELETE FROM user_persona_tokens WHERE user_id = %s AND persona_name = %s", (user_id, persona_name))


def sync_deleted(cur, dirty: dict) -> None:
    for user_id, persona_name in dirty["deleted_personas"]:
        purge(cur, user_id, persona_name)


def sync(cur, cache, dirty: dict) -> None:
    for user_id, persona_name in dirty["personas"]:
        persona = cache.get_persona(user_id, persona_name)
        if not persona:
            continue
        cur.execute(
            """
            INSERT INTO user_personas (user_id, name, system_prompt, current_session_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, name) DO UPDATE SET
                system_prompt = EXCLUDED.system_prompt,
                current_session_id = EXCLUDED.current_session_id
            """,
            (user_id, persona_name, persona["system_prompt"], persona.get("current_session_id")),
        )
