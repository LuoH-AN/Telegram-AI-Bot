"""In-memory + DB-backed state store."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .ids import local_user_id_for_wechat
from .state_models import WeChatAccountState
from .state_store_db import load_state_from_db, save_state_to_db


class WeChatStateStore:
    """Persist login state and peer mappings to PostgreSQL."""

    def __init__(self, state_dir: str | Path, *, account_key: str = "default", logger=None):
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._account_key = (account_key or "default").strip() or "default"
        self._lock = threading.RLock()
        self._cached_state: WeChatAccountState | None = None
        self._logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _clone_state(state: WeChatAccountState) -> WeChatAccountState:
        return WeChatAccountState(
            token=state.token,
            user_id=state.user_id,
            base_url=state.base_url,
            get_updates_buf=state.get_updates_buf,
            peer_map=dict(state.peer_map),
            context_tokens=dict(state.context_tokens),
        )

    def load(self, *, force: bool = False) -> WeChatAccountState:
        with self._lock:
            if self._cached_state is None or force:
                self._cached_state = load_state_from_db(self._account_key, self._logger)
            return self._clone_state(self._cached_state)

    def save(self, state: WeChatAccountState) -> None:
        with self._lock:
            self._cached_state = self._clone_state(state)
            save_state_to_db(self._account_key, state, self._logger)

    def clear_token(self) -> None:
        state = self.load()
        state.token = ""
        state.user_id = ""
        state.get_updates_buf = ""
        self.save(state)

    def remember_peer(self, peer_id: str, *, context_token: str | None = None) -> int:
        state = self.load()
        local_id = local_user_id_for_wechat(peer_id)
        state.peer_map[str(local_id)] = peer_id
        if context_token:
            state.context_tokens[peer_id] = context_token
        self.save(state)
        return local_id

    def remember_context_token(self, scope_id: str, context_token: str) -> None:
        if scope_id and context_token:
            state = self.load()
            state.context_tokens[scope_id] = context_token
            self.save(state)

    def resolve_peer(self, local_user_id: int) -> str | None:
        return self.load().peer_map.get(str(local_user_id))

    def resolve_context_token(self, peer_id: str) -> str | None:
        return self.load().context_tokens.get(peer_id)
