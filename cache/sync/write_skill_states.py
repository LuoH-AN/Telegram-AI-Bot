"""Sync skill state rows."""

from __future__ import annotations

from .skill_sql import SKILL_STATE_UPSERT_SQL
from .skill_values import skill_state_values


def sync_skill_states(cur, dirty: dict) -> None:
    for state in dirty["updated_skill_states"]:
        cur.execute(SKILL_STATE_UPSERT_SQL, skill_state_values(state))
