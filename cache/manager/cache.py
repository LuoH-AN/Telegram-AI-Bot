"""Cache manager composition."""

from __future__ import annotations

import threading

from .conversation import ConversationsMixin
from .cron import CronMixin
from .dirty import DirtyMixin
from .memory import MemoriesMixin
from .persona import PersonasMixin
from .session.current import SessionsCurrentMixin
from .session.store import SessionsStoreMixin
from .settings import SettingsMixin
from .skill import SkillsMixin
from .state.maps import init_cache_maps
from .state.dirty import init_dirty_state
from .token import TokensMixin


class CacheManager(
    SettingsMixin,
    PersonasMixin,
    SessionsStoreMixin,
    SessionsCurrentMixin,
    ConversationsMixin,
    TokensMixin,
    MemoriesMixin,
    CronMixin,
    SkillsMixin,
    DirtyMixin,
):
    """Manages in-memory caches and dirty sync state."""

    def __init__(self):
        self._lock = threading.RLock()
        init_cache_maps(self)
        init_dirty_state(self)
        # Temporary ID for sessions not yet persisted. Initialized to DB max(id)
        # by cache/sync/session.py:load() and re-keyed to the real SERIAL value
        # in cache/sync/session.py:sync_new() via _rekey(). Not a stable key.
        self._session_id_counter = 0

    def _next_session_id(self) -> int:
        with self._lock:
            self._session_id_counter += 1
            return self._session_id_counter
