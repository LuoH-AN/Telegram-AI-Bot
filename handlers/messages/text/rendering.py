from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from config import MAX_MESSAGE_LENGTH
from utils import ChatEventPump, StreamOutboundAdapter, edit_message_safe, send_message_safe

logger = logging.getLogger(__name__)

@dataclass
class RenderState:
    bot_message: object | None
    final_delivery_confirmed: bool = False
    status_seed_cancelled: bool = False

@dataclass
class RenderRuntime:
    state: RenderState
    outbound: StreamOutboundAdapter
    render_pump: ChatEventPump
    stream_update: Callable[[str], Awaitable[bool]]
    status_update: Callable[[str], Awaitable[bool]]
    tool_event_callback: Callable[[dict], None]
    clear_placeholder: Callable[[], None]
    status_seed_task: asyncio.Task

async def setup_render_runtime(update, bot_message, ctx: str) -> RenderRuntime:
    state = RenderState(bot_message=bot_message)
    async def _edit_placeholder(text: str) -> bool:
        if state.bot_message is None:
            sent_messages = await send_message_safe(update.message, text)
            if not sent_messages:
                return False
            state.bot_message = sent_messages[-1]
            return True
        return await edit_message_safe(state.bot_message, text)
    async def _send_text(text: str) -> bool:
        return bool(await send_message_safe(update.message, text))
    async def _delete_placeholder() -> None:
        if state.bot_message is None:
            return
        try:
            await state.bot_message.delete()
        except Exception:
            pass
        state.bot_message = None
    outbound = StreamOutboundAdapter(
        max_message_length=MAX_MESSAGE_LENGTH,
        has_placeholder=lambda: True,
        edit_placeholder=_edit_placeholder,
        send_text=_send_text,
        delete_placeholder=_delete_placeholder,
        empty_placeholder_text="",
    )
    async def _render_event(event) -> None:
        if event.kind in {"stream", "status"}:
            await outbound.stream_update(event.text)
    render_pump = ChatEventPump(_render_event)
    render_pump.start()
    loop = asyncio.get_running_loop()
    def _tool_event_callback(event: dict) -> None:
        if event.get("type") == "tool_start":
            tool_name = str(event.get("tool_name") or "tool").strip() or "tool"
            render_pump.emit_threadsafe(loop, "status", f"Running {tool_name}...")
    async def _stream_update(text: str) -> bool:
        return await render_pump.emit("stream", text)
    async def _status_update(text: str) -> bool:
        return await render_pump.emit("status", text)
    async def _seed_status_after_delay() -> None:
        try:
            await asyncio.sleep(3)
            if not state.status_seed_cancelled and not state.final_delivery_confirmed:
                await _status_update("Thinking...")
        except asyncio.CancelledError:
            return
        except Exception:
            logger.debug("%s failed to seed Telegram delayed status", ctx, exc_info=True)
    return RenderRuntime(
        state=state,
        outbound=outbound,
        render_pump=render_pump,
        stream_update=_stream_update,
        status_update=_status_update,
        tool_event_callback=_tool_event_callback,
        clear_placeholder=lambda: setattr(state, "bot_message", None),
        status_seed_task=asyncio.create_task(_seed_status_after_delay()),
    )
