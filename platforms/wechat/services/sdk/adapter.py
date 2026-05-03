"""Adapter wrapping wechatbot-sdk to provide the interface expected by the runtime mixins.

This adapter owns the WeChatBot instance and exposes:
- state_store: peer/context mapping backed by the same DB schema
- login lifecycle (QR URL capture, credential extraction)
- message polling via the SDK's long-poll loop
- send_text / send_media / typing methods
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from wechatbot import WeChatBot
from wechatbot.types import Credentials, IncomingMessage

from platforms.wechat.services.official.ids import local_user_id_for_wechat
from platforms.wechat.services.official.state.db import load_state_from_db, save_state_to_db
from platforms.wechat.services.official.state.model import WeChatAccountState

logger = logging.getLogger(__name__)


class _PeerContextStore:
    """Lightweight peer/context mapping persisted to the same DB table.

    Replaces the old WeChatStateStore for peer_map + context_tokens while
    letting the SDK manage login credentials via cred_path.
    """

    def __init__(self, account_key: str = "default"):
        self._account_key = (account_key or "default").strip() or "default"
        self._lock = threading.RLock()
        self._cached_state: WeChatAccountState | None = None
        self._logger = logger

    @staticmethod
    def _clone_state(state: WeChatAccountState) -> WeChatAccountState:
        return WeChatAccountState(
            token=state.token,
            user_id=state.user_id,
            base_url=state.base_url,
            get_updates_buf=state.get_updates_buf,
            peer_map=dict(state.peer_map),
            context_tokens=dict(state.context_tokens),
        )

    def load(self, *, force: bool = False) -> WeChatAccountState:
        with self._lock:
            if self._cached_state is None or force:
                self._cached_state = load_state_from_db(self._account_key, self._logger)
            return self._clone_state(self._cached_state)

    def save(self, state: WeChatAccountState) -> None:
        with self._lock:
            self._cached_state = self._clone_state(state)
            save_state_to_db(self._account_key, state, self._logger)

    def update_credentials(self, token: str, user_id: str, base_url: str) -> None:
        state = self.load()
        state.token = token
        state.user_id = user_id
        state.base_url = base_url
        state.get_updates_buf = ""
        self.save(state)

    def clear_token(self) -> None:
        state = self.load()
        state.token = ""
        state.user_id = ""
        state.get_updates_buf = ""
        self.save(state)

    def clear_all(self) -> None:
        state = self.load()
        state.token = ""
        state.user_id = ""
        state.get_updates_buf = ""
        state.peer_map = {}
        state.context_tokens = {}
        self.save(state)

    def remember_peer(self, peer_id: str, *, context_token: str | None = None) -> int:
        local_id = local_user_id_for_wechat(peer_id)
        state = self.load()
        state.peer_map[str(local_id)] = peer_id
        if context_token:
            state.context_tokens[peer_id] = context_token
        self.save(state)
        return local_id

    def remember_context_token(self, scope_id: str, context_token: str) -> None:
        if scope_id and context_token:
            state = self.load()
            state.context_tokens[scope_id] = context_token
            self.save(state)

    def resolve_peer(self, local_user_id: int) -> str | None:
        return self.load().peer_map.get(str(local_user_id))

    def resolve_context_token(self, peer_id: str) -> str | None:
        return self.load().context_tokens.get(peer_id)


class WeChatBotAdapter:
    """Wraps wechatbot.WeChatBot and exposes the interface consumed by runtime mixins.

    Each adapter instance represents one logged-in WeChat account.
    The `account_id` is the WeChat user_id (wxid) used as the unique key.
    """

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
        self.state_store = _PeerContextStore(account_key=account_id)

        if cred_path:
            self._cred_path = Path(cred_path)
        else:
            self._cred_path = self.state_dir / "credentials.json"

        self._on_qr_url = on_qr_url
        self._bot: WeChatBot | None = None
        self._message_handler: Callable[[IncomingMessage], Any] | None = None
        self._qr_url_cache: str | None = None
        self._handler_registered = False
        self._login_lock: asyncio.Lock | None = None

    def _create_bot(self) -> WeChatBot:
        return WeChatBot(
            cred_path=str(self._cred_path),
            on_qr_url=self._handle_qr_url,
        )

    def _handle_qr_url(self, url: str) -> None:
        self._qr_url_cache = url
        logger.info("WeChat QR URL received: %s", url)
        if self._on_qr_url:
            self._on_qr_url(url)

    @property
    def qr_url_cache(self) -> str | None:
        return self._qr_url_cache

    def get_bot(self) -> WeChatBot:
        if self._bot is None:
            self._bot = self._create_bot()
            self._handler_registered = False
        return self._bot

    def get_credentials(self) -> Credentials | None:
        if self._bot is None:
            return None
        return self._bot.get_credentials()

    def on_message(self, handler: Callable[[IncomingMessage], Any]) -> None:
        self._message_handler = handler

    def _get_login_lock(self) -> asyncio.Lock:
        if self._login_lock is None:
            self._login_lock = asyncio.Lock()
        return self._login_lock

    async def login(self, *, force: bool = False) -> dict:
        async with self._get_login_lock():
            bot = self.get_bot()
            creds = bot.get_credentials()
            if creds is None or force:
                creds = await bot.login(force=force)
        self._qr_url_cache = None
        self.state_store.update_credentials(
            token=creds.token,
            user_id=creds.user_id,
            base_url=creds.base_url,
        )
        return {
            "bot_token": creds.token,
            "ilink_user_id": creds.user_id,
            "baseurl": creds.base_url,
            "account_id": creds.account_id,
        }

    async def start_polling(self) -> None:
        bot = self.get_bot()
        if self._message_handler and not self._handler_registered:
            bot.on_message(self._message_handler)
            self._handler_registered = True
        await bot.start()

    def stop(self) -> None:
        if self._bot:
            self._bot.stop()

    def reset(self, *, clear_credentials: bool = False, clear_mappings: bool = False) -> None:
        if self._bot:
            self._bot.stop()
        self._bot = None
        self._handler_registered = False
        self._qr_url_cache = None
        if clear_credentials:
            self._cred_path.unlink(missing_ok=True)
        if clear_mappings:
            self.state_store.clear_all()
        else:
            self.state_store.clear_token()

    def _seed_context_token(self, bot: WeChatBot, user_id: str, context_token: str | None) -> str | None:
        resolved = context_token or self.state_store.resolve_context_token(user_id)
        if resolved:
            bot._context_tokens[user_id] = resolved
        return resolved

    async def send_text(self, user_id: str, text: str, *, context_token: str | None = None) -> None:
        bot = self.get_bot()
        self._seed_context_token(bot, user_id, context_token)
        await bot.send(user_id, text)

    async def send_media(self, user_id: str, content: dict, *, context_token: str | None = None) -> None:
        bot = self.get_bot()
        self._seed_context_token(bot, user_id, context_token)
        await bot.send_media(user_id, content)

    async def reply_to_message(self, msg: IncomingMessage, text: str) -> None:
        bot = self.get_bot()
        await bot.reply(msg, text)

    async def download_media(self, msg: IncomingMessage):
        bot = self.get_bot()
        return await bot.download(msg)

    async def send_typing(self, user_id: str, *, context_token: str | None = None) -> None:
        bot = self.get_bot()
        self._seed_context_token(bot, user_id, context_token)
        await bot.send_typing(user_id)

    async def stop_typing(self, user_id: str, *, context_token: str | None = None) -> None:
        bot = self.get_bot()
        self._seed_context_token(bot, user_id, context_token)
        await bot.stop_typing(user_id)
