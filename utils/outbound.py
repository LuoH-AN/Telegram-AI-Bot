"""Unified outbound adapter for streaming and final text delivery."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class StreamOutboundAdapter:
    """Platform-agnostic outbound helper used by Telegram/Discord renderers."""

    def __init__(
        self,
        *,
        max_message_length: int,
        has_placeholder: Callable[[], bool],
        edit_placeholder: Callable[[str], Awaitable[bool]],
        send_text: Callable[[str], Awaitable[bool]],
        delete_placeholder: Callable[[], Awaitable[None]],
        empty_placeholder_text: str = "Thinking...",
    ):
        self.max_message_length = max_message_length
        self._has_placeholder = has_placeholder
        self._edit_placeholder = edit_placeholder
        self._send_text = send_text
        self._delete_placeholder = delete_placeholder
        self._empty_placeholder_text = empty_placeholder_text
        self.stream_attempts = 0
        self.stream_successes = 0

    async def stream_update(self, text: str) -> bool:
        """Apply one streaming/status update to the placeholder message."""
        self.stream_attempts += 1
        if not self._has_placeholder():
            return False
        safe_text = (text or "").rstrip() or self._empty_placeholder_text
        ok = await self._edit_placeholder(safe_text)
        if ok:
            self.stream_successes += 1
        return ok

    async def deliver_final(self, text: str) -> bool:
        """Deliver final response with edit-first, send-fallback semantics."""
        safe_text = (text or "").rstrip() or "(Empty response)"
        if len(safe_text) > self.max_message_length:
            if self._has_placeholder():
                await self._safe_delete_placeholder()
            return await self._send_text(safe_text)

        if self._has_placeholder():
            edited = await self._edit_placeholder(safe_text)
            if edited:
                return True
            await self._safe_delete_placeholder()

        return await self._send_text(safe_text)

    async def _safe_delete_placeholder(self) -> None:
        try:
            await self._delete_placeholder()
        except Exception:
            logger.debug("Failed to delete placeholder message", exc_info=True)
