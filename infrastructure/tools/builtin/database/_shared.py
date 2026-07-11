"""Shared helpers for the per-entity user-data tools (admin toolset).

Each tool is scoped to the calling user and mutates state through the cache
layer, which owns dirty-tracking and DB sync — no raw SQL leaves this package.
"""

from __future__ import annotations

import json
from typing import Any

USER_DATA_INSTRUCTION = (
    "\nuser_* tools (admin toolset) read and change the calling user's OWN data — "
    "every call is scoped to that user, no raw SQL:\n"
    "- user_settings: list|get|set (api_key, base_url, model, temperature, reasoning_effort, "
    "token_limit, current_persona, global_prompt, title_model, cron_model, ...). "
    "Clear a field by setting it to \"\".\n"
    "- user_personas: list|get|create|edit|delete|switch (name + prompt).\n"
    "- user_sessions: list|get|rename|delete|switch (persona; session_id; title).\n"
    "- user_conversations: list|get|clear|replace (session_id; messages=[{role, content}]). "
    "replace overwrites the whole session.\n"
    "- user_cron: list|get|add|update|delete (name; cron; prompt; enabled).\n"
    "- user_skills: list|get|toggle|delete (name; enabled).\n"
    "- user_skill_state: get|set (name; state object). set {} to clear.\n"
    "- user_tokens: get|reset|set_limit (persona; limit).\n"
    "Prefer these over terminal/psql for user data."
)


def get_cache():
    from infrastructure.cache import cache

    return cache


def commit() -> None:
    """Flush cache dirty state to the database after a mutation."""
    from infrastructure.cache import sync_to_database

    sync_to_database()


def dumps(value: Any, indent: bool = True) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2 if indent else None, default=str)
