"""Multi-account manager for WeChat runtime.

Each WeChat account is keyed by its wxid. An account owns a state
directory under ``WECHAT_STATE_BASE``, a :class:`WeChatBotAdapter`
instance, and a long-poll task. Pending login slots are managed via the
``PendingMixin`` (see ``accounts_pending.py``); discovery on startup is
in ``accounts_discover.py``.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from .account import PENDING_PREFIX, MessageHandler, WeChatAccount
from .accounts_db import delete_db_account_row
from .accounts_discover import discover_existing_accounts
from .accounts_pending import PendingMixin
from ..config import logger


class AccountManager(PendingMixin):
    def __init__(self, on_qr_url: Any | None = None):
        self._on_qr_url = on_qr_url
        self._accounts: dict[str, WeChatAccount] = discover_existing_accounts(on_qr_url)
        self._lock = asyncio.Lock()

    # ── queries ───────────────────────────────────────────────────────

    def list_accounts(self) -> list[str]:
        return [aid for aid in self._accounts.keys() if not aid.startswith(PENDING_PREFIX)]

    def list_pending(self) -> list[str]:
        return [aid for aid in self._accounts.keys() if aid.startswith(PENDING_PREFIX)]

    def get_account(self, account_id: str) -> WeChatAccount | None:
        return self._accounts.get(account_id)

    def has_logged_in_accounts(self) -> bool:
        return any(acc.logged_in for acc in self._accounts.values() if not acc.is_pending)

    def first_logged_in(self) -> WeChatAccount | None:
        for acc in self._accounts.values():
            if not acc.is_pending and acc.logged_in:
                return acc
        return None

    # ── lifecycle ─────────────────────────────────────────────────────

    def remove_account(self, account_id: str, *, delete_state: bool = True) -> bool:
        if account_id not in self._accounts:
            return False
        account = self._accounts.pop(account_id)
        account.stop()
        if delete_state:
            shutil.rmtree(account.state_dir, ignore_errors=True)
            delete_db_account_row(account_id)
        logger.info("Removed WeChat account: %s", account_id)
        return True

    def start_all(self, handler: MessageHandler) -> list[asyncio.Task]:
        tasks = []
        for account in self._accounts.values():
            if account.is_pending:
                continue
            tasks.append(account.start_poll(handler))
        return tasks

    def start_one(self, account_id: str, handler: MessageHandler) -> asyncio.Task | None:
        account = self._accounts.get(account_id)
        if account is None or account.is_pending:
            return None
        return account.start_poll(handler)

    def stop_all(self) -> None:
        for account in self._accounts.values():
            account.stop()
