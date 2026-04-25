"""Dispatch and successful window advancement mixin."""

from __future__ import annotations

import asyncio

from telegram.error import RetryAfter

from .config import EDIT_ENDPOINTS


class RateLimiterDispatchMixin:
    async def _dispatch_item(self, item) -> None:
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

    def _advance_windows(self, item) -> None:
        now = asyncio.get_running_loop().time()
        if self._overall_interval > 0:
            self._global_next_at = max(self._global_next_at, now) + self._overall_interval
        if item.chat_key is None:
            return
        if item.endpoint in EDIT_ENDPOINTS:
            if self._per_chat_edit_interval > 0:
                chat_next = self._chat_edit_next_at.get(item.chat_key, 0.0)
                self._chat_edit_next_at[item.chat_key] = max(chat_next, now) + self._per_chat_edit_interval
        elif self._per_chat_interval > 0:
            chat_next = self._chat_next_at.get(item.chat_key, 0.0)
            self._chat_next_at[item.chat_key] = max(chat_next, now) + self._per_chat_interval

    def _clear_dedup_if_owner(self, item) -> None:
        if not item.dedup_key:
            return
        current = self._pending_edits.get(item.dedup_key)
        if current is item:
            self._pending_edits.pop(item.dedup_key, None)
