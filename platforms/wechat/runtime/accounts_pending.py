"""Pending login slot lifecycle (mixin for AccountManager).

Pending slots are temporary directories under WECHAT_STATE_BASE used while
a user is interactively scanning a QR code. After the SDK confirms the
login, ``promote_pending`` renames the slot to the real wxid; on cancel
``discard_pending`` cleans up.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .account import PENDING_PREFIX, WeChatAccount
from .accounts_db import delete_db_account_row, migrate_db_account_key
from ..config import WECHAT_STATE_BASE, logger


class PendingMixin:
    async def add_pending(self) -> WeChatAccount:
        async with self._lock:
            base = Path(WECHAT_STATE_BASE)
            base.mkdir(parents=True, exist_ok=True)
            n = 1
            while (base / f"{PENDING_PREFIX}{n}").exists() or f"{PENDING_PREFIX}{n}" in self._accounts:
                n += 1
            pending_id = f"{PENDING_PREFIX}{n}"
            state_dir = base / pending_id
            state_dir.mkdir(parents=True, exist_ok=True)
            account = WeChatAccount(
                account_id=pending_id,
                state_dir=state_dir,
                on_qr_url=self._on_qr_url,
            )
            self._accounts[pending_id] = account
            logger.info("Created pending WeChat login slot: %s", pending_id)
            return account

    def discard_pending(self, pending_id: str) -> None:
        if not pending_id.startswith(PENDING_PREFIX):
            return
        account = self._accounts.pop(pending_id, None)
        if not account:
            return
        account.stop()
        try:
            account.adapter.cancel_login()
        except Exception:
            logger.exception("Failed to cancel pending login %s", pending_id)
        shutil.rmtree(account.state_dir, ignore_errors=True)
        delete_db_account_row(pending_id)
        logger.info("Discarded pending WeChat login slot: %s", pending_id)

    def promote_pending(self, pending_id: str, wxid: str) -> WeChatAccount:
        if not pending_id.startswith(PENDING_PREFIX):
            raise ValueError(f"Not a pending account: {pending_id}")
        account = self._accounts.pop(pending_id, None)
        if not account:
            raise KeyError(pending_id)
        if wxid in self._accounts:
            existing = self._accounts[wxid]
            existing.adapter.adopt_credentials_from(account.adapter)
            account.stop()
            shutil.rmtree(account.state_dir, ignore_errors=True)
            delete_db_account_row(pending_id)
            logger.info("Re-logged-in existing account %s via pending %s", wxid, pending_id)
            return existing

        new_dir = Path(WECHAT_STATE_BASE) / wxid
        try:
            if new_dir.exists():
                shutil.rmtree(new_dir)
            account.state_dir.rename(new_dir)
        except OSError:
            new_dir.mkdir(parents=True, exist_ok=True)
            cred = account.state_dir / "credentials.json"
            if cred.exists():
                shutil.copy2(cred, new_dir / "credentials.json")
            shutil.rmtree(account.state_dir, ignore_errors=True)
        migrate_db_account_key(pending_id, wxid)
        account.relabel(wxid, new_dir)
        self._accounts[wxid] = account
        logger.info("Promoted pending login %s -> %s", pending_id, wxid)
        return account
