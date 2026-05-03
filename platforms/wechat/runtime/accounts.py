"""Multi-account manager for WeChat runtime.

Each WeChat account (identified by its wxid/user_id) has:
- An independent state_dir under WECHAT_STATE_BASE
- A WeChatBotAdapter instance with its own SDK client
- A dedicated polling loop

Accounts are discovered at startup by scanning state_base subdirectories
that contain valid credentials.json. New accounts can be added via /login.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from ..services.sdk import WeChatBotAdapter
from ..config import WECHAT_STATE_BASE, logger

# Type alias for the message handler callback
MessageHandler = Any  # Callable[[IncomingMessage], Awaitable[None]]


class WeChatAccount:
    """Represents a single logged-in WeChat account."""

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


class AccountManager:
    """Manages multiple WeChat accounts within a single runtime."""

    def __init__(self, on_qr_url: Any | None = None):
        self._accounts: dict[str, WeChatAccount] = {}
        self._lock = asyncio.Lock()
        self._on_qr_url = on_qr_url
        self._discover_existing_accounts()

    def _discover_existing_accounts(self) -> None:
        base = Path(WECHAT_STATE_BASE)
        if not base.exists():
            base.mkdir(parents=True, exist_ok=True)
            return

        for subdir in base.iterdir():
            if not subdir.is_dir():
                continue
            cred_file = subdir / "credentials.json"
            if not cred_file.exists():
                continue
            # Extract account_id from directory name or from credentials
            account_id = subdir.name
            self._accounts[account_id] = WeChatAccount(
                account_id=account_id,
                state_dir=subdir,
                on_qr_url=self._on_qr_url,
            )
            logger.info("Discovered WeChat account: %s", account_id)

    def list_accounts(self) -> list[str]:
        return list(self._accounts.keys())

    def get_account(self, account_id: str) -> WeChatAccount | None:
        return self._accounts.get(account_id)

    def has_accounts(self) -> bool:
        return len(self._accounts) > 0

    async def add_account(self, account_id: str) -> WeChatAccount:
        async with self._lock:
            if account_id in self._accounts:
                return self._accounts[account_id]
            state_dir = Path(WECHAT_STATE_BASE) / account_id
            state_dir.mkdir(parents=True, exist_ok=True)
            account = WeChatAccount(
                account_id=account_id,
                state_dir=state_dir,
                on_qr_url=self._on_qr_url,
            )
            self._accounts[account_id] = account
            logger.info("Added WeChat account: %s", account_id)
            return account

    def remove_account(self, account_id: str) -> bool:
        if account_id not in self._accounts:
            return False
        account = self._accounts.pop(account_id)
        account.stop()
        # Optionally delete state_dir
        logger.info("Removed WeChat account: %s", account_id)
        return True

    def start_all(self, handler: MessageHandler) -> list[asyncio.Task]:
        tasks = []
        for account in self._accounts.values():
            tasks.append(account.start_poll(handler))
        return tasks

    def stop_all(self) -> None:
        for account in self._accounts.values():
            account.stop()