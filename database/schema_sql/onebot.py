"""Schema SQL for OneBot group configuration."""

CREATE_ONEBOT_GROUP_CONFIG_TABLE = """
    CREATE TABLE IF NOT EXISTS onebot_group_config (
        group_id BIGINT PRIMARY KEY,
        mode TEXT NOT NULL DEFAULT 'individual',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_ONEBOT_PROACTIVE_CONFIG_TABLE = """
    CREATE TABLE IF NOT EXISTS onebot_proactive_config (
        group_id BIGINT PRIMARY KEY,
        enabled BOOLEAN NOT NULL DEFAULT FALSE,
        probability REAL NOT NULL DEFAULT 0.1,
        keywords TEXT NOT NULL DEFAULT '',
        blacklist TEXT NOT NULL DEFAULT '',
        mute_until BIGINT NOT NULL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""
