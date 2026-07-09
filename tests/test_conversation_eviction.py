"""Tests for bounded conversation cache eviction (data-safety contract).

These pin the invariant: oldest already-persisted messages may be dropped from
memory, but a read always returns the *complete* history (reloading from the DB
when the in-memory head was evicted), and messages not yet persisted are never
evicted (so append-sync never loses them).
"""

from __future__ import annotations

import infrastructure.cache.manager.conversation as conv_mod
import infrastructure.config as cfg


def test_cap_zero_disables_eviction():
    conv_mod.CONVERSATION_CACHE_CAP = 0
    cache = conv_mod.ConversationsMixin.__new__(conv_mod.ConversationsMixin)
    import threading

    cache._lock = threading.RLock()
    cache._conversations_cache = {1: []}
    cache._persisted_msg_count = {}
    cache._conv_offset = {}
    cache._dirty_conversations = set()
    cache._cleared_conversations = set()
    cache._maybe_evict(1)
    assert cache._conv_offset == {}


def _fresh_cache(cap, persisted_db=None):
    """Build a ConversationsMixin with a fake DB backing the reload helper."""
    import threading

    cache = conv_mod.ConversationsMixin.__new__(conv_mod.ConversationsMixin)
    cache._lock = threading.RLock()
    cache._conversations_cache = {}
    cache._persisted_msg_count = {}
    cache._conv_offset = {}
    cache._dirty_conversations = set()
    cache._cleared_conversations = set()
    # conversation.py binds CONVERSATION_CACHE_CAP at import; set it on the module.
    conv_mod.CONVERSATION_CACHE_CAP = cap
    # persisted_db: session_id -> full ordered message list (the "DB")
    cache._fake_db = persisted_db or {}

    def fake_load(session_id):
        return [dict(m) for m in cache._fake_db.get(session_id, [])]

    import infrastructure.cache.sync.conversation_reload as cr

    orig = cr.load_session_messages
    cr.load_session_messages = fake_load
    return cache, orig


def test_eviction_only_drops_persisted_prefix_and_reload_restores(monkeypatch):
    db = {7: [{"role": "user", "content": f"u{i}"} for i in range(50)]}
    cache, orig = _fresh_cache(cap=10, persisted_db=db)
    # Simulate: 50 persisted messages loaded, then a fresh unpersisted one added.
    cache._conversations_cache[7] = [dict(m) for m in db[7]] + [{"role": "assistant", "content": "NEW"}]
    cache._persisted_msg_count[7] = 50
    cache._dirty_conversations.add(7)

    cache._maybe_evict(7)
    # Eviction keeps the last `cap` messages; the unpersisted NEW must survive.
    assert len(cache._conversations_cache[7]) == 10
    assert cache._conversations_cache[7][-1]["content"] == "NEW"
    assert cache._conv_offset[7] == 41  # dropped 41 of the 51 in-memory messages

    # A read reloads the full DB history, reattaches the unpersisted NEW, resets offset.
    full = cache.get_conversation_by_session(7)
    assert len(full) == 51  # 50 persisted (from DB) + the still-unpersisted NEW
    assert full[-1]["content"] == "NEW"
    assert full[0]["content"] == "u0"  # evicted head restored from DB
    assert cache._conv_offset[7] == 0


def test_unpersisted_messages_never_evicted(monkeypatch):
    # Nothing persisted yet; cache well over cap -> nothing can be evicted
    db = {}
    cache, orig = _fresh_cache(cap=5, persisted_db=db)
    cache._conversations_cache[7] = [{"role": "user", "content": f"m{i}"} for i in range(30)]
    cache._persisted_msg_count[7] = 0  # nothing persisted
    cache._maybe_evict(7)
    assert len(cache._conversations_cache[7]) == 30  # untouched


def test_mark_persisted_then_evict_keeps_tail():
    db = {}
    cache, orig = _fresh_cache(cap=4, persisted_db=db)
    cache._conversations_cache[7] = [{"role": "user", "content": f"m{i}"} for i in range(8)]
    # After sync, all 8 are persisted
    cache.mark_conversation_persisted(7, 8)
    assert len(cache._conversations_cache[7]) == 4
    assert cache._conv_offset[7] == 4


def test_clear_resets_offset_and_count():
    db = {}
    cache, orig = _fresh_cache(cap=4, persisted_db=db)
    cache._conversations_cache[7] = [{"role": "user", "content": f"m{i}"} for i in range(8)]
    cache._persisted_msg_count[7] = 8
    cache.mark_conversation_persisted(7, 8)
    assert cache._conv_offset.get(7, 0) > 0
    cache.clear_conversation_by_session(7)
    assert 7 not in cache._conv_offset
    assert 7 not in cache._persisted_msg_count
    assert cache._conversations_cache[7] == []
