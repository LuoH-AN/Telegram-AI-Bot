"""Main runtime loop and inbound dispatch."""

from __future__ import annotations

import asyncio

from services.cron import set_main_loop, start_cron_scheduler
from services.wechat.official import local_chat_id_for_wechat

from ..config import logger
from ..context import WeChatMessageContext
from ..message.extract import should_respond_in_wechat_group


class RuntimeLoopMixin:
    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        set_main_loop(self._loop)
        start_cron_scheduler(self)
        while True:
            try:
                await self.login()
                state = self.client.state_store.load()
                response = await asyncio.to_thread(self.client.get_updates, state.token, state.get_updates_buf)
                if int(response.get("errcode") or 0) == -14:
                    logger.warning("WeChat session expired, clearing local token and restarting login")
                    self.client.state_store.clear_token()
                    await asyncio.sleep(2)
                    continue
                next_buf = str(response.get("get_updates_buf") or "")
                if next_buf:
                    state.get_updates_buf = next_buf
                    self.client.state_store.save(state)
                for message in response.get("msgs") or []:
                    await self.handle_message(message)
            except Exception:
                logger.exception("WeChat main loop failed")
                await asyncio.sleep(5)

    async def handle_message(self, message: dict) -> None:
        from ..chat.process import process_chat_message
        from ..commands.dispatch import dispatch_command
        inbound = self._parse_inbound_message(message)
        if inbound.message_type == 2:
            return
        state = self.client.state_store.load()
        if self._should_skip_inbound_echo(inbound, str(state.user_id or "").strip()):
            return
        if inbound.message_state == 1 or self._seen_messages.remember_once(inbound.inbound_key):
            return
        peer_id = inbound.from_user_id
        if not peer_id:
            return
        reply_to_id = inbound.reply_to_id
        context_token = str(message.get("context_token") or "").strip() or None
        local_user_id = self.client.state_store.remember_peer(peer_id, context_token=context_token)
        if context_token:
            self.client.state_store.remember_context_token(reply_to_id, context_token)
        ctx = WeChatMessageContext(
            runtime=self,
            peer_id=peer_id,
            reply_to_id=reply_to_id,
            local_user_id=local_user_id,
            local_chat_id=local_chat_id_for_wechat(reply_to_id),
            is_group=inbound.is_group,
            group_id=inbound.group_id,
            context_token=context_token,
            inbound_key=inbound.inbound_key,
        )
        if ctx.is_group and not should_respond_in_wechat_group(inbound.text_body):
            return
        if inbound.normalized_text.startswith(self.command_prefix):
            await dispatch_command(ctx, inbound.normalized_text)
            return
        await process_chat_message(self, ctx, message)
