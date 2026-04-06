"""Async event queue primitives for chat stream rendering."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable


@dataclass(slots=True)
class ChatRenderEvent:
    """A structured render event produced by chat execution."""

    kind: str
    text: str
    created_at: float = field(default_factory=time.monotonic)


class ChatEventPump:
    """Single-consumer async queue for rendering chat events."""

    def __init__(self, render_func: Callable[[ChatRenderEvent], Awaitable[bool | None]]):
        self._render_func = render_func
        self._queue: asyncio.Queue[ChatRenderEvent | None] = asyncio.Queue()
        self._runner_task: asyncio.Task | None = None
        self._last_rendered_text: str | None = None

    def start(self) -> None:
        """Start the background render worker."""
        if self._runner_task is not None:
            return
        self._runner_task = asyncio.create_task(self._runner(), name="chat-event-pump")

    async def emit(self, kind: str, text: str) -> bool:
        """Queue an event for rendering."""
        if self._runner_task is None:
            self.start()
        await self._queue.put(ChatRenderEvent(kind=kind, text=text))
        return True

    def emit_threadsafe(self, loop: asyncio.AbstractEventLoop, kind: str, text: str) -> None:
        """Queue an event from a non-event-loop thread."""

        def _put_now() -> None:
            self._queue.put_nowait(ChatRenderEvent(kind=kind, text=text))

        loop.call_soon_threadsafe(_put_now)

    async def drain(self) -> None:
        """Wait until all queued events are rendered."""
        await self._queue.join()

    async def stop(self) -> None:
        """Stop the render worker after draining queued events."""
        if self._runner_task is None:
            return
        await self._queue.join()
        await self._queue.put(None)
        await self._runner_task
        self._runner_task = None

    def force_stop(self) -> None:
        """Immediately cancel the render worker without draining."""
        if self._runner_task is not None:
            self._runner_task.cancel()
            self._runner_task = None

    async def _runner(self) -> None:
        while True:
            event = await self._queue.get()
            if event is None:
                self._queue.task_done()
                break
            try:
                # Deduplicate identical edits to reduce platform API pressure.
                text = (event.text or "").rstrip() or "Thinking..."
                if text != self._last_rendered_text:
                    rendered = await self._render_func(ChatRenderEvent(kind=event.kind, text=text, created_at=event.created_at))
                    if rendered is not False:
                        self._last_rendered_text = text
            finally:
                self._queue.task_done()
