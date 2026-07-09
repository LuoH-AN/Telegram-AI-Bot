"""Tests for the Telegram rate limiter: edit supersession (Q1) and global window (M4).

Each test drives its own event loop via asyncio.run so only plain pytest is needed.
"""

from __future__ import annotations

import asyncio

from telegram.error import RetryAfter

from adapters.telegram.rate.item import QueueItem
from adapters.telegram.rate.limiter import QueuedRateLimiter


def _new_limiter():
    lim = QueuedRateLimiter()
    lim._condition = asyncio.Condition()
    return lim


def _item(seq, *, chat_key, dedup_key, endpoint="editMessageText"):
    loop = asyncio.get_event_loop()
    return QueueItem(
        ready_at=loop.time(),
        priority=10,
        sequence=seq,
        callback=lambda: None,
        args=(),
        kwargs={},
        future=loop.create_future(),
        endpoint=endpoint,
        chat_key=chat_key,
        dedup_key=dedup_key,
        max_retries=8,
    )


def test_global_window_advances_on_chat_routed_retryafter():
    lim = _new_limiter()

    async def run():
        item = _item(1, chat_key=123, dedup_key=None, endpoint="sendMessage")
        await lim._handle_retry_after(item, RetryAfter(retry_after=5))
        return lim._global_next_at, lim._chat_next_at.get(123, 0)

    g, c = asyncio.run(run())
    assert g > 0
    assert c > 0


def test_old_superseded_edit_abandoned_on_retry():
    lim = _new_limiter()

    async def run():
        key = "editMessageText:123:42"
        old = _item(1, chat_key=123, dedup_key=key)
        new = _item(2, chat_key=123, dedup_key=key)
        # Real flow: old was already popped from the queue and dispatched when the
        # 429 arrived, so only register it as the dedup owner — do not enqueue it.
        old.dispatched = True
        lim._pending_edits[key] = old
        await lim._enqueue(new)               # newer edit takes ownership
        assert lim._pending_edits[key] is new
        await lim._handle_retry_after(old, RetryAfter(retry_after=3))
        return old, new, key

    old, new, key = asyncio.run(run())
    assert old.future.done() and old.future.result() is True
    assert not any(it is old for it in lim._queue)
    assert lim._pending_edits[key] is new


def test_newer_supersedes_older_pending():
    lim = _new_limiter()

    async def run():
        key = "editMessageText:999:7"
        older = _item(10, chat_key=999, dedup_key=key)
        newer = _item(20, chat_key=999, dedup_key=key)
        await lim._enqueue(older)
        await lim._enqueue(newer)
        return older

    assert asyncio.run(run()).canceled is True


def test_older_does_not_supersede_newer():
    lim = _new_limiter()

    async def run():
        key = "editMessageText:555:1"
        newer = _item(30, chat_key=555, dedup_key=key)
        older = _item(10, chat_key=555, dedup_key=key)
        await lim._enqueue(newer)
        await lim._enqueue(older)
        return newer

    assert asyncio.run(run()).canceled is False
