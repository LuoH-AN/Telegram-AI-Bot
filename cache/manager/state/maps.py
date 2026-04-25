"""Cache map initializers."""


def init_cache_maps(obj) -> None:
    obj._settings_cache = {}
    obj._personas_cache = {}
    obj._sessions_cache = {}
    obj._conversations_cache = {}
    obj._persona_tokens_cache = {}
    obj._memories_cache = {}
    obj._cron_tasks_cache = {}
    obj._skills_cache = {}
    obj._skill_states_cache = {}
