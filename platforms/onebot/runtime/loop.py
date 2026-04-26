"""Main runtime loop and inbound dispatch for OneBot.

Uses WebSocket connection to NapCat. Events are received via the
WebSocket connection and dispatched to handlers.
"""

from __future__ import annotations

import asyncio

from services.cron import set_main_loop, start_cron_scheduler

from ..config import logger, ONEBOT_MODE

MAX_INBOUND_TASKS = 8


class RuntimeLoopMixin:
    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        set_main_loop(self._loop)
        start_cron_scheduler(self)

        if ONEBOT_MODE == "ws":
            # WebSocket mode: FastAPI handles the WS connection at /onebot/ws
            # Just wait here - the FastAPI bridge handles incoming connections
            logger.info("OneBot/WS mode: waiting for NapCat WebSocket connections at /onebot/ws")
            while True:
                await asyncio.sleep(60)

        inflight_tasks: set[asyncio.Task] = set()
        semaphore = asyncio.Semaphore(MAX_INBOUND_TASKS)

        async def _dispatch_incoming(event: dict) -> None:
            async with semaphore:
                await self.handle_event(event)

        async def _on_event(event: dict) -> None:
            task = asyncio.create_task(_dispatch_incoming(event))
            inflight_tasks.add(task)

            def _on_done(done: asyncio.Task) -> None:
                inflight_tasks.discard(done)
                try:
                    done.result()
                except asyncio.CancelledError:
                    return
                except Exception:
                    logger.exception("OneBot inbound event task failed")

            task.add_done_callback(_on_done)

        self.client.on_event = _on_event

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

        if ctx.is_group and get_group_mode(int(inbound.group_id)) == "shared":
            session_user_id = int(inbound.group_id)
        else:
            session_user_id = local_user_id

        ctx = self._build_context(inbound, local_user_id, local_chat_id, session_user_id)

        if inbound.normalized_text.startswith(self.command_prefix):
            await dispatch_command(ctx, inbound.normalized_text)
            return

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
