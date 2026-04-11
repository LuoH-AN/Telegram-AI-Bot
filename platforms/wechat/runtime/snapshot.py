"""Login snapshot state helpers."""

from __future__ import annotations

import json

from ..config import logger


class RuntimeSnapshotMixin:
    def _build_login_page_url(self) -> str:
        from config import WEB_BASE_URL
        return f"{WEB_BASE_URL.rstrip('/')}/wechat/login?access={self.login_access_token}"

    def _build_login_image_url(self) -> str:
        from config import WEB_BASE_URL
        return f"{WEB_BASE_URL.rstrip('/')}/wechat/login/qr?access={self.login_access_token}"

    def _set_login_snapshot(self, **updates) -> dict:
        with self._login_state_lock:
            snapshot = dict(self._login_snapshot)
            snapshot.update(updates)
            snapshot["page_url"] = self._build_login_page_url()
            snapshot["public_image_url"] = self._build_login_image_url()
            self._login_snapshot = snapshot
            stored = dict(self._login_snapshot)
        try:
            self._login_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self._login_snapshot_path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.debug("Failed to persist WeChat login snapshot", exc_info=True)
        return stored

    def get_login_snapshot(self) -> dict:
        state = self.client.state_store.load()
        creds = self.client.get_credentials()
        with self._login_state_lock:
            snapshot = dict(self._login_snapshot)
        if creds:
            snapshot.update({"logged_in": True, "status": "connected", "message": "WeChat 已登录", "user_id": creds.user_id, "qr_url": ""})
            return snapshot
        if state.token and snapshot.get("logged_in"):
            snapshot.update({"logged_in": True, "status": "connected", "message": "WeChat 已登录", "user_id": state.user_id, "qr_url": ""})
            return snapshot
        qr_url = self.client.qr_url_cache or ""
        if qr_url:
            snapshot.update(
                {
                    "logged_in": False,
                    "status": "wait",
                    "message": "请打开页面链接或图片链接扫码登录",
                    "user_id": "",
                    "qr_url": qr_url,
                }
            )
        return snapshot
