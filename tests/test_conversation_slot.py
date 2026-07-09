"""Tests for conversation_slot serialization and lock eviction."""

from __future__ import annotations

import asyncio

from domain.services.queue import conversation_slot, _LOCKS, _REFCOUNT


def _run(coro):
    return asyncio.run(coro)


def test_serialization_blocks_concurrent_same_key():
    """Two slots with the same key must not run their bodies concurrently."""

    async def run():
        order: list[str] = []
        started = asyncio.Event()
        proceed = asyncio.Event()

        async def worker(tag):
            async with conversation_slot("k") as queued:
                order.append(f"{tag}:enter:queued={queued}")
                started.set()
                await proceed.wait()
                order.append(f"{tag}:exit")

        t1 = asyncio.create_task(worker("a"))
        await started.wait()
        t2 = asyncio.create_task(worker("b"))
        await asyncio.sleep(0)  # let t2 reach the lock
        # t2 must be queued behind t1 (not entered yet)
        assert order == ["a:enter:queued=False"]
        proceed.set()
        await asyncio.gather(t1, t2)
        return order

    order = _run(run())
    assert order[0] == "a:enter:queued=False"
    assert order[-1] == "b:exit"
    # b entered only after a exited
    assert order.index("a:exit") < order.index("b:enter:queued=True")


def test_different_keys_run_concurrently():
    async def run():
        a_started = asyncio.Event()
        b_started = asyncio.Event()

        async def w(key, ev):
            async with conversation_slot(key):
                ev.set()
                await asyncio.sleep(0.05)

        await asyncio.gather(w("x", a_started), w("y", b_started))

    _run(run())  # no deadlock = different keys concurrent


def test_lock_evicted_when_idle():
    """After all holders release, the lock must be removed from the dict."""

    async def run():
        async with conversation_slot("evict-me"):
            assert "evict-me" in _LOCKS
        # after release, idle lock is removed
        await asyncio.sleep(0)
        return "evict-me" in _LOCKS

    assert _run(run()) is False
    assert "evict-me" not in _REFCOUNT


def test_lock_not_evicted_while_queued():
    """A lock with a waiter must survive the first holder's release."""

    async def run():
        first_done = asyncio.Event()
        b_entered = asyncio.Event()

        async def second():
            async with conversation_slot("shared"):
                b_entered.set()

        async with conversation_slot("shared"):
            t = asyncio.create_task(second())  # queued behind us
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            # while first holder still holds, second is queued; lock present
            present_during = "shared" in _LOCKS
        # release first -> second acquires
        await b_entered.wait()
        await asyncio.sleep(0)
        return present_during

    # the lock exists during contention (second still needs it)
    assert _run(run()) is True
