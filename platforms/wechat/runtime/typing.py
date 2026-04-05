"""Typing indicator helpers."""

from __future__ import annotations

import asyncio

from ..config import logger


class RuntimeTypingMixin:
    async def safe_send_typing(self, peer_id: str, context_token: str | None, *, status: int) -> None:
        state = self.client.state_store.load()
        if not state.token:
            return
        try:
            config = await asyncio.to_thread(self.client.get_config, state.token, peer_id, context_token=context_token)
            ticket = str(config.get("typing_ticket") or "").strip()
            if not ticket:
                return
            await asyncio.to_thread(self.client.send_typing, state.token, peer_id, ticket, status=status)
        except Exception:
            logger.debug("Failed to update WeChat typing indicator", exc_info=True)

    async def _typing_loop(self, peer_id: str, context_token: str | None, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self.safe_send_typing(peer_id, context_token, status=1)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=4)
            except asyncio.TimeoutError:
                continue
        await self.safe_send_typing(peer_id, context_token, status=2)
