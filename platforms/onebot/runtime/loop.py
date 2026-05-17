"""Main runtime loop and inbound dispatch for OneBot."""

from __future__ import annotations

import asyncio

from services.cron import set_main_loop, start_cron_scheduler
from platforms.shared.runtime import make_bounded_dispatcher

from ..config import (
    logger,
    ONEBOT_MODE,
    ONEBOT_WS_BIND_HOST,
    ONEBOT_WS_BIND_PORT,
    ONEBOT_WS_PATH,
)

MAX_INBOUND_TASKS = 8


class RuntimeLoopMixin:
    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        set_main_loop(self._loop)
        start_cron_scheduler(self)

        if ONEBOT_MODE == "ws":
            from ..ws_server import serve_onebot_ws

            await serve_onebot_ws(
                self,
                host=ONEBOT_WS_BIND_HOST,
                port=ONEBOT_WS_BIND_PORT,
                path=ONEBOT_WS_PATH,
            )
            return

        self.client.on_event = make_bounded_dispatcher(
            self.handle_event,
            max_concurrent=MAX_INBOUND_TASKS,
            error_log_label="OneBot inbound event",
            logger=logger,
        )

        while True:
            try:
                if hasattr(self.client, "start_server"):
                    await self.client.start_server()
                    logger.info("OneBot/NapCat server listening, waiting for connection...")
                    # In server mode, wait for the first connection
                    while not self.client.connected:
                        await asyncio.sleep(1)
                    logger.info("OneBot/NapCat connection established")
                    while self.client.connected:
                        await asyncio.sleep(1)
                else:
                    await self.client.connect()
                    logger.info("OneBot/NapCat connection established")
                    while self.client.connected:
                        await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("OneBot connection failed, reconnecting in 5s")
                await asyncio.sleep(5)

    async def handle_event(self, event: dict) -> None:
        """Handle an incoming OneBot event."""
        from ..chat.process import process_chat_message
        from ..commands.dispatch import dispatch_command
        from .prompt_upload import try_handle_prompt_upload

        if event.get("post_type") == "notice" and event.get("notice_type") == "group_upload":
            self._capture_group_upload(event)
            return

        try:
            inbound = self._parse_event(event)
        except ValueError as exc:
            logger.info("OneBot handle_event: parse failed %s (post_type=%s)", exc, event.get("post_type"))
            return

        logger.info("OneBot handle_event: user=%s chat=%s is_group=%s text=%r command=%s",
            inbound.user_id, inbound.group_id or inbound.user_id, inbound.is_group,
            inbound.normalized_text[:50], inbound.normalized_text.startswith(self.command_prefix))

        if self._seen_messages.remember_once(inbound.inbound_key):
            return

        if self._should_skip_echo(inbound):
            return

        local_user_id = inbound.user_id
        local_chat_id = inbound.group_id if inbound.is_group else inbound.user_id

        from ..group_config import get_group_mode

        is_group = inbound.is_group
        if is_group and get_group_mode(int(inbound.group_id)) == "shared":
            session_user_id = int(inbound.group_id)
        else:
            session_user_id = local_user_id

        ctx = self._build_context(inbound, local_user_id, local_chat_id, session_user_id)

        if await try_handle_prompt_upload(self, ctx, inbound):
            return

        if inbound.normalized_text.startswith(self.command_prefix):
            from platforms.commands.dispatch import is_known_command

            if is_known_command(inbound.normalized_text, self.command_prefix):
                await dispatch_command(ctx, inbound.normalized_text)
                return
            if is_group:
                logger.info("Ignoring unknown slash command in group %s: %r",
                    inbound.group_id, inbound.normalized_text[:50])
                return
            await dispatch_command(ctx, inbound.normalized_text)
            return

        if is_group:
            from ..proactive import (
                extract_nickname,
                is_direct_trigger,
                record_user,
                should_reply_in_group,
            )

            record_user(
                int(inbound.group_id),
                extract_nickname(inbound.raw_event),
                inbound.normalized_text,
            )

            decision = should_reply_in_group(
                group_id=int(inbound.group_id),
                text=inbound.normalized_text,
                raw_event=inbound.raw_event,
                self_id=inbound.self_id,
            )
            if not decision.should_reply:
                logger.info("Skipping group message (reason=%s) group=%s", decision.reason, inbound.group_id)
                return
            ctx.proactive_reason = decision.reason
            ctx.proactive_direct = is_direct_trigger(decision.reason)
            logger.info("Proactive reply: group=%s reason=%s", inbound.group_id, decision.reason)

        await process_chat_message(self, ctx, inbound)

    def _build_context(self, inbound, local_user_id: int, local_chat_id: int, session_user_id: int):
        from ..context import OneBotMessageContext

        return OneBotMessageContext(
            runtime=self,
            peer_id=inbound.reply_to_id,
            reply_to_id=inbound.reply_to_id,
            local_user_id=local_user_id,
            local_chat_id=local_chat_id,
            session_user_id=session_user_id,
            is_group=inbound.is_group,
            group_id=inbound.group_id,
            context_token=None,
            inbound_key=inbound.inbound_key,
            raw_event=inbound.raw_event,
        )

    def _capture_group_upload(self, event: dict) -> None:
        from .pending_uploads import capture_group_upload_notice

        captured = capture_group_upload_notice(event)
        if captured:
            logger.info(
                "Captured group_upload: group=%s user=%s file=%s",
                event.get("group_id"), event.get("user_id"), captured.file_name,
            )
