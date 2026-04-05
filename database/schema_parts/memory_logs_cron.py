"""Schema SQL for memory, logs, and cron tables."""

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

CREATE_USER_LOGS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_logs (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        log_type TEXT NOT NULL,
        model TEXT,
        prompt_tokens INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
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
