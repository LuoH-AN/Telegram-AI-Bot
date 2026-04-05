"""Schema SQL for token tables and settings migrations."""

CREATE_USER_PERSONA_TOKENS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_persona_tokens (
        user_id BIGINT NOT NULL,
        persona_name TEXT NOT NULL,
        prompt_tokens BIGINT DEFAULT 0,
        completion_tokens BIGINT DEFAULT 0,
        total_tokens BIGINT DEFAULT 0,
        token_limit BIGINT DEFAULT 0,
        PRIMARY KEY (user_id, persona_name)
    )
"""

MIGRATE_PERSONA_TOKENS_ADD_LIMIT = """
    ALTER TABLE user_persona_tokens ADD COLUMN IF NOT EXISTS token_limit BIGINT DEFAULT 0
"""

MIGRATE_SETTINGS_ADD_CRON_MODEL = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS cron_model TEXT
"""

MIGRATE_SETTINGS_ADD_STREAM_MODE = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS stream_mode TEXT
"""

MIGRATE_SETTINGS_ADD_GLOBAL_PROMPT = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS global_prompt TEXT
"""

MIGRATE_SETTINGS_ADD_REASONING_EFFORT = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS reasoning_effort TEXT
"""

MIGRATE_SETTINGS_ADD_SHOW_THINKING = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS show_thinking BOOLEAN DEFAULT FALSE
"""
