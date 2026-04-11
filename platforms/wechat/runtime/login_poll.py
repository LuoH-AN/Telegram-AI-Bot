"""Async login lifecycle.

Uses the SDK's login() method directly. The SDK handles QR polling
internally; we just call login() and wait for credentials.
The QR URL is captured via the adapter's on_qr_url callback.
"""

from __future__ import annotations

from ..config import logger


class RuntimeLoginPollMixin:
    async def login(self, *, force: bool = False) -> None:
        creds = self.client.get_credentials()
        if creds and not force:
            self.client.state_store.update_credentials(
                token=creds.token,
                user_id=creds.user_id,
                base_url=creds.base_url,
            )
            self._set_login_snapshot(logged_in=True, status="connected", message="WeChat 已登录", user_id=creds.user_id, qr_url="")
            return

        self._set_login_snapshot(
            logged_in=False,
            status="pending",
            message="正在获取登录二维码...",
            user_id="",
            qr_url=self.client.qr_url_cache or "",
        )
        try:
            payload = await self.client.login(force=force)
        except Exception:
            logger.exception("WeChat login failed")
            self._set_login_snapshot(
                logged_in=False,
                status="error",
                message="登录失败，5秒后重试...",
                user_id="",
                qr_url=self.client.qr_url_cache or "",
            )
            raise

        with self._login_state_lock:
            self._active_qr = None
        self._set_login_snapshot(
            logged_in=True,
            status="connected",
            message="WeChat 登录成功",
            user_id=str(payload.get("ilink_user_id") or ""),
            qr_url="",
        )
        logger.info("WeChat login confirmed for user %s", payload.get("ilink_user_id") or "(unknown)")
