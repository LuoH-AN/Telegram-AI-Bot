"""Dirty-state initializers."""


def init_dirty_state(obj) -> None:
    obj._dirty_settings = set()
    obj._dirty_personas = set()
    obj._deleted_personas = set()
    obj._dirty_conversations = set()
    obj._cleared_conversations = set()
    obj._dirty_tokens = set()
    obj._new_memories = []
    obj._deleted_memory_ids = []
    obj._cleared_memories = set()
    obj._new_cron_tasks = []
    obj._updated_cron_tasks = []
    obj._deleted_cron_tasks = []
    obj._new_skills = []
    obj._updated_skills = []
    obj._deleted_skills = []
    obj._updated_skill_states = []
    obj._new_sessions = []
    obj._dirty_session_titles = {}
    obj._deleted_sessions = set()
