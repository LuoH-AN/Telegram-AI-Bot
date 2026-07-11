from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from adapters.telegram.rich_text import send_rich_text
from adapters.telegram.ux.locale import language, pick
from adapters.telegram.ux.panels import stop_keyboard
from infrastructure.config import (
    MAX_MESSAGE_LENGTH,
    STREAM_FORCE_UPDATE_INTERVAL,
    TELEGRAM_NATIVE_DRAFTS,
    normalize_telegram_tool_progress,
)
from shared.utils.ai.status import build_tool_progress_text
from shared.utils.stream import ChatEventPump, StreamOutboundAdapter, edit_message_safe, send_message_safe

from .draft import build_draft_id, can_use_native_draft, send_native_draft

logger = logging.getLogger(__name__)


@dataclass
class RenderState:
    bot_message: object | None
    final_delivery_confirmed: bool = False
    status_seed_cancelled: bool = False
    user_message_persisted: bool = False
    tool_message: object | None = None
    tool_messages: list[object] = field(default_factory=list)
    native_draft_enabled: bool = False
    native_draft_failed: bool = False
    draft_id: int = 0
    finished: bool = False


@dataclass
class RenderRuntime:
    state: RenderState
    outbound: StreamOutboundAdapter
    render_pump: ChatEventPump
    stream_update: Callable[[str], Awaitable[bool]]
    status_update: Callable[[str], Awaitable[bool]]
    tool_event_callback: Callable[[dict], None]
    prepare_tool_boundary: Callable[[str], Awaitable[bool]]
    clear_placeholder: Callable[[], None]
    clear_tool_status: Callable[[], Awaitable[None]]
    status_seed_task: asyncio.Task


