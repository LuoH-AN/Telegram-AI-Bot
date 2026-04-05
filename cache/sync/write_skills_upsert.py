"""Sync created/updated skill rows."""

from __future__ import annotations

from .skill_sql import SKILL_UPDATE_SQL, SKILL_UPSERT_SQL
from .skill_values import skill_update_values, skill_values


def sync_new_skills(cur, dirty: dict) -> None:
    for skill in dirty["new_skills"]:
        cur.execute(SKILL_UPSERT_SQL, skill_values(skill))
        returned = cur.fetchone()
        if returned and skill.get("id") is None:
            skill["id"] = returned[0]


def sync_updated_skills(cur, dirty: dict) -> None:
    for skill in dirty["updated_skills"]:
        cur.execute(SKILL_UPDATE_SQL, skill_update_values(skill))
