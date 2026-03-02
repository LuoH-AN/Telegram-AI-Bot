"""Database schema definitions."""

# SQL statements for creating tables

# Global advisory lock key for schema init/migrations.
# Keep this stable across processes/containers.
SCHEMA_INIT_LOCK_KEY = 913_247_551_004_921

# Global user settings (API config and defaults)
CREATE_USER_SETTINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id BIGINT PRIMARY KEY,
        api_key TEXT,
        base_url TEXT,
        model TEXT,
        temperature REAL,
        reasoning_effort TEXT,
        token_limit BIGINT DEFAULT 0,
        current_persona TEXT DEFAULT 'default',
        enabled_tools TEXT,
        tts_voice TEXT,
        tts_style TEXT,
        tts_endpoint TEXT,
        api_presets TEXT,
        title_model TEXT,
        cron_model TEXT,
        cron_enabled_tools TEXT
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
        token_limit BIGINT DEFAULT 0,
        PRIMARY KEY (user_id, persona_name)
    )
"""

# Migration: add token_limit column to existing user_persona_tokens tables
MIGRATE_PERSONA_TOKENS_ADD_LIMIT = """
    ALTER TABLE user_persona_tokens ADD COLUMN IF NOT EXISTS token_limit BIGINT DEFAULT 0
"""

# Migration: add cron_model column to existing user_settings tables
MIGRATE_SETTINGS_ADD_CRON_MODEL = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS cron_model TEXT
"""

# Migration: add cron_enabled_tools column to existing user_settings tables
MIGRATE_SETTINGS_ADD_CRON_ENABLED_TOOLS = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS cron_enabled_tools TEXT
"""

# Migration: add stream_mode column to existing user_settings tables
MIGRATE_SETTINGS_ADD_STREAM_MODE = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS stream_mode TEXT
"""

# Migration: add global_prompt column to existing user_settings tables
MIGRATE_SETTINGS_ADD_GLOBAL_PROMPT = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS global_prompt TEXT
"""

# Migration: add reasoning_effort column to existing user_settings tables
MIGRATE_SETTINGS_ADD_REASONING_EFFORT = """
    ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS reasoning_effort TEXT
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

# Cron tasks (scheduled AI tasks)
CREATE_USER_CRON_TASKS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_cron_tasks (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        name TEXT NOT NULL,
        cron_expression TEXT NOT NULL,
        prompt TEXT NOT NULL,
        enabled BOOLEAN DEFAULT TRUE,
        last_run_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
    )
"""

CREATE_CRON_TASKS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_cron_tasks_user
    ON user_cron_tasks(user_id)
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
    MIGRATE_PERSONA_TOKENS_ADD_LIMIT,
    MIGRATE_SETTINGS_ADD_CRON_MODEL,
    MIGRATE_SETTINGS_ADD_CRON_ENABLED_TOOLS,
    MIGRATE_SETTINGS_ADD_STREAM_MODE,
    MIGRATE_SETTINGS_ADD_GLOBAL_PROMPT,
    MIGRATE_SETTINGS_ADD_REASONING_EFFORT,
    CREATE_USER_MEMORIES_TABLE,
    CREATE_MEMORIES_INDEX,
    CREATE_USER_LOGS_TABLE,
    CREATE_USER_LOGS_INDEX,
    CREATE_USER_CRON_TASKS_TABLE,
    CREATE_CRON_TASKS_INDEX,
]


def create_tables(connection):
    """Create all required database tables."""
    # Serialize schema DDL across processes to avoid startup deadlocks when
    # Telegram/Discord workers initialize DB concurrently.
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_INIT_LOCK_KEY,))
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
    connection.commit()
