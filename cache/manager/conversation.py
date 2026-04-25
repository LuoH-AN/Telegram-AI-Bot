"""Conversation cache mixin."""

from __future__ import annotations


class ConversationsMixin:
    def add_message_to_session(self, session_id: int, role: str, content: str) -> None:
        with self._lock:
            self._conversations_cache.setdefault(session_id, [])
            self._conversations_cache[session_id].append({"role": role, "content": content})
            self._dirty_conversations.add(session_id)

    def clear_conversation_by_session(self, session_id: int) -> None:
        with self._lock:
            self._conversations_cache[session_id] = []
            self._cleared_conversations.add(session_id)
            self._dirty_conversations.discard(session_id)

    def set_conversation_by_session(self, session_id: int, messages: list) -> None:
        with self._lock:
            self._conversations_cache[session_id] = [dict(m) for m in messages]

    def get_conversation_by_session(self, session_id: int) -> list:
        with self._lock:
            self._conversations_cache.setdefault(session_id, [])
            return [dict(m) for m in self._conversations_cache[session_id]]
