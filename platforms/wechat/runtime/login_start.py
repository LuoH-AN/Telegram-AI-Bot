"""Login session bootstrap helpers.

Bridges the SDK's QR-based login to the runtime's snapshot/lock model.
The SDK handles QR fetching internally; we capture the QR URL via the
on_qr_url callback and expose it through the login snapshot.
"""

from __future__ import annotations

import asyncio

from ..config import logger


class RuntimeLoginStartMixin:
    def _start_login_session_sync(self, *, force: bool = False) -> dict:
        if force:
            self.client.reset(clear_credentials=True, clear_mappings=True)
        state = self.client.state_store.load()
        creds = self.client.get_credentials()
        if creds and not force:
            return self._set_login_snapshot(
                logged_in=True,
                status="connected",
                message="WeChat is already logged in",
                user_id=creds.user_id,
                qr_url="",
            )
        if state.token and not force:
            return self._set_login_snapshot(
                logged_in=True,
                status="connected",
                message="WeChat is already logged in",
                user_id=state.user_id,
                qr_url="",
            )

        qr_url = self.client.qr_url_cache or ""
        snapshot = self._set_login_snapshot(
            logged_in=False,
            status="wait" if qr_url else "pending",
            message="Scan the QR code directly to log in" if qr_url else "Switching account and waiting for a new QR code...",
            user_id="",
            qr_url=qr_url,
        )
        if force:
            loop = self._loop
            if loop and loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(self.login(force=True), loop)
                except Exception:
                    logger.exception("Failed to trigger forced WeChat re-login")
        logger.info("WeChat login status prepared: status=%s qr_ready=%s", snapshot.get("status"), bool(qr_url))
        return snapshot

    def force_new_login_sync(self) -> dict:
        with self._login_state_lock:
            self._active_qr = None
        return self._start_login_session_sync(force=True)
