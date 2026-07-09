"""Builtin toolset: database — per-entity user-data tools.

user_settings, user_personas, user_sessions, user_conversations, user_cron,
user_skills, user_skill_state, user_tokens. All scoped to the calling user and
routed through the cache layer (dirty-tracking + DB sync), never raw SQL.
"""
