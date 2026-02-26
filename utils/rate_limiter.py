"""Queued Telegram rate limiter with RetryAfter requeue support."""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from telegram.error import RetryAfter
from telegram.ext import BaseRateLimiter

logger = logging.getLogger(__name__)


_QUEUED_ENDPOINTS = {
    "copyMessage",
    "deleteMessage",
    "editMessageCaption",
    "editMessageLiveLocation",
    "editMessageMedia",
    "editMessageReplyMarkup",
    "editMessageText",
    "forwardMessage",
    "sendAnimation",
    "sendAudio",
    "sendChatAction",
    "sendContact",
    "sendDice",
    "sendDocument",
    "sendInvoice",
    "sendLocation",
    "sendMediaGroup",
    "sendMessage",
    "sendPhoto",
    "sendPoll",
    "sendSticker",
    "sendVenue",
    "sendVideo",
    "sendVideoNote",
    "sendVoice",
    "stopMessageLiveLocation",
}


_LOW_PRIORITY_ENDPOINTS = {
    "sendChatAction",
}


_EDIT_ENDPOINTS = {
    "editMessageCaption",
    "editMessageMedia",
    "editMessageReplyMarkup",
    "editMessageText",
}


def _to_chat_key(chat_id: Any) -> int | str | None:
    """Normalize chat_id for per-chat throttling."""
    if chat_id is None:
        return None
    if isinstance(chat_id, int):
        return chat_id
    if isinstance(chat_id, str):
        try:
            return int(chat_id)
        except ValueError:
            return chat_id
    return str(chat_id)


@dataclass(order=True)
class _QueueItem:
    """Single queued Telegram API request."""

    ready_at: float
    priority: int
    sequence: int
    callback: Callable[..., Coroutine[Any, Any, Any]] = field(compare=False)
    args: Any = field(compare=False)
    kwargs: dict[str, Any] = field(compare=False)
    future: asyncio.Future[Any] = field(compare=False)
    endpoint: str = field(compare=False)
    chat_key: int | str | None = field(compare=False)
    dedup_key: str | None = field(compare=False, default=None)
    max_retries: int = field(compare=False, default=0)
    retries: int = field(compare=False, default=0)
    canceled: bool = field(compare=False, default=False)
    dispatched: bool = field(compare=False, default=False)


