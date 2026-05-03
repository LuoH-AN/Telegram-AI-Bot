"""Adapter wrapping wechatbot-sdk for the runtime mixins.

Each adapter instance represents one WeChat account slot. The
``account_id`` is initially a placeholder (e.g. ``_pending_1``) for an
in-progress login, then relabelled to the wxid once login completes.
Login lifecycle methods live in ``lifecycle.AdapterLifecycleMixin``;
outbound message methods live in ``outbound.AdapterOutboundMixin``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from wechatbot import WeChatBot
from wechatbot.types import Credentials, IncomingMessage

from .lifecycle import AdapterLifecycleMixin
from .outbound import AdapterOutboundMixin
from .peer_store import PeerContextStore

logger = logging.getLogger(__name__)


class WeChatBotAdapter(AdapterLifecycleMixin, AdapterOutboundMixin):
    def __init__(
        self,
        *,
        account_id: str,
        state_dir: str | Path,
        cred_path: str | Path | None = None,
        on_qr_url: Callable[[str], None] | None = None,
    ):
        self.account_id = account_id
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_store = PeerContextStore(account_key=account_id)
        self._cred_path = Path(cred_path) if cred_path else self.state_dir / "credentials.json"
        self._on_qr_url = on_qr_url
        self._bot: WeChatBot | None = None
        self._message_handler: Callable[[IncomingMessage], Any] | None = None
        self._qr_url_cache: str | None = None
        self._handler_registered = False
        self._login_lock: asyncio.Lock | None = None
        self._login_task: asyncio.Task | None = None
        self._login_in_progress = False

    def _create_bot(self) -> WeChatBot:
        return WeChatBot(cred_path=str(self._cred_path), on_qr_url=self._handle_qr_url)

    def _handle_qr_url(self, url: str) -> None:
        self._qr_url_cache = url
        logger.info("WeChat QR URL received: %s", url)
        if self._on_qr_url:
            self._on_qr_url(url)

    @property
    def qr_url_cache(self) -> str | None:
        return self._qr_url_cache

    @property
    def login_in_progress(self) -> bool:
        return self._login_in_progress

    def get_bot(self) -> WeChatBot:
        if self._bot is None:
            self._bot = self._create_bot()
            self._handler_registered = False
        return self._bot

    def get_credentials(self) -> Credentials | None:
        return self._bot.get_credentials() if self._bot is not None else None

    def on_message(self, handler: Callable[[IncomingMessage], Any]) -> None:
        self._message_handler = handler

    def _get_login_lock(self) -> asyncio.Lock:
        if self._login_lock is None:
            self._login_lock = asyncio.Lock()
        return self._login_lock

    async def start_polling(self) -> None:
        bot = self.get_bot()
        if self._message_handler and not self._handler_registered:
            bot.on_message(self._message_handler)
            self._handler_registered = True
        await bot.start()

    def stop(self) -> None:
        if self._bot:
            self._bot.stop()
