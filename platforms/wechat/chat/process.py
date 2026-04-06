"""Inbound chat processing for WeChat messages."""

from __future__ import annotations

import asyncio
import time

from services import (
    add_assistant_message,
    add_token_usage,
    add_user_message,
    conversation_slot,
    ensure_session,
    get_conversation,
    get_current_persona_name,
    get_remaining_tokens,
    get_session_message_count,
    get_system_prompt,
    get_user_settings,
    has_api_key,
)
from services.log import record_ai_interaction, record_error
from services.refresh import ensure_user_state
from services.runtime_queue import cancel_user_responses, register_response, unregister_response
from utils import get_datetime_prompt
from utils.tool_status import build_tool_status_text
from utils.ai_helpers import estimate_tokens as _estimate_tokens
from utils.ai_helpers import estimate_tokens_str as _estimate_tokens_str
from utils.platform_parity import build_api_key_required_message, build_latex_guidance, build_retry_message, build_token_limit_reached_message

from ..config import logger
from ..message.content import build_user_content_from_wechat_message
from ..recent_cache import NoopPump
from .round import run_completion_round
from .title import generate_and_set_title
async def process_chat_message(runtime, ctx, message: dict) -> None:
    user_id = ctx.local_user_id
    ensure_user_state(user_id)
    user_content, save_msg = await build_user_content_from_wechat_message(runtime, message, is_group=ctx.is_group)
    if isinstance(user_content, str) and not user_content.strip():
        await ctx.reply_text("Please send a text message or attachment.")
        return
    if not has_api_key(user_id):
        await ctx.reply_text(build_api_key_required_message(runtime.command_prefix))
        return
    persona_name = get_current_persona_name(user_id)
    remaining = get_remaining_tokens(user_id, persona_name)
    if remaining is not None and remaining <= 0:
        await ctx.reply_text(build_token_limit_reached_message(runtime.command_prefix, persona_name))
        return

    settings = get_user_settings(user_id)
    reasoning = str(settings.get("reasoning_effort", "") or "").strip().lower()
    show_thinking = bool(settings.get("show_thinking"))
    session_id = ensure_session(user_id, persona_name)
    cancelled = cancel_user_responses(ctx.local_chat_id, user_id, platform="wechat")
    if cancelled:
        logger.info("%s cancelled %d active WeChat response(s) due to new incoming message", ctx.log_context, len(cancelled))
    request_start = time.monotonic()
    messages = [{"role": "system", "content": get_system_prompt(user_id, persona_name) + "\n\n" + get_datetime_prompt() + build_latex_guidance()}] + list(get_conversation(session_id)) + [{"role": "user", "content": user_content}]
    loop = asyncio.get_running_loop()
    last_tool_status = {"text": ""}

    async def _send_tool_status(text: str) -> None:
        try:
            await runtime.send_text_to_peer(
                ctx.reply_to_id,
                text,
                context_token=ctx.context_token,
                dedupe_key=None,
            )
        except Exception:
            logger.debug("%s failed to send WeChat tool status", ctx.log_context, exc_info=True)

    def _tool_event_callback(event: dict) -> None:
        event_type = str(event.get("type") or "").strip()
        if event_type not in {"tool_start", "tool_error"}:
            return
        status_text = build_tool_status_text(event)
        if not status_text:
            return

        def _schedule() -> None:
            if status_text == last_tool_status["text"]:
                return
            last_tool_status["text"] = status_text
            asyncio.create_task(_send_tool_status(status_text))

        loop.call_soon_threadsafe(_schedule)

    slot_key = f"wechat:{ctx.local_chat_id}:{user_id}:{session_id}:{ctx.inbound_key or message.get('message_id') or int(time.time() * 1000)}"
    slot_cm = conversation_slot(slot_key)
    was_queued = await slot_cm.__aenter__()
    final_delivery_confirmed = False
    if asyncio.current_task():
        register_response(slot_key, task=asyncio.current_task(), pump=NoopPump())
    typing_stop = asyncio.Event()
    typing_task = asyncio.create_task(runtime._typing_loop(ctx.reply_to_id, ctx.context_token, typing_stop))
    try:
        if was_queued:
            await ctx.reply_text("Previous request is still running. Queued and starting soon...")
        generated = await run_completion_round(
            user_id=user_id,
            settings=settings,
            messages=messages,
            user_reasoning_effort=reasoning,
            show_thinking=show_thinking,
            tool_event_callback=_tool_event_callback,
        )
        await ctx.reply_text(generated["display_final"])
        final_delivery_confirmed = True
        add_user_message(session_id, save_msg)
        add_assistant_message(session_id, generated["final_text"])
        if get_session_message_count(session_id) <= 2:
            asyncio.create_task(generate_and_set_title(user_id, session_id, save_msg, generated["final_text"]))
        prompt_tokens = generated["prompt_tokens"] or _estimate_tokens(generated["messages"])
        completion_tokens = generated["completion_tokens"] or _estimate_tokens_str(generated["final_text"])
        if prompt_tokens or completion_tokens:
            add_token_usage(user_id, prompt_tokens, completion_tokens, persona_name=persona_name)
        latency_ms = int((time.monotonic() - request_start) * 1000)
        record_ai_interaction(user_id, settings["model"], prompt_tokens, completion_tokens, prompt_tokens + completion_tokens, None, latency_ms, persona_name)
    except asyncio.CancelledError:
        logger.info("%s response cancelled by /stop", ctx.log_context)
        if not final_delivery_confirmed:
            await ctx.reply_text("(Response stopped)")
    except Exception as exc:
        logger.exception("%s AI API error", ctx.log_context)
        if not final_delivery_confirmed:
            await ctx.reply_text(build_retry_message())
        record_error(user_id, str(exc), "wechat chat handler", settings.get("model"), persona_name)
    finally:
        typing_stop.set()
        try:
            await typing_task
        except Exception:
            pass
        unregister_response(slot_key)
        await slot_cm.__aexit__(None, None, None)
