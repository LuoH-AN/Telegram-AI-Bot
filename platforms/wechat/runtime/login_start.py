"""Login session bootstrap helpers."""

from __future__ import annotations

import time

from ..config import logger


class RuntimeLoginStartMixin:
    def _start_login_session_sync(self, *, force: bool = False) -> dict:
        current = self.client.state_store.load()
        if force:
            current.token = ""
            current.user_id = ""
            current.get_updates_buf = ""
            current.peer_map = {}
            current.context_tokens = {}
            self.client.state_store.save(current)
        elif current.token:
            return self._set_login_snapshot(
                logged_in=True,
                status="connected",
                message="WeChat 已登录",
                user_id=current.user_id,
                qr_url="",
            )

        qr = self.client.fetch_qr_code()
        qrcode = str(qr.get("qrcode") or "").strip()
        qrcode_url = str(qr.get("qrcode_img_content") or "").strip()
        if not qrcode or not qrcode_url:
            raise RuntimeError(f"Failed to fetch WeChat QR code: {qr}")
        with self._login_state_lock:
            self._active_qr = {"qrcode": qrcode, "qr_url": qrcode_url, "started_at": time.time(), "status": "wait"}
        snapshot = self._set_login_snapshot(
            logged_in=False,
            status="wait",
            message="请打开页面链接或图片链接扫码登录",
            user_id="",
            qr_url=qrcode_url,
        )
        logger.info("WeChat login page: %s", snapshot["page_url"])
        logger.info("WeChat QR image link: %s", snapshot["public_image_url"])
        logger.info("WeChat upstream QR URL: %s", qrcode_url)
        return snapshot

    def force_new_login_sync(self) -> dict:
        with self._login_state_lock:
            self._active_qr = None
        return self._start_login_session_sync(force=True)
