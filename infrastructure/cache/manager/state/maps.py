"""Cache map initializers."""


def init_cache_maps(obj) -> None:
    obj._settings_cache = {}
    obj._personas_cache = {}
    obj._sessions_cache = {}
    obj._conversations_cache = {}
    # Per-session count of messages confirmed persisted to the DB, and how many
    # oldest messages were dropped from the in-memory copy (head offset). Used to
    # bound memory: oldest already-persisted messages are evicted past a cap and
    # reloaded from the DB on next read. Head offset 0 == nothing dropped.
    obj._persisted_msg_count = {}
    obj._conv_offset = {}
    obj._persona_tokens_cache = {}
    obj._memories_cache = {}
    obj._cron_tasks_cache = {}
    obj._skills_cache = {}
    obj._skill_states_cache = {}
