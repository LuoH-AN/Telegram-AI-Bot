"""Tests for cache manager thread-safety (D1) and live-reference contract."""

from __future__ import annotations

import threading

from infrastructure.cache.manager.cache import CacheManager


def test_live_reference_mutation_persists():
    """update_memory mutates the list returned by get_memories in place."""
    cache = CacheManager()
    cache.get_settings(1)
    cache.add_memory(1, "hello")
    mems = cache.get_memories(1)
    mems.append({"id": None, "user_id": 1, "content": "inplace", "source": "user", "embedding": None})
    assert cache.get_memories(1)[-1]["content"] == "inplace"


def test_token_usage_live_reference_mutation():
    cache = CacheManager()
    cache.get_settings(1)
    cache.get_token_usage(1, "default")["prompt_tokens"] = 7
    assert cache.get_token_usage(1, "default")["prompt_tokens"] == 7


def test_concurrent_writers_and_iterators_no_race():
    """get_all_cron_tasks / runtime_stats must not raise under concurrent mutation."""
    cache = CacheManager()
    cache.get_settings(1)
    stop = threading.Event()
    errors: list[tuple] = []

    def writer():
        i = 0
        while not stop.is_set():
            cache.add_memory(1, f"m{i}")
            cache.add_cron_task(1, f"c{i}", "* * * * *", "p")
            cache.update_settings(1, "k", i)
            cache.add_token_usage(1, 1, 1, "default")
            i += 1

    def iterator():
        try:
            while not stop.is_set():
                cache.get_all_cron_tasks()
                cache.runtime_stats()
        except Exception as exc:
            errors.append(("iter", repr(exc)))

    threads = [threading.Thread(target=writer) for _ in range(3)]
    threads += [threading.Thread(target=iterator) for _ in range(3)]
    for t in threads:
        t.start()
    try:
        import time as _time

        _time.sleep(1.0)
    finally:
        stop.set()
    for t in threads:
        t.join()
    assert not errors, errors


def test_runtime_stats_reports_memory_pressure():
    cache = CacheManager()
    cache.add_message_to_session(1, "user", "x" * 500)
    stats = cache.runtime_stats()
    assert stats["messages"] == 1
    assert stats["approx_conversation_bytes"] >= 500


def test_dirty_trackers_populated_and_cleared():
    cache = CacheManager()
    cache.get_settings(1)
    cache.add_memory(1, "x")
    dirty = cache.get_and_clear_dirty()
    assert 1 in dirty["settings"]
    assert dirty["new_memories"]
    # after clearing, a second snapshot is empty
    assert not cache.get_and_clear_dirty()["new_memories"]
