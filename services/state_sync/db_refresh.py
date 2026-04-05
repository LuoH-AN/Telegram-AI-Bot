"""Database-to-cache refresh implementation."""

from cache import cache
from database.connection import get_connection, get_dict_cursor
from database.loaders import (
    parse_conversation_row,
    parse_persona_row,
    parse_session_row,
    parse_settings_row,
    parse_skill_row,
    parse_skill_state_row,
    parse_token_row,
)


def refresh_cache_from_db(user_id: int) -> None:
    conn = get_connection()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM user_settings WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row:
                cache.set_settings(user_id, parse_settings_row(row))

            cur.execute("SELECT name, system_prompt, current_session_id FROM user_personas WHERE user_id = %s", (user_id,))
            cache.replace_user_personas(user_id, [parse_persona_row(row) for row in (cur.fetchall() or [])])

            cur.execute(
                "SELECT id, persona_name, title, created_at FROM user_sessions WHERE user_id = %s ORDER BY id",
                (user_id,),
            )
            sessions_by_persona: dict[str, list[dict]] = {}
            session_ids: set[int] = set()
            for row in cur.fetchall() or []:
                session = parse_session_row(row, user_id=user_id)
                sessions_by_persona.setdefault(row["persona_name"], []).append(session)
                session_ids.add(row["id"])
            cache.replace_user_sessions(user_id, sessions_by_persona)

            conversations: dict[int, list[dict]] = {session_id: [] for session_id in session_ids}
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
                    conversations.setdefault(row["session_id"], []).append(parse_conversation_row(row))
            for session_id, messages in conversations.items():
                cache.set_conversation_by_session(session_id, messages)

            cur.execute(
                "SELECT persona_name, prompt_tokens, completion_tokens, total_tokens, token_limit "
                "FROM user_persona_tokens WHERE user_id = %s",
                (user_id,),
            )
            usage_by_persona = {row["persona_name"]: parse_token_row(row) for row in (cur.fetchall() or [])}
            cache.replace_user_token_usage(user_id, usage_by_persona)

            cur.execute("SELECT * FROM user_skills WHERE user_id = %s ORDER BY id", (user_id,))
            cache.set_skills(user_id, [parse_skill_row(row) for row in (cur.fetchall() or [])])

            cur.execute("SELECT * FROM user_skill_states WHERE user_id = %s ORDER BY id", (user_id,))
            for row in cur.fetchall() or []:
                parsed = parse_skill_state_row(row)
                cache.set_skill_state(
                    user_id,
                    parsed["skill_name"],
                    {
                        "id": parsed["id"],
                        "state": parsed["state"],
                        "state_version": parsed["state_version"],
                        "checkpoint_ref": parsed["checkpoint_ref"],
                        "updated_at": parsed["updated_at"],
                    },
                )
    finally:
        conn.close()

