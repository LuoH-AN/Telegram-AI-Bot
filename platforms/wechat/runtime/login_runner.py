"""Background login coroutine driver for the pending slot.

Lives separately from ``login_start.py`` so each module stays under the
120-line limit. Provides ``LoginRunnerMixin`` with the helpers used by
``RuntimeLoginStartMixin`` to spawn / cancel / promote pending logins.
"""

from __future__ import annotations

import asyncio

from ..config import logger


def make_pending_snapshot(adapter, set_snapshot) -> dict:
    qr_url = adapter.qr_url_cache or ""
    return set_snapshot(
        logged_in=False,
        status="wait" if qr_url else "pending",
        message="Scan the QR code to log in" if qr_url else "Fetching a fresh QR code...",
        user_id="",
        qr_url=qr_url,
    )


class LoginRunnerMixin:
    def _cancel_pending_login(self) -> None:
        if not self._pending_login_id:
            return
        pending_id = self._pending_login_id
        self._pending_login_id = None
        try:
            self._accounts.discard_pending(pending_id)
        except Exception:
            logger.exception("Failed to discard pending login slot %s", pending_id)

    def _spawn_pending_login_account(self):
        loop = self._loop
        if loop is None or not loop.is_running():
            raise RuntimeError("WeChat runtime loop is not running yet")
        # add_pending is async; run it on the loop from this worker thread.
        future = asyncio.run_coroutine_threadsafe(self._accounts.add_pending(), loop)
        account = future.result(timeout=5)
        self._pending_login_id = account.account_id
        return account

    def _kick_login_coroutine(self, account) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        task = loop.create_task(self._login_runner(account))
        account.adapter.set_login_task(task)

    async def _login_runner(self, account):
        adapter = account.adapter
        try:
            payload = await adapter.login(force=True)
        except asyncio.CancelledError:
            logger.info("Pending WeChat login %s was cancelled", account.account_id)
            return
        except Exception as exc:
            logger.exception("Pending WeChat login %s failed: %s", account.account_id, exc)
            self._set_login_snapshot(
                logged_in=False, status="error", message=f"Login failed: {exc}",
                user_id="", qr_url="",
            )
            if self._pending_login_id == account.account_id:
                self._pending_login_id = None
            self._accounts.discard_pending(account.account_id)
            return

        wxid = str(payload.get("ilink_user_id") or "").strip()
        if not wxid:
            logger.error("Pending login %s succeeded but returned no wxid", account.account_id)
            self._accounts.discard_pending(account.account_id)
            if self._pending_login_id == account.account_id:
                self._pending_login_id = None
            return

        promoted = self._accounts.promote_pending(account.account_id, wxid)
        if self._pending_login_id == account.account_id:
            self._pending_login_id = None
        self._ensure_account_polling(promoted)
        if self.client is None:
            self.client = promoted.adapter
        self._set_login_snapshot(
            logged_in=True, status="connected",
            message="WeChat login succeeded", user_id=wxid, qr_url="",
        )
        logger.info("WeChat login confirmed for user %s", wxid)

    def _ensure_account_polling(self, account) -> None:
        existing = getattr(account, "_poll_task", None)
        if existing and not existing.done():
            return
        handler = getattr(self, "_dispatcher", None)
        if handler is None:
            return
        self._accounts.start_one(account.account_id, handler)
