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
        """Build a fresh login snapshot.

        Priority:
        1. If an interactive login is in flight (pending slot), reflect its
           state — fresh QR if available, "pending" otherwise. Stale QR
           URLs from a finished session are NOT served.
        2. Else if any account is logged in, report ``connected``.
        3. Else report ``idle``.
        """
        with self._login_state_lock:
            base = dict(self._login_snapshot)

        pending = self.get_pending_account()
        if pending is not None:
            adapter = pending.adapter
            if adapter.login_in_progress:
                qr_url = adapter.qr_url_cache or ""
                base.update({
                    "logged_in": False,
                    "status": "wait" if qr_url else "pending",
                    "message": (
                        "Scan the QR code to log in" if qr_url
                        else "Fetching a fresh QR code..."
                    ),
                    "user_id": "",
                    "qr_url": qr_url,
                })
                return base
            # Pending slot exists but login coroutine has finished. The
            # promote/discard handler in login_start clears _pending_login_id
            # before we get here under normal flow; if we're racing, treat
            # the slot as not-yet-promoted and keep the old snapshot.

        # No active interactive login. Report whether any real account is
        # currently logged in.
        first = self._accounts.first_logged_in()
        if first is not None:
            creds = first.adapter.get_credentials()
            user_id = (creds.user_id if creds else first.account_id)
            base.update({
                "logged_in": True,
                "status": "connected",
                "message": "WeChat is already logged in",
                "user_id": user_id,
                "qr_url": "",
            })
            return base

        base.update({
            "logged_in": False,
            "status": "idle",
            "message": "No active WeChat account",
            "user_id": "",
            "qr_url": "",
        })
        return base
