"""Worker loop and throttling decision logic."""

from __future__ import annotations

import asyncio

from .config import EDIT_ENDPOINTS


class RateLimiterWorkerMixin:
    async def _worker_loop(self) -> None:
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

    def _should_delay_for_limits(self, item) -> bool:
        now = asyncio.get_running_loop().time()
        next_allowed = item.ready_at
        if self._overall_interval > 0:
            next_allowed = max(next_allowed, self._global_next_at)
        if item.chat_key is not None:
            if item.endpoint in EDIT_ENDPOINTS:
                if self._per_chat_edit_interval > 0:
                    next_allowed = max(next_allowed, self._chat_edit_next_at.get(item.chat_key, 0.0))
            elif self._per_chat_interval > 0:
                next_allowed = max(next_allowed, self._chat_next_at.get(item.chat_key, 0.0))
        if next_allowed <= now:
            return False
        item.ready_at = next_allowed
        return True