class QueuedRateLimiter(BaseRateLimiter[int]):
    """Queue-based rate limiter for Telegram API write operations.

    Features:
    - Global + per-chat throttling
    - RetryAfter delayed requeue (non-blocking for the worker)
    - Dedup for high-frequency edit requests
    - Basic runtime metrics for observability
    """

    def __init__(
        self,
        *,
        overall_max_rate: float = 25.0,
        overall_time_period: float = 1.0,
        per_chat_max_rate: float = 1.0,
        per_chat_time_period: float = 1.0,
        per_chat_edit_max_rate: float | None = None,
        per_chat_edit_time_period: float = 1.0,
        max_retries: int = 8,
        retry_jitter: float = 0.4,
        queue_warn_threshold: int = 100,
    ) -> None:
        self._overall_interval = (
            overall_time_period / overall_max_rate if overall_max_rate > 0 and overall_time_period > 0 else 0.0
        )
        self._per_chat_interval = (
            per_chat_time_period / per_chat_max_rate
            if per_chat_max_rate > 0 and per_chat_time_period > 0
            else 0.0
        )
        if per_chat_edit_max_rate is None:
            self._per_chat_edit_interval = self._per_chat_interval
        else:
            self._per_chat_edit_interval = (
                per_chat_edit_time_period / per_chat_edit_max_rate
                if per_chat_edit_max_rate > 0 and per_chat_edit_time_period > 0
                else 0.0
            )
        self._max_retries = max_retries
        self._retry_jitter = max(0.0, retry_jitter)
        self._queue_warn_threshold = max(1, queue_warn_threshold)

        self._global_next_at = 0.0
        self._chat_next_at: dict[int | str, float] = {}
        self._chat_edit_next_at: dict[int | str, float] = {}

        self._queue: list[_QueueItem] = []
        self._pending_edits: dict[str, _QueueItem] = {}
        self._condition: asyncio.Condition | None = None
        self._worker: asyncio.Task[None] | None = None
        self._initialized = False
        self._shutdown = False
        self._init_lock = asyncio.Lock()
        self._seq = itertools.count()

        # Metrics
        self.retry_after_count = 0
        self.max_retry_after_seconds = 0.0
        self.queue_peak = 0
        self.edit_superseded_count = 0
        self._last_warned_queue = 0

    async def initialize(self) -> None:
        """Initialize worker resources."""
        async with self._init_lock:
            if self._initialized:
                return

            self._condition = asyncio.Condition()
            self._shutdown = False
            self._worker = asyncio.create_task(
                self._worker_loop(),
                name="telegram-send-queue",
            )
            self._initialized = True
            logger.info(
                "Telegram queued rate limiter enabled "
                "(global_interval=%.3fs, per_chat_interval=%.3fs, "
                "per_chat_edit_interval=%.3fs, max_retries=%d)",
                self._overall_interval,
                self._per_chat_interval,
                self._per_chat_edit_interval,
                self._max_retries,
            )

    async def shutdown(self) -> None:
        """Stop worker and fail pending queued requests."""
        async with self._init_lock:
            if not self._initialized:
                return

            self._shutdown = True
            condition = self._condition
            if condition is not None:
                async with condition:
                    condition.notify_all()

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
        """Process a Telegram request with queue/rate-limit strategy."""
        await self.initialize()
        max_retries = self._resolve_max_retries(rate_limit_args)

        if endpoint not in _QUEUED_ENDPOINTS:
            return await self._run_direct(callback, args, kwargs, endpoint, max_retries)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        chat_key = _to_chat_key(data.get("chat_id"))
        dedup_key = self._build_edit_dedup_key(endpoint, data)
        priority = 20 if endpoint in _LOW_PRIORITY_ENDPOINTS else 10

        item = _QueueItem(
            ready_at=loop.time(),
            priority=priority,
            sequence=next(self._seq),
            callback=callback,
            args=args,
            kwargs=kwargs,
            future=future,
            endpoint=endpoint,
            chat_key=chat_key,
            dedup_key=dedup_key,
            max_retries=max_retries,
        )
        await self._enqueue(item)
        return await future

    async def _enqueue(self, item: _QueueItem) -> None:
        """Push request into heap queue and notify worker."""
        condition = self._condition
        if condition is None:
            raise RuntimeError("Rate limiter not initialized")

        async with condition:
            if item.dedup_key:
                previous = self._pending_edits.get(item.dedup_key)
                if (
                    previous is not None
                    and previous is not item
                    and not previous.dispatched
                    and not previous.future.done()
                ):
                    previous.canceled = True
                    previous.future.set_result(True)
                    self.edit_superseded_count += 1
                self._pending_edits[item.dedup_key] = item

            heapq.heappush(self._queue, item)
            queue_size = len(self._queue)
            if queue_size > self.queue_peak:
                self.queue_peak = queue_size
            if queue_size >= self._queue_warn_threshold and queue_size > self._last_warned_queue:
                self._last_warned_queue = queue_size
                logger.warning(
                    "Telegram send queue backlog=%d (peak=%d)",
                    queue_size,
                    self.queue_peak,
                )
            condition.notify()

    async def _worker_loop(self) -> None:
        """Main worker loop."""
        try:
            while True:
                item = await self._next_ready_item()
                if item is None:
                    return
                if item.canceled:
                    self._clear_dedup_if_owner(item)
                    continue

                if self._should_delay_for_limits(item):
                    await self._enqueue(item)
                    continue

                await self._dispatch_item(item)
        except asyncio.CancelledError:
            return

    async def _next_ready_item(self) -> _QueueItem | None:
        """Wait until at least one request is due for dispatch."""
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

    def _should_delay_for_limits(self, item: _QueueItem) -> bool:
        """Reschedule item if global/per-chat throttle windows are not open yet."""
        now = asyncio.get_running_loop().time()
        next_allowed = item.ready_at

        if self._overall_interval > 0:
            next_allowed = max(next_allowed, self._global_next_at)

        if item.chat_key is not None:
            if item.endpoint in _EDIT_ENDPOINTS:
                if self._per_chat_edit_interval > 0:
                    next_allowed = max(next_allowed, self._chat_edit_next_at.get(item.chat_key, 0.0))
            elif self._per_chat_interval > 0:
                next_allowed = max(next_allowed, self._chat_next_at.get(item.chat_key, 0.0))

        if next_allowed <= now:
            return False

        item.ready_at = next_allowed
        return True

    async def _dispatch_item(self, item: _QueueItem) -> None:
        """Execute one queued request and resolve/requeue future."""
        item.dispatched = True

        try:
            result = await item.callback(*item.args, **item.kwargs)
        except RetryAfter as exc:
            await self._handle_retry_after(item, exc)
            return
        except Exception as exc:
            self._clear_dedup_if_owner(item)
            if not item.future.done():
                item.future.set_exception(exc)
            return

        self._clear_dedup_if_owner(item)
        self._advance_windows(item)
        if not item.future.done():
            item.future.set_result(result)

    async def _handle_retry_after(self, item: _QueueItem, exc: RetryAfter) -> None:
        """Requeue request with RetryAfter delay if retries remain."""
        retry_after = float(getattr(exc, "retry_after", 0.0) or 0.0)
        self.retry_after_count += 1
        if retry_after > self.max_retry_after_seconds:
            self.max_retry_after_seconds = retry_after

        if not self._has_retries_left(item.retries, item.max_retries):
            self._clear_dedup_if_owner(item)
            if not item.future.done():
                item.future.set_exception(exc)
            logger.warning(
                "Telegram RetryAfter exhausted retries for %s chat=%s wait=%.2fs",
                item.endpoint,
                item.chat_key,
                retry_after,
            )
            return

        item.retries += 1
        item.dispatched = False
        item.ready_at = asyncio.get_running_loop().time() + retry_after + random.uniform(0, self._retry_jitter)

        # RetryAfter usually targets the current chat; avoid blocking all chats.
        if item.chat_key is not None:
            if item.endpoint in _EDIT_ENDPOINTS:
                self._chat_edit_next_at[item.chat_key] = max(
                    self._chat_edit_next_at.get(item.chat_key, 0.0),
                    item.ready_at,
                )
            else:
                self._chat_next_at[item.chat_key] = max(
                    self._chat_next_at.get(item.chat_key, 0.0),
                    item.ready_at,
                )
        else:
            self._global_next_at = max(self._global_next_at, item.ready_at)

        logger.warning(
            "Telegram RetryAfter on %s chat=%s, retry=%d/%s, wait=%.2fs, queue=%d",
            item.endpoint,
            item.chat_key,
            item.retries,
            "inf" if item.max_retries < 0 else str(item.max_retries),
            retry_after,
            len(self._queue),
        )
        await self._enqueue(item)

    async def _run_direct(
        self,
        callback: Callable[..., Coroutine[Any, Any, Any]],
        args: Any,
        kwargs: dict[str, Any],
        endpoint: str,
        max_retries: int,
    ) -> Any:
        """Run non-queued requests with RetryAfter retries."""
        attempts = 0
        while True:
            try:
                return await callback(*args, **kwargs)
            except RetryAfter as exc:
                retry_after = float(getattr(exc, "retry_after", 0.0) or 0.0)
                self.retry_after_count += 1
                if retry_after > self.max_retry_after_seconds:
                    self.max_retry_after_seconds = retry_after

                if not self._has_retries_left(attempts, max_retries):
                    raise

                attempts += 1
                delay = retry_after + random.uniform(0, self._retry_jitter)
                logger.warning(
                    "Telegram RetryAfter on %s (direct), retry=%d/%s, wait=%.2fs",
                    endpoint,
                    attempts,
                    "inf" if max_retries < 0 else str(max_retries),
                    retry_after,
                )
                await asyncio.sleep(delay)

    def _advance_windows(self, item: _QueueItem) -> None:
        """Advance global and per-chat windows after a successful dispatch."""
        now = asyncio.get_running_loop().time()

        if self._overall_interval > 0:
            self._global_next_at = max(self._global_next_at, now) + self._overall_interval

        if item.chat_key is not None:
            if item.endpoint in _EDIT_ENDPOINTS:
                if self._per_chat_edit_interval > 0:
                    chat_next = self._chat_edit_next_at.get(item.chat_key, 0.0)
                    self._chat_edit_next_at[item.chat_key] = max(chat_next, now) + self._per_chat_edit_interval
            elif self._per_chat_interval > 0:
                chat_next = self._chat_next_at.get(item.chat_key, 0.0)
                self._chat_next_at[item.chat_key] = max(chat_next, now) + self._per_chat_interval

    def _clear_dedup_if_owner(self, item: _QueueItem) -> None:
        """Remove dedup pointer only when it still points to this request."""
        if not item.dedup_key:
            return
        current = self._pending_edits.get(item.dedup_key)
        if current is item:
            self._pending_edits.pop(item.dedup_key, None)

    @staticmethod
    def _build_edit_dedup_key(endpoint: str, data: dict[str, Any]) -> str | None:
        """Return a dedup key for edit requests to collapse stale updates."""
        if endpoint not in _EDIT_ENDPOINTS:
            return None

        inline_message_id = data.get("inline_message_id")
        if inline_message_id:
            return f"{endpoint}:inline:{inline_message_id}"

        chat_key = _to_chat_key(data.get("chat_id"))
        message_id = data.get("message_id")
        if chat_key is None or message_id is None:
            return None
        return f"{endpoint}:{chat_key}:{message_id}"

    def _resolve_max_retries(self, rate_limit_args: int | None) -> int:
        """Resolve retries from call-level override or limiter default."""
        if rate_limit_args is None:
            return self._max_retries
        return rate_limit_args

    @staticmethod
    def _has_retries_left(current_retries: int, max_retries: int) -> bool:
        """Return True if one more retry is still allowed."""
        return max_retries < 0 or current_retries < max_retries

    def snapshot_metrics(self) -> dict[str, int | float]:
        """Expose queue/retry metrics for dashboards or debugging."""
        return {
            "retry_after_count": self.retry_after_count,
            "max_retry_after_seconds": self.max_retry_after_seconds,
            "queue_length": len(self._queue),
            "queue_peak": self.queue_peak,
            "edit_superseded_count": self.edit_superseded_count,
        }
