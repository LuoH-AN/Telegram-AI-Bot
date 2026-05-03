"""Login snapshot state helpers."""

from __future__ import annotations

import json

from ..config import logger


class RuntimeSnapshotMixin:
    def _set_login_snapshot(self, **updates) -> dict:
        with self._login_state_lock:
            snapshot = dict(self._login_snapshot)
            snapshot.update(updates)
            self._login_snapshot = snapshot
            stored = dict(self._login_snapshot)
        try:
            self._login_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self._login_snapshot_path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.debug("Failed to persist WeChat login snapshot", exc_info=True)
        return stored

    def get_login_snapshot(self) -> dict:
        if not self.client:
            with self._login_state_lock:
                snapshot = dict(self._login_snapshot)
            snapshot.update({"logged_in": False, "status": "idle", "message": "No active WeChat account", "user_id": "", "qr_url": ""})
            return snapshot
        state = self.client.state_store.load()
        creds = self.client.get_credentials()
        with self._login_state_lock:
            snapshot = dict(self._login_snapshot)
        if creds:
            snapshot.update({"logged_in": True, "status": "connected", "message": "WeChat is already logged in", "user_id": creds.user_id, "qr_url": ""})
            return snapshot
        if state.token and snapshot.get("logged_in"):
            snapshot.update({"logged_in": True, "status": "connected", "message": "WeChat is already logged in", "user_id": state.user_id, "qr_url": ""})
            return snapshot
        qr_url = self.client.qr_url_cache or ""
        if qr_url:
            snapshot.update(
                {
                    "logged_in": False,
                    "status": "wait",
                    "message": "Scan the QR code directly to log in",
                    "user_id": "",
                    "qr_url": qr_url,
                }
            )
        return snapshot
