"""Bounded concurrent dispatcher for inbound platform events.

Both OneBot and WeChat runtimes fan out incoming events to a handler with
the same pattern: a Semaphore bounds concurrent handlers, a set tracks
in-flight tasks, and a done-callback discards finished tasks while
logging exceptions. This module factors that pattern out.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def make_bounded_dispatcher(
    handler: Callable[[T], Awaitable[None]],
    *,
    max_concurrent: int,
    error_log_label: str,
    logger: logging.Logger,
) -> Callable[[T], Awaitable[None]]:
    """Return an async callback that schedules ``handler(item)`` with bounded concurrency.

    The returned callback creates a task per item, caps concurrency at
    ``max_concurrent`` via a Semaphore, tracks in-flight tasks, and logs
    any non-cancellation exception with ``error_log_label`` prefix.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    inflight: set[asyncio.Task] = set()

    async def _bounded(item: T) -> None:
        async with semaphore:
            await handler(item)

    async def _enqueue(item: T) -> None:
        task = asyncio.create_task(_bounded(item))
        inflight.add(task)

        def _on_done(done: asyncio.Task) -> None:
            inflight.discard(done)
            try:
                done.result()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("%s task failed", error_log_label)

        task.add_done_callback(_on_done)

    return _enqueue
