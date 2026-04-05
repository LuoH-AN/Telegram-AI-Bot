"""Async QR login poll loop."""

from __future__ import annotations

import asyncio

from ..config import logger


class RuntimeLoginPollMixin:
    async def login(self) -> None:
        state = self.client.state_store.load()
        if state.token:
            self._set_login_snapshot(logged_in=True, status="connected", message="WeChat 已登录", user_id=state.user_id, qr_url="")
            return

        while True:
            with self._login_state_lock:
                active_qr = dict(self._active_qr) if self._active_qr else None
            if not active_qr:
                try:
                    await asyncio.to_thread(self._start_login_session_sync)
                except Exception:
                    logger.exception("Failed to start WeChat QR login session")
                    self._set_login_snapshot(logged_in=False, status="error", message="二维码生成失败，请稍后重试", user_id="", qr_url="")
                    await asyncio.sleep(5)
                    continue
                with self._login_state_lock:
                    active_qr = dict(self._active_qr) if self._active_qr else None
                if not active_qr:
                    await asyncio.sleep(1)
                    continue

            status = await asyncio.to_thread(self.client.poll_qr_status, active_qr["qrcode"])
            status_value = str(status.get("status") or "wait")
            if status_value == "scaned":
                self._set_login_snapshot(logged_in=False, status="scaned", message="已扫码，请在微信中确认授权", user_id="", qr_url=active_qr["qr_url"])
            elif status_value == "confirmed" and status.get("bot_token"):
                current = self.client.state_store.load()
                current.token = str(status.get("bot_token") or "")
                current.user_id = str(status.get("ilink_user_id") or "")
                current.base_url = str(status.get("baseurl") or current.base_url or self.client.base_url)
                current.get_updates_buf = ""
                self.client.state_store.save(current)
                with self._login_state_lock:
                    self._active_qr = None
                self._set_login_snapshot(logged_in=True, status="connected", message="WeChat 登录成功", user_id=current.user_id, qr_url="")
                logger.info("WeChat login confirmed for user %s", current.user_id or "(unknown)")
                return
            elif status_value == "expired":
                logger.info("WeChat QR expired, refreshing login QR")
                try:
                    await asyncio.to_thread(self._start_login_session_sync, force=True)
                except Exception:
                    logger.exception("Failed to refresh WeChat QR login session")
                    self._set_login_snapshot(logged_in=False, status="error", message="二维码刷新失败，请稍后重试", user_id="", qr_url="")
                    await asyncio.sleep(5)
                continue
            else:
                self._set_login_snapshot(logged_in=False, status="wait", message="等待扫码中", user_id="", qr_url=active_qr["qr_url"])
            await asyncio.sleep(2)
