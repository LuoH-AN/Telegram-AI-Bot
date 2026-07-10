"""Regression tests for sync failure and session-id rekey safety."""

from __future__ import annotations

import pytest

from infrastructure.cache.manager.cache import CacheManager
from infrastructure.cache.sync import session as session_sync
from infrastructure.cache.sync import write as write_sync


class _Cursor:
    def __init__(self, new_id: int = 100):
        self.new_id = new_id
        self.last_sql = ""
        self.conversation_inserts: list[tuple] = []

    def execute(self, sql, params=None):
        self.last_sql = sql
        if "INSERT INTO user_conversations" in sql:
            self.conversation_inserts.append(params)

    def fetchone(self):
        if "RETURNING id" in self.last_sql:
            return (self.new_id,)
        if "COUNT(*)" in self.last_sql:
            return (0,)
        raise AssertionError(self.last_sql)


def test_sync_failure_restores_dirty_and_raises(monkeypatch):
    cache = CacheManager()
    cache.update_settings(7, "model", "new-model")

    def fail_connection():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(write_sync, "get_connection", fail_connection)
    with pytest.raises(RuntimeError, match="database unavailable"):
        write_sync.sync_to_database(cache)
    assert 7 in cache._dirty_settings
    assert cache.get_settings(7)["model"] == "new-model"


def test_refresh_stops_when_dirty_flush_fails(monkeypatch):
    import domain.services.sync_state.user as user_sync

    refreshed: list[int] = []
    monkeypatch.setattr(user_sync, "has_local_dirty_state", lambda _user_id: True)
    monkeypatch.setattr(user_sync, "sync_to_database", lambda: (_ for _ in ()).throw(RuntimeError("write failed")))
    monkeypatch.setattr(user_sync, "refresh_cache_from_db", refreshed.append)

    user_sync.refresh_user_state_from_db(9, force=True)
    assert refreshed == []


def test_late_write_using_old_session_id_is_persisted_under_new_id():
    cache = CacheManager()
    cache.get_settings(1)
    created = cache.create_session(1, "default")
    cache.set_current_session_id(1, "default", created["id"])
    old_id = created["id"]
    dirty = cache.get_and_clear_dirty()
    cursor = _Cursor(new_id=100)

    session_sync.sync_new(cursor, cache, dirty)
    cache.add_message_to_session(old_id, "user", "arrived after rekey")

    late_dirty = cache.get_and_clear_dirty()
    assert late_dirty["conversations"] == {100}
    assert cache.get_conversation_by_session(old_id)[0]["content"] == "arrived after rekey"

    session_sync.sync_conversations(cursor, cache, late_dirty)
    assert cursor.conversation_inserts
    assert cursor.conversation_inserts[0][2] == 100
