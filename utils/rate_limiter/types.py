"""Queue item data structures for Telegram rate limiter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass(order=True)
class QueueItem:
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