async def setup_render_runtime(
    update,
    context,
    bot_message,
    ctx: str,
    *,
    tool_progress_mode: str | None = None,
) -> RenderRuntime:
    message = update.effective_message
    native_draft = TELEGRAM_NATIVE_DRAFTS and bot_message is None and can_use_native_draft(update)
    draft_id = build_draft_id(update) if native_draft else 0
    state = RenderState(bot_message, native_draft_enabled=native_draft, draft_id=draft_id)
    lang = language(update, context)
    user_id = update.effective_user.id
    progress_mode = normalize_telegram_tool_progress(tool_progress_mode)

    async def _edit_placeholder(text: str) -> bool:
        if state.bot_message is None:
            if state.native_draft_enabled and not state.native_draft_failed:
                if await send_native_draft(update, context, state.draft_id, text):
                    return True
                state.native_draft_failed = True
            sent_messages = await send_message_safe(
                message,
                text,
                reply_markup=None if state.finished else stop_keyboard(lang, user_id=user_id),
            )
            if not sent_messages:
                return False
            state.bot_message = sent_messages[-1]
            return True
        return await edit_message_safe(
            state.bot_message,
            text,
            reply_markup=None if state.finished else stop_keyboard(lang, user_id=user_id),
        )

    async def _send_text(text: str) -> bool:
        if await send_rich_text(message, text):
            return True
        return bool(await send_message_safe(message, text))

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
        can_edit_final=lambda: state.bot_message is not None,
        edit_placeholder=_edit_placeholder,
        send_text=_send_text,
        delete_placeholder=_delete_placeholder,
        empty_placeholder_text="",
        stream_edit_min_interval_seconds=STREAM_FORCE_UPDATE_INTERVAL,
    )

    async def _start_tool_status(text: str) -> bool:
        if state.tool_message is not None:
            state.tool_messages.append(state.tool_message)
            state.tool_message = None
        sent_messages = await send_message_safe(message, text, disable_notification=True)
        if not sent_messages:
            return False
        state.tool_message = sent_messages[-1]
        return True

    async def _render_tool_status(text: str) -> bool:
        if state.tool_message is None:
            return await _start_tool_status(text)
        return await edit_message_safe(state.tool_message, text)

    async def _finish_tool_status(text: str) -> bool:
        if state.tool_message is None:
            ok = await _start_tool_status(text)
            if state.tool_message is not None:
                state.tool_messages.append(state.tool_message)
                state.tool_message = None
            return ok
        ok = await edit_message_safe(state.tool_message, text)
        state.tool_messages.append(state.tool_message)
        state.tool_message = None
        return ok

    tool_states: dict[str, str] = {}

    async def _clear_tool_status() -> None:
        if state.tool_message is None:
            return
        for name, status in list(tool_states.items()):
            if status == "running":
                tool_states[name] = "error"
        text = build_tool_progress_text(tool_states, lang=lang, mode=progress_mode)
        if text:
            await _finish_tool_status(text)
        else:
            state.tool_messages.append(state.tool_message)
            state.tool_message = None

    async def _render_event(event) -> bool:
        if event.kind == "tool_round_start":
            return await _start_tool_status(event.text)
        if event.kind == "tool_round_update":
            return await _render_tool_status(event.text)
        if event.kind == "tool_round_end":
            return await _finish_tool_status(event.text)
        if event.kind in {"stream", "status"}:
            return await outbound.stream_update(event.text)
        return False

    render_pump = ChatEventPump(_render_event)
    render_pump.start()
    loop = asyncio.get_running_loop()
    last_tool_status = ""

    def _emit_tool_status(kind: str, *, force: bool = False) -> None:
        nonlocal last_tool_status
        status_text = build_tool_progress_text(tool_states, lang=lang, mode=progress_mode)
        if not status_text:
            return
        if not force and status_text == last_tool_status:
            return
        last_tool_status = status_text
        render_pump.emit_threadsafe(loop, kind, status_text)

    def _tool_event_callback(event: dict) -> None:
        nonlocal last_tool_status
        event_type = str(event.get("type") or "").strip()
        name = str(event.get("tool_name") or "").strip()
        if event_type == "tool_batch_start":
            tool_states.clear()
            last_tool_status = ""
            for tool_name in event.get("tool_names") or []:
                tool_states[str(tool_name)] = "running"
            _emit_tool_status("tool_round_start", force=True)
        elif event_type == "tool_start" and name:
            tool_states[name] = "running"
        elif event_type == "tool_error" and name:
            tool_states[name] = "error"
        elif event_type == "tool_end" and name:
            tool_states[name] = "done" if event.get("ok") else "error"
        elif event_type == "tool_batch_end":
            _emit_tool_status("tool_round_end", force=True)
            return
        else:
            return
        _emit_tool_status("tool_round_update")

    async def _stream_update(text: str) -> bool:
        return await render_pump.emit("stream", text)

    async def _status_update(text: str) -> bool:
        return await render_pump.emit("status", text)

    async def _prepare_tool_boundary(text: str) -> bool:
        await render_pump.drain()
        state.native_draft_enabled = False
        visible = (text or "").strip()
        if visible:
            ok = await outbound.deliver_final(visible)
            if state.bot_message is not None:
                try:
                    await state.bot_message.edit_reply_markup(reply_markup=None)
                except Exception:
                    logger.debug("%s failed to remove stop keyboard at tool boundary", ctx, exc_info=True)
        else:
            await outbound.discard_placeholder()
            ok = True
        state.bot_message = None
        outbound.reset_stream_window()
        return ok

    async def _seed_status_after_delay() -> None:
        try:
            await asyncio.sleep(3)
            if not state.status_seed_cancelled and not state.final_delivery_confirmed:
                await _status_update(pick(lang, "正在思考…", "Thinking…"))
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
        prepare_tool_boundary=_prepare_tool_boundary,
        clear_placeholder=lambda: setattr(state, "bot_message", None),
        clear_tool_status=_clear_tool_status,
        status_seed_task=asyncio.create_task(_seed_status_after_delay()),
    )
