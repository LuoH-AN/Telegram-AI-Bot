"""Async login lifecycle (legacy entry point).

The interactive login flow is now driven through ``login_start``: callers
should use ``runtime.force_new_login_sync()`` (POST /api/wechat/login/new)
or check ``runtime.get_login_snapshot()`` (GET /api/wechat/login).

This module remains for backward-compat callers that invoke
``runtime.login()`` directly. It just delegates to the pending-slot driver.
"""

from __future__ import annotations

from ..config import logger


class RuntimeLoginPollMixin:
    async def login(self, *, force: bool = False) -> None:
        """Drive an interactive QR login.

        - ``force=False``: if any account is already logged in, this is a
          no-op. Otherwise it spawns a pending login slot and waits until
          the SDK either confirms or fails.
        - ``force=True``: always spawn a fresh pending login slot.
        """
        if not force:
            existing = self._accounts.first_logged_in()
            if existing is not None:
                creds = existing.adapter.get_credentials()
                self._set_login_snapshot(
                    logged_in=True,
                    status="connected",
                    message="WeChat is already logged in",
                    user_id=str(creds.user_id if creds else existing.account_id),
                    qr_url="",
                )
                return

        # Cancel any prior pending slot then spin up a new one.
        self._cancel_pending_login()
        account = self._spawn_pending_login_account()
        try:
            payload = await account.adapter.login(force=True)
        except Exception:
            logger.exception("WeChat login failed")
            self._accounts.discard_pending(account.account_id)
            if self._pending_login_id == account.account_id:
                self._pending_login_id = None
            self._set_login_snapshot(
                logged_in=False,
                status="error",
                message="Login failed. Retry in 5 seconds.",
                user_id="",
                qr_url="",
            )
            raise

        wxid = str(payload.get("ilink_user_id") or "").strip()
        if wxid:
            promoted = self._accounts.promote_pending(account.account_id, wxid)
            if self._pending_login_id == account.account_id:
                self._pending_login_id = None
            if self.client is None:
                self.client = promoted.adapter
            self._ensure_account_polling(promoted)

        with self._login_state_lock:
            self._active_qr = None
        self._set_login_snapshot(
            logged_in=True,
            status="connected",
            message="WeChat login succeeded",
            user_id=wxid,
            qr_url="",
        )
        logger.info("WeChat login confirmed for user %s", wxid or "(unknown)")
