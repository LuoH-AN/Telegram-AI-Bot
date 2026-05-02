"""RetryAfter and direct-call retry logic mixin."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Callable, Coroutine

from telegram.error import RetryAfter

from .config import EDIT_ENDPOINTS

logger = logging.getLogger(__name__)


class RateLimiterRetryMixin:
    async def _handle_retry_after(self, item, exc: RetryAfter) -> None:
        retry_after = float(getattr(exc, "retry_after", 0.0) or 0.0)
        self.retry_after_count += 1
        self.max_retry_after_seconds = max(self.max_retry_after_seconds, retry_after)
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
        if item.chat_key is not None:
            if item.endpoint in EDIT_ENDPOINTS:
                self._chat_edit_next_at[item.chat_key] = max(self._chat_edit_next_at.get(item.chat_key, 0.0), item.ready_at)
            else:
                self._chat_next_at[item.chat_key] = max(self._chat_next_at.get(item.chat_key, 0.0), item.ready_at)
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
        attempts = 0
        while True:
            try:
                return await callback(*args, **kwargs)
            except RetryAfter as exc:
                retry_after = float(getattr(exc, "retry_after", 0.0) or 0.0)
                self.retry_after_count += 1
                self.max_retry_after_seconds = max(self.max_retry_after_seconds, retry_after)
                if not self._has_retries_left(attempts, max_retries):
                    raise
                attempts += 1
                logger.warning(
                    "Telegram RetryAfter on %s (direct), retry=%d/%s, wait=%.2fs",
                    endpoint,
                    attempts,
                    "inf" if max_retries < 0 else str(max_retries),
                    retry_after,
                )
                await asyncio.sleep(retry_after + random.uniform(0, self._retry_jitter))
