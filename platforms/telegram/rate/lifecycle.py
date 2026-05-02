"""Lifecycle and request entrypoint mixin."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from .config import LOW_PRIORITY_ENDPOINTS, QUEUED_ENDPOINTS, to_chat_key
from .item import QueueItem

logger = logging.getLogger(__name__)


class RateLimiterLifecycleMixin:
    async def initialize(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            self._condition = asyncio.Condition()
            self._shutdown = False
            self._worker = asyncio.create_task(self._worker_loop(), name="telegram-send-queue")
            self._initialized = True
            logger.info(
                "Telegram queued rate limiter enabled "
                "(global_interval=%.3fs, per_chat_interval=%.3fs, per_chat_edit_interval=%.3fs, max_retries=%d)",
                self._overall_interval,
                self._per_chat_interval,
                self._per_chat_edit_interval,
                self._max_retries,
            )

    async def shutdown(self) -> None:
        async with self._init_lock:
            if not self._initialized:
                return
            self._shutdown = True
            if self._condition is not None:
                async with self._condition:
                    self._condition.notify_all()
            if self._worker is not None:
                self._worker.cancel()
                await asyncio.gather(self._worker, return_exceptions=True)
            for item in self._queue:
                if not item.future.done():
                    item.future.cancel()
            self._queue.clear()
            self._pending_edits.clear()
            self._chat_next_at.clear()
            self._chat_edit_next_at.clear()
            self._global_next_at = 0.0
            self._worker = None
            self._condition = None
            self._initialized = False

    async def process_request(
        self,
        callback: Callable[..., Coroutine[Any, Any, Any]],
        args: Any,
        kwargs: dict[str, Any],
        endpoint: str,
        data: dict[str, Any],
        rate_limit_args: int | None,
    ) -> Any:
        await self.initialize()
        max_retries = self._resolve_max_retries(rate_limit_args)
        if endpoint not in QUEUED_ENDPOINTS:
            return await self._run_direct(callback, args, kwargs, endpoint, max_retries)

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        item = QueueItem(
            ready_at=loop.time(),
            priority=20 if endpoint in LOW_PRIORITY_ENDPOINTS else 10,
            sequence=next(self._seq),
            callback=callback,
            args=args,
            kwargs=kwargs,
            future=future,
            endpoint=endpoint,
            chat_key=to_chat_key(data.get("chat_id")),
            dedup_key=self._build_edit_dedup_key(endpoint, data),
            max_retries=max_retries,
        )
        await self._enqueue(item)
        return await future
