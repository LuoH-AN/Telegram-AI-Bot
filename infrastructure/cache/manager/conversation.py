"""Conversation infrastructure.cache mixin.

Memory is bounded per session: oldest *already-persisted* messages past
CONVERSATION_CACHE_CAP are dropped from the in-memory copy (their head offset is
tracked in _conv_offset). The next read reloads the full history from the DB and
resets the offset, so callers always see complete history. Messages not yet
persisted are never evicted, and append-sync (cached[db_count:]) stays correct
because eviction only removes the persisted prefix.
"""

from __future__ import annotations

from infrastructure.config import CONVERSATION_CACHE_CAP


class ConversationsMixin:
    def add_message_to_session(self, session_id: int, role: str, content: str, reasoning_content: str | None = None) -> None:
        with self._lock:
            self._conversations_cache.setdefault(session_id, [])
            msg: dict = {"role": role, "content": content}
            if reasoning_content:
                msg["reasoning_content"] = reasoning_content
            self._conversations_cache[session_id].append(msg)
            self._dirty_conversations.add(session_id)
            self._maybe_evict(session_id)

    def clear_conversation_by_session(self, session_id: int) -> None:
        with self._lock:
            self._conversations_cache[session_id] = []
            self._conv_offset.pop(session_id, None)
            self._persisted_msg_count.pop(session_id, None)
            self._cleared_conversations.add(session_id)
            self._dirty_conversations.discard(session_id)

    def set_conversation_by_session(self, session_id: int, messages: list) -> None:
        with self._lock:
            self._conversations_cache[session_id] = [dict(m) for m in messages]
            self._conv_offset.pop(session_id, None)
            self._maybe_evict(session_id)

    def get_conversation_by_session(self, session_id: int) -> list:
        with self._lock:
            return self._conversation_full(session_id)

    def _conversation_full(self, session_id: int) -> list:
        """Return the complete message list for a session, reloading from DB if
        the in-memory head was evicted. Resets the offset after reload, and
        preserves any in-memory tail not yet persisted."""
        offset = self._conv_offset.get(session_id, 0)
        if offset > 0:
            try:
                from infrastructure.cache.sync.conversation_reload import load_session_messages

                persisted = load_session_messages(session_id)
                persisted_n = len(persisted)
                current = self._conversations_cache.get(session_id, [])
                # current[i] is global index offset+i; keep only the part beyond the
                # persisted prefix (those messages are only in memory, not in the DB).
                keep_from = persisted_n - offset
                tail = current[keep_from:] if keep_from > 0 and keep_from < len(current) else []
                self._conversations_cache[session_id] = persisted + tail
                self._persisted_msg_count[session_id] = persisted_n
                self._conv_offset[session_id] = 0
            except Exception:
                pass  # DB unavailable: return whatever is cached
        self._conversations_cache.setdefault(session_id, [])
        return [dict(m) for m in self._conversations_cache[session_id]]

    def _maybe_evict(self, session_id: int) -> None:
        """Drop oldest persisted messages past the soft cap. Caller holds the lock."""
        cap = CONVERSATION_CACHE_CAP
        if cap <= 0:
            return
        messages = self._conversations_cache.get(session_id)
        if messages is None or len(messages) <= cap:
            return
        persisted = self._persisted_msg_count.get(session_id, 0)
        # Evict only from the persisted prefix; keep every unpersisted message.
        evictable = min(len(messages) - cap, persisted)
        if evictable <= 0:
            return
        self._conversations_cache[session_id] = messages[evictable:]
        self._conv_offset[session_id] = self._conv_offset.get(session_id, 0) + evictable

    def mark_conversation_persisted(self, session_id: int, count: int) -> None:
        """Record that `count` messages are confirmed in the DB (called after sync)."""
        with self._lock:
            self._persisted_msg_count[session_id] = max(self._persisted_msg_count.get(session_id, 0), count)
            self._maybe_evict(session_id)
