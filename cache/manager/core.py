"""Cache manager composition."""

from __future__ import annotations

import threading

from .conversations import ConversationsMixin
from .cron import CronMixin
from .dirty import DirtyMixin
from .memories import MemoriesMixin
from .personas import PersonasMixin
from .sessions_current import SessionsCurrentMixin
from .sessions_store import SessionsStoreMixin
from .settings import SettingsMixin
from .skills import SkillsMixin
from .state_caches import init_cache_maps
from .state_dirty import init_dirty_state
from .tokens import TokensMixin


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
        self._session_id_counter = 0

    def _next_session_id(self) -> int:
        with self._lock:
            self._session_id_counter += 1
            return self._session_id_counter
