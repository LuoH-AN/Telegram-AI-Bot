"""Database schema definitions."""

# SQL statements for creating tables

# Global user settings (API config, current persona)
CREATE_USER_SETTINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id BIGINT PRIMARY KEY,
        api_key TEXT,
        base_url TEXT,
        model TEXT,
        temperature REAL,
        token_limit BIGINT DEFAULT 0,
        current_persona TEXT DEFAULT 'default'
    )
"""

# Add token_limit and current_persona columns if they don't exist (migration)
MIGRATE_USER_SETTINGS = """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='user_settings' AND column_name='token_limit') THEN
            ALTER TABLE user_settings ADD COLUMN token_limit BIGINT DEFAULT 0;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='user_settings' AND column_name='current_persona') THEN
            ALTER TABLE user_settings ADD COLUMN current_persona TEXT DEFAULT 'default';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='user_settings' AND column_name='enabled_tools') THEN
            ALTER TABLE user_settings ADD COLUMN enabled_tools TEXT;
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='user_settings' AND column_name='system_prompt') THEN
            ALTER TABLE user_settings DROP COLUMN IF EXISTS system_prompt;
        END IF;
    END $$;
"""

# Persona definitions
CREATE_USER_PERSONAS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_personas (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        name TEXT NOT NULL,
        system_prompt TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
    )
"""

CREATE_PERSONAS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_personas_user_id
    ON user_personas(user_id)
"""

# Conversations now linked to persona
CREATE_USER_CONVERSATIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_conversations (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        persona_name TEXT NOT NULL DEFAULT 'default',
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

# Add persona_name column if it doesn't exist (migration)
MIGRATE_USER_CONVERSATIONS = """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='user_conversations' AND column_name='persona_name') THEN
            ALTER TABLE user_conversations ADD COLUMN persona_name TEXT NOT NULL DEFAULT 'default';
        END IF;
    END $$;
"""

CREATE_CONVERSATIONS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_conversations_user_persona
    ON user_conversations(user_id, persona_name)
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

# Keep old token table for migration, will migrate data from it
CREATE_USER_TOKEN_USAGE_TABLE = """
    CREATE TABLE IF NOT EXISTS user_token_usage (
        user_id BIGINT PRIMARY KEY,
        prompt_tokens BIGINT DEFAULT 0,
        completion_tokens BIGINT DEFAULT 0,
        total_tokens BIGINT DEFAULT 0,
        token_limit BIGINT DEFAULT 0
    )
"""

# Memories (shared across personas)
CREATE_USER_MEMORIES_TABLE = """
    CREATE TABLE IF NOT EXISTS user_memories (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_MEMORIES_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_memories_user_id
    ON user_memories(user_id)
"""

# Add embedding column to user_memories (migration)
MIGRATE_USER_MEMORIES_EMBEDDING = """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='user_memories' AND column_name='embedding') THEN
            ALTER TABLE user_memories ADD COLUMN embedding TEXT;
        END IF;
    END $$;
"""

# All schema creation statements in order
SCHEMA_STATEMENTS = [
    CREATE_USER_SETTINGS_TABLE,
    MIGRATE_USER_SETTINGS,
    CREATE_USER_PERSONAS_TABLE,
    CREATE_PERSONAS_INDEX,
    CREATE_USER_CONVERSATIONS_TABLE,
    MIGRATE_USER_CONVERSATIONS,
    CREATE_CONVERSATIONS_INDEX,
    CREATE_USER_PERSONA_TOKENS_TABLE,
    CREATE_USER_TOKEN_USAGE_TABLE,
    CREATE_USER_MEMORIES_TABLE,
    CREATE_MEMORIES_INDEX,
    MIGRATE_USER_MEMORIES_EMBEDDING,
]


def create_tables(connection):
    """Create all required database tables."""
    with connection.cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
    connection.commit()
