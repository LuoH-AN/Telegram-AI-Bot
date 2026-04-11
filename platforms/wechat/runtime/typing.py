"""Typing indicator helpers.

Delegates to the wechatbot-sdk's send_typing/stop_typing methods.
"""

from __future__ import annotations

import asyncio

from ..config import logger


class RuntimeTypingMixin:
    async def safe_send_typing(self, peer_id: str, context_token: str | None, *, status: int) -> None:
        state = self.client.state_store.load()
        if not (state.token or self.client.get_credentials()):
            return
        try:
            if status == 1:
                await self.client.send_typing(peer_id, context_token=context_token)
            else:
                await self.client.stop_typing(peer_id, context_token=context_token)
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
