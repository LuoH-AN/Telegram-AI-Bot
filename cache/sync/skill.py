"""Skill cache sync."""

from __future__ import annotations

import json

from database.loaders import parse_skill_row, parse_skill_state_row

DELETE_STATE_SQL = "DELETE FROM user_skill_states WHERE user_id = %s AND skill_name = %s"
DELETE_ARTIFACT_SQL = "DELETE FROM user_skill_artifacts WHERE user_id = %s AND skill_name = %s"
DELETE_SKILL_SQL = "DELETE FROM user_skills WHERE user_id = %s AND name = %s"

UPSERT_SQL = """
INSERT INTO user_skills (user_id, name, display_name, source_type, source_ref, version, enabled, install_status, entrypoint, manifest_json, capabilities_json, persist_mode, last_restore_at, last_persist_at, last_error)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (user_id, name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    source_type = EXCLUDED.source_type,
    source_ref = EXCLUDED.source_ref,
    version = EXCLUDED.version,
    enabled = EXCLUDED.enabled,
    install_status = EXCLUDED.install_status,
    entrypoint = EXCLUDED.entrypoint,
    manifest_json = EXCLUDED.manifest_json,
    capabilities_json = EXCLUDED.capabilities_json,
    persist_mode = EXCLUDED.persist_mode,
    last_restore_at = EXCLUDED.last_restore_at,
    last_persist_at = EXCLUDED.last_persist_at,
    last_error = EXCLUDED.last_error,
    updated_at = CURRENT_TIMESTAMP
RETURNING id
"""

UPDATE_SQL = """
UPDATE user_skills SET
    display_name = %s,
    source_type = %s,
    source_ref = %s,
    version = %s,
    enabled = %s,
    install_status = %s,
    entrypoint = %s,
    manifest_json = %s,
    capabilities_json = %s,
    persist_mode = %s,
    last_restore_at = %s,
    last_persist_at = %s,
    last_error = %s,
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = %s AND name = %s
"""

STATE_SQL = """
INSERT INTO user_skill_states (user_id, skill_name, state_json, state_version, checkpoint_ref, updated_at)
VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
ON CONFLICT (user_id, skill_name) DO UPDATE SET
    state_json = EXCLUDED.state_json,
    state_version = EXCLUDED.state_version,
    checkpoint_ref = EXCLUDED.checkpoint_ref,
    updated_at = CURRENT_TIMESTAMP
"""


def _values(skill: dict) -> tuple:
    return (
        skill["user_id"],
        skill["name"],
        skill.get("display_name", skill["name"]),
        skill.get("source_type", "builtin"),
        skill.get("source_ref", ""),
        skill.get("version", ""),
        bool(skill.get("enabled", True)),
        skill.get("install_status", "installed"),
        skill.get("entrypoint", ""),
        json.dumps(skill.get("manifest", {}), ensure_ascii=False),
        json.dumps(skill.get("capabilities", []), ensure_ascii=False),
        skill.get("persist_mode", "none"),
        skill.get("last_restore_at"),
        skill.get("last_persist_at"),
        skill.get("last_error", ""),
    )


def _update_values(skill: dict) -> tuple:
    return _values(skill)[2:] + (skill["user_id"], skill["name"])


def _state_values(state: dict) -> tuple:
    return (
        state["user_id"],
        state["skill_name"],
        json.dumps(state.get("state", {}), ensure_ascii=False),
        state.get("state_version", ""),
        state.get("checkpoint_ref", ""),
    )


def load(cur, cache) -> None:
    cur.execute("SELECT * FROM user_skills ORDER BY id")
    skills: dict[int, list] = {}
    for row in cur.fetchall():
        skills.setdefault(row["user_id"], []).append(parse_skill_row(row))
    for user_id, items in skills.items():
        cache.set_skills(user_id, items)

    cur.execute("SELECT * FROM user_skill_states ORDER BY id")
    for row in cur.fetchall():
        parsed = parse_skill_state_row(row)
        cache.set_skill_state(
            parsed["user_id"],
            parsed["skill_name"],
            {
                "id": parsed["id"],
                "state": parsed["state"],
                "state_version": parsed["state_version"],
                "checkpoint_ref": parsed["checkpoint_ref"],
                "updated_at": parsed["updated_at"],
            },
        )


def sync_deleted(cur, dirty: dict) -> None:
    for user_id, name in dirty["deleted_skills"]:
        cur.execute(DELETE_STATE_SQL, (user_id, name))
        cur.execute(DELETE_ARTIFACT_SQL, (user_id, name))
        cur.execute(DELETE_SKILL_SQL, (user_id, name))


def sync_new(cur, dirty: dict) -> None:
    for skill in dirty["new_skills"]:
        cur.execute(UPSERT_SQL, _values(skill))
        returned = cur.fetchone()
        if returned and skill.get("id") is None:
            skill["id"] = returned[0]


def sync_updated(cur, dirty: dict) -> None:
    for skill in dirty["updated_skills"]:
        cur.execute(UPDATE_SQL, _update_values(skill))


def sync_states(cur, dirty: dict) -> None:
    for state in dirty["updated_skill_states"]:
        cur.execute(STATE_SQL, _state_values(state))
