"""Conversation message helpers backed by the in-memory cache."""

from __future__ import annotations

from cache import cache


def ensure_session(user_id: int, persona_name: str | None = None) -> int:
    return cache.ensure_session_id(user_id, persona_name)


def get_conversation(session_id: int) -> list:
    return cache.get_conversation_by_session(session_id)


def add_message(session_id: int, role: str, content: str) -> None:
    cache.add_message_to_session(session_id, role, content)


def add_user_message(session_id: int, content: str) -> None:
    cache.add_message_to_session(session_id, "user", content)


def add_assistant_message(session_id: int, content: str) -> None:
    cache.add_message_to_session(session_id, "assistant", content)


def clear_conversation(session_id: int) -> None:
    cache.clear_conversation_by_session(session_id)


def get_message_count(session_id: int) -> int:
    return len(cache.get_conversation_by_session(session_id))
