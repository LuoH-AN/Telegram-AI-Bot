"""Schema SQL for OneBot group configuration."""

CREATE_ONEBOT_GROUP_CONFIG_TABLE = """
    CREATE TABLE IF NOT EXISTS onebot_group_config (
        group_id BIGINT PRIMARY KEY,
        mode TEXT NOT NULL DEFAULT 'individual',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""
