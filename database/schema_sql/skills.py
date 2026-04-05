"""Schema SQL for skills and WeChat runtime state."""

CREATE_USER_SKILLS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_skills (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        name TEXT NOT NULL,
        display_name TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        version TEXT DEFAULT '',
        enabled BOOLEAN DEFAULT TRUE,
        install_status TEXT NOT NULL DEFAULT 'installed',
        entrypoint TEXT DEFAULT '',
        manifest_json TEXT DEFAULT '{}',
        capabilities_json TEXT DEFAULT '[]',
        persist_mode TEXT NOT NULL DEFAULT 'none',
        last_restore_at TIMESTAMP,
        last_persist_at TIMESTAMP,
        last_error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
    )
"""

CREATE_USER_SKILLS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_user_skills_user
    ON user_skills(user_id)
"""

CREATE_USER_SKILL_STATES_TABLE = """
    CREATE TABLE IF NOT EXISTS user_skill_states (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        skill_name TEXT NOT NULL,
        state_json TEXT DEFAULT '{}',
        state_version TEXT DEFAULT '',
        checkpoint_ref TEXT DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, skill_name)
    )
"""

CREATE_USER_SKILL_ARTIFACTS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_skill_artifacts (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        skill_name TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        storage_backend TEXT NOT NULL DEFAULT 'hf_dataset',
        storage_path TEXT NOT NULL,
        git_revision TEXT DEFAULT '',
        meta_json TEXT DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_WECHAT_RUNTIME_STATE_TABLE = """
    CREATE TABLE IF NOT EXISTS wechat_runtime_state (
        account_key TEXT PRIMARY KEY,
        token TEXT DEFAULT '',
        user_id TEXT DEFAULT '',
        base_url TEXT DEFAULT '',
        get_updates_buf TEXT DEFAULT '',
        peer_map TEXT DEFAULT '{}',
        context_tokens TEXT DEFAULT '{}',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""
