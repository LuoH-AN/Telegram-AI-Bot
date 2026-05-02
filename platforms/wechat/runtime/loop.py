"""Main runtime loop and inbound dispatch.

Uses wechatbot-sdk's long-poll loop with an on_message callback.
The SDK handles get_updates polling, cursor management, and session
expiry internally. We just register a handler and start.
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

        self.client.on_message(
            make_bounded_dispatcher(
                self.handle_sdk_message,
                max_concurrent=MAX_INBOUND_TASKS,
                error_log_label="WeChat inbound message",
                logger=logger,
            )
        )

        while True:
            try:
                await self._ensure_logged_in()
                logger.info("WeChat polling started")
                await self.client.start_polling()
            except Exception:
                logger.exception("WeChat main loop failed, restarting in 5s")
                await asyncio.sleep(5)

    async def _ensure_logged_in(self) -> None:
        creds = self.client.get_credentials()
        if creds:
            self.client.state_store.update_credentials(
                token=creds.token,
                user_id=creds.user_id,
                base_url=creds.base_url,
            )
            self._set_login_snapshot(logged_in=True, status="connected", message="WeChat is already logged in", user_id=creds.user_id, qr_url="")
            return
        await self.login()

    async def handle_sdk_message(self, msg) -> None:
        """Handle an IncomingMessage from the wechatbot SDK."""
        from ..chat.process import process_chat_message
        from ..commands.dispatch import dispatch_command

        inbound = self._parse_sdk_message(msg)
        state = self.client.state_store.load()
        if self._should_skip_inbound_echo(inbound, str(state.user_id or "").strip()):
            return
        if self._seen_messages.remember_once(inbound.inbound_key):
            return

        peer_id = inbound.from_user_id
        if not peer_id:
            return

        # Extract context_token from the SDK message's internal field
        context_token = getattr(msg, "_context_token", None) or str(
            getattr(msg, "raw", {}).get("context_token") or ""
        ).strip() or None

        local_user_id = self.client.state_store.remember_peer(peer_id, context_token=context_token)
        reply_to_id = peer_id  # Single-chat: reply target is always the peer
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
