"""Schema SQL for core user/persona/session/conversation tables."""

SCHEMA_INIT_LOCK_KEY = 913_247_551_004_921

CREATE_USER_SETTINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id BIGINT PRIMARY KEY,
        api_key TEXT,
        base_url TEXT,
        model TEXT,
        temperature REAL,
        reasoning_effort TEXT,
        show_thinking BOOLEAN DEFAULT FALSE,
        token_limit BIGINT DEFAULT 0,
        current_persona TEXT DEFAULT 'default',
        tts_voice TEXT,
        tts_style TEXT,
        tts_endpoint TEXT,
        api_presets TEXT,
        title_model TEXT,
        cron_model TEXT,
        stream_mode TEXT,
        global_prompt TEXT
    )
"""

CREATE_USER_PERSONAS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_personas (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        name TEXT NOT NULL,
        system_prompt TEXT NOT NULL,
        current_session_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
    )
"""

CREATE_PERSONAS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_personas_user_id
    ON user_personas(user_id)
"""

CREATE_USER_SESSIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        persona_name TEXT NOT NULL DEFAULT 'default',
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_SESSIONS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_sessions_user_persona
    ON user_sessions(user_id, persona_name)
"""

CREATE_USER_CONVERSATIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_conversations (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        persona_name TEXT NOT NULL DEFAULT 'default',
        session_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_CONVERSATIONS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_conversations_user_persona
    ON user_conversations(user_id, persona_name)
"""

CREATE_CONVERSATIONS_SESSION_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_conversations_session_id
    ON user_conversations(session_id)
"""
