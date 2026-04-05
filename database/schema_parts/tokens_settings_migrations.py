"""Schema SQL for token usage table."""

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
