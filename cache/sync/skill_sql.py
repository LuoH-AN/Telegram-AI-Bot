"""Skill-related SQL statements."""

SKILL_DELETE_STATE_SQL = "DELETE FROM user_skill_states WHERE user_id = %s AND skill_name = %s"
SKILL_DELETE_ARTIFACT_SQL = "DELETE FROM user_skill_artifacts WHERE user_id = %s AND skill_name = %s"
SKILL_DELETE_SKILL_SQL = "DELETE FROM user_skills WHERE user_id = %s AND name = %s"

SKILL_UPSERT_SQL = """
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

SKILL_UPDATE_SQL = """
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

SKILL_STATE_UPSERT_SQL = """
INSERT INTO user_skill_states (user_id, skill_name, state_json, state_version, checkpoint_ref, updated_at)
VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
ON CONFLICT (user_id, skill_name) DO UPDATE SET
    state_json = EXCLUDED.state_json,
    state_version = EXCLUDED.state_version,
    checkpoint_ref = EXCLUDED.checkpoint_ref,
    updated_at = CURRENT_TIMESTAMP
"""
