"""Queued Telegram rate limiter with RetryAfter requeue support."""

from .queued import QueuedRateLimiter

__all__ = ["QueuedRateLimiter"]
