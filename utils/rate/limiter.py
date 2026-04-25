"""Concrete queued Telegram rate limiter."""

from __future__ import annotations

from .base import QueuedRateLimiterBase
from .dispatch import RateLimiterDispatchMixin
from .lifecycle import RateLimiterLifecycleMixin
from .queue import RateLimiterQueueMixin
from .retry import RateLimiterRetryMixin
from .worker import RateLimiterWorkerMixin


class QueuedRateLimiter(
    RateLimiterLifecycleMixin,
    RateLimiterQueueMixin,
    RateLimiterWorkerMixin,
    RateLimiterRetryMixin,
    RateLimiterDispatchMixin,
    QueuedRateLimiterBase,
):
    """Queue-based rate limiter for Telegram API write operations."""

