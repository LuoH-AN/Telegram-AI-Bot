"""Queue push/pop operations for limiter worker."""

from __future__ import annotations

import asyncio
import heapq
import logging

from .item import QueueItem

logger = logging.getLogger(__name__)


class RateLimiterQueueMixin:
    async def _enqueue(self, item: QueueItem) -> None:
        condition = self._condition
        if condition is None:
            raise RuntimeError("Rate limiter not initialized")

        async with condition:
            if item.dedup_key:
                previous = self._pending_edits.get(item.dedup_key)
                if previous is not None and previous is not item and not previous.dispatched and not previous.future.done():
                    previous.canceled = True
                    previous.future.set_result(True)
                    self.edit_superseded_count += 1
                self._pending_edits[item.dedup_key] = item

            heapq.heappush(self._queue, item)
            queue_size = len(self._queue)
            self.queue_peak = max(self.queue_peak, queue_size)
            if queue_size >= self._queue_warn_threshold and queue_size > self._last_warned_queue:
                self._last_warned_queue = queue_size
                logger.warning("Telegram send queue backlog=%d (peak=%d)", queue_size, self.queue_peak)
            condition.notify()

    async def _next_ready_item(self) -> QueueItem | None:
        condition = self._condition
        if condition is None:
            return None

        loop = asyncio.get_running_loop()
        while True:
            async with condition:
                while not self._queue and not self._shutdown:
                    await condition.wait()
                if self._shutdown:
                    return None
                next_item = self._queue[0]
                delay = next_item.ready_at - loop.time()
                if delay > 0:
                    try:
                        await asyncio.wait_for(condition.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
                    continue
                return heapq.heappop(self._queue)
