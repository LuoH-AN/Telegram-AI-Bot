"""Database schema definitions."""

# SQL statements for creating tables

# Global user settings (API config and defaults)
CREATE_USER_SETTINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id BIGINT PRIMARY KEY,
        api_key TEXT,
        base_url TEXT,
        model TEXT,
        temperature REAL,
        token_limit BIGINT DEFAULT 0,
        current_persona TEXT DEFAULT 'default',
        enabled_tools TEXT,
        tts_voice TEXT,
        tts_style TEXT,
        tts_endpoint TEXT,
        api_presets TEXT,
        title_model TEXT
    )
"""

# Persona definitions
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

# Sessions table (multiple sessions per persona)
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

# Conversations linked to session_id
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

# Token usage per persona
CREATE_USER_PERSONA_TOKENS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_persona_tokens (
        user_id BIGINT NOT NULL,
        persona_name TEXT NOT NULL,
        prompt_tokens BIGINT DEFAULT 0,
        completion_tokens BIGINT DEFAULT 0,
        total_tokens BIGINT DEFAULT 0,
        PRIMARY KEY (user_id, persona_name)
    )
"""

# Memories (shared across personas)
CREATE_USER_MEMORIES_TABLE = """
    CREATE TABLE IF NOT EXISTS user_memories (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'user',
        embedding TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_MEMORIES_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_memories_user_id
    ON user_memories(user_id)
"""

# User logs (AI interactions and errors)
CREATE_USER_LOGS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_logs (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        log_type TEXT NOT NULL,
        model TEXT,
        prompt_tokens INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        tool_calls TEXT,
        latency_ms INTEGER,
        persona_name TEXT,
        error_message TEXT,
        error_context TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_USER_LOGS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_user_logs_user_created
    ON user_logs(user_id, created_at DESC)
"""

# All schema creation statements in order
SCHEMA_STATEMENTS = [
    CREATE_USER_SETTINGS_TABLE,
    CREATE_USER_PERSONAS_TABLE,
    CREATE_PERSONAS_INDEX,
    CREATE_USER_SESSIONS_TABLE,
    CREATE_SESSIONS_INDEX,
    CREATE_USER_CONVERSATIONS_TABLE,
    CREATE_CONVERSATIONS_INDEX,
    CREATE_CONVERSATIONS_SESSION_INDEX,
    CREATE_USER_PERSONA_TOKENS_TABLE,
    CREATE_USER_MEMORIES_TABLE,
    CREATE_MEMORIES_INDEX,
    CREATE_USER_LOGS_TABLE,
    CREATE_USER_LOGS_INDEX,
]


def create_tables(connection):
    """Create all required database tables."""
    with connection.cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
    connection.commit()
