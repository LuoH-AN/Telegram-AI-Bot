"""Main runtime loop and inbound dispatch.

Uses wechatbot-sdk's long-poll loop with an on_message callback.
Supports multiple accounts: each account gets its own poll loop.
Inbound messages are routed by the account that received them.
"""

from __future__ import annotations

import asyncio

from services.cron import set_main_loop, start_cron_scheduler
from platforms.shared.runtime import make_bounded_dispatcher
from platforms.wechat.services.official import local_chat_id_for_wechat

from ..config import logger
from ..context import WeChatMessageContext

MAX_INBOUND_TASKS = 8


class RuntimeLoopMixin:
    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        set_main_loop(self._loop)
        start_cron_scheduler(self)

        # Login any accounts that don't have credentials yet
        await self._ensure_all_logged_in()

        # Start loopback HTTP login API so Telegram can trigger QR login
        from .login_api import start_login_api_server

        login_api_runner = await start_login_api_server()

        dispatcher = make_bounded_dispatcher(
            self.handle_sdk_message,
            max_concurrent=MAX_INBOUND_TASKS,
            error_log_label="WeChat inbound message",
            logger=logger,
        )

        self._accounts.start_all(dispatcher)
        logger.info(
            "WeChat runtime started with %d account(s): %s",
            len(self.get_account_ids()),
            ", ".join(self.get_account_ids()) or "(none)",
        )

        # Keep running forever
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self._accounts.stop_all()
            await login_api_runner.cleanup()

    async def _ensure_all_logged_in(self) -> None:
        for account_id in self.get_account_ids():
            account = self._accounts.get_account(account_id)
            if not account:
                continue
            creds = account.adapter.get_credentials()
            if creds:
                account.adapter.state_store.update_credentials(
                    token=creds.token,
                    user_id=creds.user_id,
                    base_url=creds.base_url,
                )
                logger.info("Account %s already logged in (user_id=%s)", account_id, creds.user_id)
                continue
            # Need to login — set as active for mixin compat
            self.set_active_account(account_id)
            await self.login()
            logger.info("Account %s logged in", account_id)

    async def handle_sdk_message(self, msg) -> None:
        """Handle an IncomingMessage from the wechatbot SDK."""
        from ..chat.process import process_chat_message
        from ..commands.dispatch import dispatch_command

        inbound = self._parse_sdk_message(msg)

        # Determine which account received this message.
        # The SDK puts the bot's user_id in msg.to_user_id (for single chat)
        # or in the raw payload. Fall back to first account if ambiguous.
        account_id = self._resolve_account_id(msg)
        if account_id:
            self.set_active_account(account_id)

        if not self.client:
            logger.warning("No active WeChat account, dropping message")
            return

        state = self.client.state_store.load()
        if self._should_skip_inbound_echo(inbound, str(state.user_id or "").strip()):
            return
        if self._seen_messages.remember_once(inbound.inbound_key):
            return

        peer_id = inbound.from_user_id
        if not peer_id:
            return

        context_token = getattr(msg, "_context_token", None) or str(
            getattr(msg, "raw", {}).get("context_token") or ""
        ).strip() or None

        local_user_id = self.client.state_store.remember_peer(peer_id, context_token=context_token)
        reply_to_id = peer_id
        if context_token:
            self.client.state_store.remember_context_token(reply_to_id, context_token)

        ctx = WeChatMessageContext(
            runtime=self,
            peer_id=peer_id,
            reply_to_id=reply_to_id,
            local_user_id=local_user_id,
            local_chat_id=local_chat_id_for_wechat(reply_to_id),
            is_group=False,
            group_id=None,
            context_token=context_token,
            inbound_key=inbound.inbound_key,
            _sdk_msg=msg,
        )
        if inbound.normalized_text.startswith(self.command_prefix):
            await dispatch_command(ctx, inbound.normalized_text)
            return
        await process_chat_message(self, ctx, msg)

    def _resolve_account_id(self, msg) -> str | None:
        """Try to determine which account received this message.

        The SDK's IncomingMessage has `to_user_id` for single chat
        (the bot's own wxid). For group messages, check raw payload.
        """
        # Direct attribute
        to_user = getattr(msg, "to_user_id", None)
        if to_user:
            return str(to_user)

        # Raw payload
        raw = getattr(msg, "raw", {}) or {}
        to_user = raw.get("to_user_id") or raw.get("toUserName") or raw.get("self_id")
        if to_user:
            return str(to_user)

        # Fallback: first account
        ids = self.get_account_ids()
        return ids[0] if ids else None
