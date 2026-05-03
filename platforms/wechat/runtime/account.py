"""WeChatAccount: a single account slot (logged-in or pending)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..services.sdk import WeChatBotAdapter
from ..config import logger

MessageHandler = Any  # Callable[[IncomingMessage], Awaitable[None]]

PENDING_PREFIX = "_pending_"


class WeChatAccount:
    def __init__(
        self,
        *,
        account_id: str,
        state_dir: Path,
        on_qr_url: Any | None = None,
    ):
        self.account_id = account_id
        self.state_dir = state_dir
        self.adapter = WeChatBotAdapter(
            account_id=account_id,
            state_dir=state_dir,
            on_qr_url=on_qr_url,
        )
        self._poll_task: asyncio.Task | None = None
        self._running = False

    @property
    def logged_in(self) -> bool:
        return self.adapter.get_credentials() is not None

    @property
    def is_pending(self) -> bool:
        return self.account_id.startswith(PENDING_PREFIX)

    def relabel(self, new_id: str, new_state_dir: Path) -> None:
        self.account_id = new_id
        self.state_dir = new_state_dir
        self.adapter.relabel(new_id, new_state_dir)

    def start_poll(self, handler: MessageHandler) -> asyncio.Task:
        self.adapter.on_message(handler)
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        return self._poll_task

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                if not self.logged_in:
                    await asyncio.sleep(5)
                    continue
                await self.adapter.start_polling()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("WeChat account %s poll error", self.account_id)
                await asyncio.sleep(5)

    def stop(self) -> None:
        self._running = False
        self.adapter.stop()
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
