"""Persona cascade delete helpers."""


def cascade_delete_persona(cur, user_id: int, persona_name: str) -> None:
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
