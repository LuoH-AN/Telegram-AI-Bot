"""Async helpers for consuming blocking iterators safely."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import TypeVar

T = TypeVar("T")


async def iter_in_executor(iterator: Iterator[T]) -> AsyncIterator[T]:
    """Yield items from a blocking iterator without blocking the event loop."""
    loop = asyncio.get_event_loop()
    sentinel = object()
    it = iter(iterator)

    while True:
        item = await loop.run_in_executor(None, next, it, sentinel)
        if item is sentinel:
            break
        yield item

