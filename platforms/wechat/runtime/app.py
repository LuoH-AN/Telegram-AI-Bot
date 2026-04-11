"""WeChat runtime facade class."""

from __future__ import annotations

import asyncio
import secrets
import threading
from pathlib import Path

from services.wechat.runtime import set_wechat_runtime
from services.wechat.sdk import WeChatBotAdapter

from ..config import WECHAT_COMMAND_PREFIX, WECHAT_LOGIN_ACCESS_TOKEN, WECHAT_STATE_DIR
from ..recent_cache import RecentKeyCache
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
        self.client = WeChatBotAdapter(state_dir=WECHAT_STATE_DIR)
        self.command_prefix = WECHAT_COMMAND_PREFIX
        self._loop: asyncio.AbstractEventLoop | None = None
        self._typing_lock = asyncio.Lock()
        self._seen_messages = RecentKeyCache(ttl_seconds=15 * 60, max_items=2048)
        self._sent_messages = RecentKeyCache(ttl_seconds=30, max_items=2048)
        self._recent_outbound_fingerprints = RecentKeyCache(ttl_seconds=60, max_items=2048)
        self.login_access_token = WECHAT_LOGIN_ACCESS_TOKEN or secrets.token_urlsafe(24)
        self._login_state_lock = threading.RLock()
        self._login_snapshot_path = Path(WECHAT_STATE_DIR) / "login_snapshot.json"
        self._active_qr: dict | None = None
        self._login_snapshot = {
            "available": True, "logged_in": False, "status": "idle", "message": "WeChat runtime initialized",
            "user_id": "", "qr_url": "", "page_url": self._build_login_page_url(),
            "public_image_url": self._build_login_image_url(), "access_token_hint": self.login_access_token,
        }
        set_wechat_runtime(self)
