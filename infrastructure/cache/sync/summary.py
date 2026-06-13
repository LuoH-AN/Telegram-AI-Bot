"""Sync summary logging."""

from __future__ import annotations

LABELS = {
    "settings": "settings",
    "personas": "personas",
    "deleted_personas": "deleted personas",
    "new_sessions": "new sessions",
    "dirty_session_titles": "session titles",
    "deleted_sessions": "deleted sessions",
    "conversations": "conversations",
    "cleared_conversations": "cleared convs",
    "tokens": "token records",
    "new_memories": "new memories",
    "deleted_memory_ids": "deleted memories",
    "cleared_memories": "cleared memories",
    "new_cron_tasks": "new cron tasks",
    "updated_cron_tasks": "updated cron tasks",
    "deleted_cron_tasks": "deleted cron tasks",
    "new_skills": "new skills",
    "updated_skills": "updated skills",
    "deleted_skills": "deleted skills",
    "updated_skill_states": "updated skill states",
}


def log_sync_summary(logger, dirty: dict) -> None:
    parts = [f"{len(dirty[key])} {label}" for key, label in LABELS.items() if dirty.get(key)]
    if parts:
        logger.info("Synced to DB: %s", ", ".join(parts))
