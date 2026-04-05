"""Load settings and personas into cache."""

from __future__ import annotations

from database.loaders import parse_persona_row, parse_settings_row


def load_settings(cur, cache) -> None:
    cur.execute("SELECT * FROM user_settings")
    for row in cur.fetchall():
        cache.set_settings(row["user_id"], parse_settings_row(row))


def load_personas(cur, cache) -> None:
    cur.execute("SELECT user_id, name, system_prompt, current_session_id FROM user_personas")
    for row in cur.fetchall():
        cache.set_persona(row["user_id"], parse_persona_row(row))


def run_settings_personas_load(cur, cache) -> None:
    load_settings(cur, cache)
    load_personas(cur, cache)
    cur.execute(
        """
        SELECT s.user_id
        FROM user_settings s
        LEFT JOIN user_personas p ON s.user_id = p.user_id
        WHERE p.id IS NULL
        """
    )
    for _ in cur.fetchall():
        pass
