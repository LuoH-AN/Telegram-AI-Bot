"""WeChat runtime facade class."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from platforms.wechat.services.runtime import set_wechat_runtime
from platforms.wechat.services.login import get_wechat_login_access_token
from platforms.wechat.services.sdk import WeChatBotAdapter

from ..config import WECHAT_COMMAND_PREFIX, WECHAT_STATE_BASE
from platforms.shared.cache import RecentKeyCache
from .accounts import AccountManager
from .ident import RuntimeIdentMixin
from .login_poll import RuntimeLoginPollMixin
from .login_start import RuntimeLoginStartMixin
from .loop import RuntimeLoopMixin
from .send_file import RuntimeSendFileMixin
from .send_text import RuntimeSendTextMixin
from .snapshot import RuntimeSnapshotMixin
from .typing import RuntimeTypingMixin


class WeChatBotRuntime(
    RuntimeIdentMixin,
    RuntimeSnapshotMixin,
    RuntimeLoginStartMixin,
    RuntimeLoginPollMixin,
    RuntimeTypingMixin,
    RuntimeSendTextMixin,
    RuntimeSendFileMixin,
    RuntimeLoopMixin,
):
    def __init__(self) -> None:
        self._accounts = AccountManager(on_qr_url=self._handle_qr_url)
        self.command_prefix = WECHAT_COMMAND_PREFIX
        self._loop: asyncio.AbstractEventLoop | None = None
        self._typing_lock = asyncio.Lock()
        self._seen_messages = RecentKeyCache(ttl_seconds=15 * 60, max_items=2048)
        self._sent_messages = RecentKeyCache(ttl_seconds=30, max_items=2048)
        self._recent_outbound_fingerprints = RecentKeyCache(ttl_seconds=60, max_items=2048)
        self.login_access_token = get_wechat_login_access_token()
        self._login_state_lock = threading.RLock()
        self._login_snapshot_path = Path(WECHAT_STATE_BASE) / "login_snapshot.json"
        self._active_qr: dict | None = None
        self._login_snapshot = {
            "available": True, "logged_in": False, "status": "idle", "message": "WeChat runtime initialized",
            "user_id": "", "qr_url": "", "access_token_hint": self.login_access_token,
        }
        # The currently-pending login slot id (a `_pending_<n>` key in
        # `_accounts`). Only one interactive login may be active at a time:
        # a second `/login wechat new` cancels the previous pending slot.
        self._pending_login_id: str | None = None
        # Adapter used for outbound sending. Set per-inbound-message to the
        # account that received the message; mixins read `self.client` to
        # send replies/typing/files. ``None`` until the first account logs in.
        self.client: WeChatBotAdapter | None = None
        set_wechat_runtime(self)

    def _handle_qr_url(self, url: str) -> None:
        self._active_qr = {"url": url}
        self._set_login_snapshot(logged_in=False, status="waiting_scan", message="Scan QR to login", user_id="", qr_url=url)

    def set_active_account(self, account_id: str) -> None:
        account = self._accounts.get_account(account_id)
        if account:
            self.client = account.adapter

    def get_account_ids(self) -> list[str]:
        return self._accounts.list_accounts()

    def get_pending_account(self):
        if not self._pending_login_id:
            return None
        return self._accounts.get_account(self._pending_login_id)
