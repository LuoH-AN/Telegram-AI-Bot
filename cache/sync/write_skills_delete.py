"""Sync deleted skills."""

from __future__ import annotations

from .skill_sql import SKILL_DELETE_ARTIFACT_SQL, SKILL_DELETE_SKILL_SQL, SKILL_DELETE_STATE_SQL


def sync_deleted_skills(cur, dirty: dict) -> None:
    for user_id, name in dirty["deleted_skills"]:
        cur.execute(SKILL_DELETE_STATE_SQL, (user_id, name))
        cur.execute(SKILL_DELETE_ARTIFACT_SQL, (user_id, name))
        cur.execute(SKILL_DELETE_SKILL_SQL, (user_id, name))
