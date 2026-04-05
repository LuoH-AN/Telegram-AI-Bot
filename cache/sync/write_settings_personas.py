"""Sync settings and personas."""

from __future__ import annotations

from .constants import SETTINGS_UPSERT_SQL, settings_upsert_values
from .persona_delete import cascade_delete_persona


def sync_settings(cur, cache, dirty: dict) -> None:
    for user_id in dirty["settings"]:
        cur.execute(SETTINGS_UPSERT_SQL, settings_upsert_values(user_id, cache.get_settings(user_id)))


def sync_deleted_personas(cur, dirty: dict) -> None:
    for user_id, persona_name in dirty["deleted_personas"]:
        cascade_delete_persona(cur, user_id, persona_name)


def sync_personas(cur, cache, dirty: dict) -> None:
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
