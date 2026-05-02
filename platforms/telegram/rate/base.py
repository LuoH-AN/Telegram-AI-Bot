"""Base class with shared state and helpers for queue limiter."""

from __future__ import annotations

import asyncio
import itertools

from telegram.ext import BaseRateLimiter

from .config import EDIT_ENDPOINTS, to_chat_key


class QueuedRateLimiterBase(BaseRateLimiter[int]):
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
            per_chat_time_period / per_chat_max_rate if per_chat_max_rate > 0 and per_chat_time_period > 0 else 0.0
        )
        self._per_chat_edit_interval = (
            self._per_chat_interval
            if per_chat_edit_max_rate is None
            else (
                per_chat_edit_time_period / per_chat_edit_max_rate
                if per_chat_edit_max_rate > 0 and per_chat_edit_time_period > 0
                else 0.0
            )
        )
        self._max_retries = max_retries
        self._retry_jitter = max(0.0, retry_jitter)
        self._queue_warn_threshold = max(1, queue_warn_threshold)
        self._global_next_at = 0.0
        self._chat_next_at: dict[int | str, float] = {}
        self._chat_edit_next_at: dict[int | str, float] = {}
        self._queue = []
        self._pending_edits = {}
        self._condition: asyncio.Condition | None = None
        self._worker: asyncio.Task[None] | None = None
        self._initialized = False
        self._shutdown = False
        self._init_lock = asyncio.Lock()
        self._seq = itertools.count()
        self.retry_after_count = 0
        self.max_retry_after_seconds = 0.0
        self.queue_peak = 0
        self.edit_superseded_count = 0
        self._last_warned_queue = 0

    @staticmethod
    def _build_edit_dedup_key(endpoint: str, data: dict) -> str | None:
        if endpoint not in EDIT_ENDPOINTS:
            return None
        inline_message_id = data.get("inline_message_id")
        if inline_message_id:
            return f"{endpoint}:inline:{inline_message_id}"
        chat_key = to_chat_key(data.get("chat_id"))
        message_id = data.get("message_id")
        if chat_key is None or message_id is None:
            return None
        return f"{endpoint}:{chat_key}:{message_id}"

    def _resolve_max_retries(self, rate_limit_args: int | None) -> int:
        return self._max_retries if rate_limit_args is None else rate_limit_args

    @staticmethod
    def _has_retries_left(current_retries: int, max_retries: int) -> bool:
        return max_retries < 0 or current_retries < max_retries

    def snapshot_metrics(self) -> dict[str, int | float]:
        return {
            "retry_after_count": self.retry_after_count,
            "max_retry_after_seconds": self.max_retry_after_seconds,
            "queue_length": len(self._queue),
            "queue_peak": self.queue_peak,
            "edit_superseded_count": self.edit_superseded_count,
        }
