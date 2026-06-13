"""Outbound media sender contextvar — bridges sync plugins to async send APIs."""

from __future__ import annotations

import asyncio
import contextvars
from abc import ABC, abstractmethod
from dataclasses import dataclass


class OutboundSender(ABC):
    """Per-message handle that plugins use to push media back to the user."""

    @abstractmethod
    async def send_image(self, data: bytes, *, filename: str, caption: str = "") -> None: ...

    @abstractmethod
    async def send_document(self, data: bytes, *, filename: str, caption: str = "") -> None: ...

    @abstractmethod
    async def send_voice(self, data: bytes, *, filename: str, caption: str = "") -> None: ...

    @abstractmethod
    async def send_video(self, data: bytes, *, filename: str, caption: str = "") -> None: ...


@dataclass
class OutboundBinding:
    sender: OutboundSender
    loop: asyncio.AbstractEventLoop


_current: contextvars.ContextVar[OutboundBinding | None] = contextvars.ContextVar(
    "current_outbound", default=None
)


def bind_outbound(sender: OutboundSender, loop: asyncio.AbstractEventLoop | None = None):
    """Set the active outbound for this task. Returns a token for reset()."""
    loop = loop or asyncio.get_event_loop()
    return _current.set(OutboundBinding(sender=sender, loop=loop))


def reset_outbound(token) -> None:
    _current.reset(token)


def get_outbound() -> OutboundBinding | None:
    return _current.get()


def _kind_to_coro(binding: OutboundBinding, kind: str, data: bytes, filename: str, caption: str):
    sender = binding.sender
    if kind == "image":
        return sender.send_image(data, filename=filename, caption=caption)
    if kind == "voice":
        return sender.send_voice(data, filename=filename, caption=caption)
    if kind == "video":
        return sender.send_video(data, filename=filename, caption=caption)
    return sender.send_document(data, filename=filename, caption=caption)


def send_sync(kind: str, data: bytes, *, filename: str, caption: str = "", timeout: float = 60.0) -> None:
    """Sync entry point used by plugin code (runs in thread pool)."""
    binding = get_outbound()
    if binding is None:
        raise RuntimeError("No outbound bound — send_file can only be used during a chat reply")
    coro = _kind_to_coro(binding, kind, data, filename, caption)
    future = asyncio.run_coroutine_threadsafe(coro, binding.loop)
    future.result(timeout=timeout)
