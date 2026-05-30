"""Shared inbound chat pipeline used by OneBot and WeChat."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

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
from services.queue import cancel_user_responses, register_response, unregister_response
from utils.files import get_datetime_prompt
from utils.ai import build_tool_status_text
from utils.ai import estimate_tokens as _estimate_tokens
from utils.ai import estimate_tokens_str as _estimate_tokens_str
from utils.platform import (
    build_api_key_required_message,
    build_latex_guidance,
    build_retry_message,
    build_token_limit_reached_message,
)

from platforms.shared.cache import NoopPump
from platforms.shared.outbound import bind_outbound, reset_outbound
from .round import run_completion_round
from .title import generate_and_set_title

logger = logging.getLogger(__name__)

SendToolStatus = Callable[[str], Awaitable[None]]
TypingFactory = Callable[[], tuple[asyncio.Event, asyncio.Task] | tuple[None, None]]
OutboundFactory = Callable[[], object]
AssistantReplyHook = Callable[[str], None]


async def process_inbound_chat(
    *,
    ctx,
    platform: str,
    user_content,
    save_msg,
    slot_key: str,
    session_user_id: int | None = None,
    send_tool_status: SendToolStatus | None = None,
    typing_factory: TypingFactory | None = None,
    outbound_factory: OutboundFactory | None = None,
    on_assistant_reply: AssistantReplyHook | None = None,
) -> None:
    """Run the full inbound-message → AI-reply pipeline.

    Platform code prepares ``user_content``/``save_msg``/``slot_key`` and
    optional helpers. This function handles the rest: api-key check, token
    limit, message build, tool-call round, persistence, accounting.
    """
    user_id = ctx.local_user_id
    if session_user_id is None:
        session_user_id = getattr(ctx, "session_user_id", user_id)

    await ensure_user_state(session_user_id)

    if isinstance(user_content, str) and not user_content.strip():
        await ctx.reply_text("Please send a text message or attachment.")
        return
    if not has_api_key(session_user_id):
        await ctx.reply_text(build_api_key_required_message(ctx.runtime.command_prefix))
        return

    persona_name = get_current_persona_name(session_user_id)
    remaining = get_remaining_tokens(session_user_id, persona_name)
    if remaining is not None and remaining <= 0:
        await ctx.reply_text(build_token_limit_reached_message(ctx.runtime.command_prefix, persona_name))
        return
    settings = get_user_settings(session_user_id)
    reasoning = str(settings.get("reasoning_effort", "") or "").strip().lower()
    show_thinking = bool(settings.get("show_thinking"))
    session_id = ensure_session(session_user_id, persona_name)

    cancelled = cancel_user_responses(ctx.local_chat_id, user_id, platform=platform)
    if cancelled:
        logger.info(
            "%s cancelled %d active %s response(s)",
            ctx.log_context,
            len(cancelled),
            platform,
        )

    request_start = time.monotonic()
    messages = (
        [
            {
                "role": "system",
                "content": get_system_prompt(session_user_id, persona_name)
                + "\n\n"
                + get_datetime_prompt()
                + build_latex_guidance(),
            }
        ]
        + list(get_conversation(session_id))
        + [{"role": "user", "content": user_content}]
    )

    loop = asyncio.get_running_loop()

    def _tool_event_callback(event: dict) -> None:
        if send_tool_status is None:
            return
        if str(event.get("type") or "").strip() != "tool_batch_start":
            return
        status_text = build_tool_status_text(event.get("tool_names") or [])
        if not status_text:
            return

        def _schedule() -> None:
            asyncio.create_task(_safe_send(send_tool_status, status_text, ctx.log_context))

        loop.call_soon_threadsafe(_schedule)

    conversation_key = f"{platform}:{ctx.local_chat_id}:{session_user_id}:{session_id}"
    response_key = slot_key
    final_delivery_confirmed = False
    current_task = asyncio.current_task()
    if current_task:
        register_response(response_key, task=current_task, pump=NoopPump())

    typing_stop, typing_task = (None, None)
    if typing_factory is not None:
        typing_stop, typing_task = typing_factory()

    outbound_token = None
    if outbound_factory is not None:
        try:
            outbound_token = bind_outbound(outbound_factory())
        except Exception:
            logger.debug("%s failed to bind outbound sender", ctx.log_context, exc_info=True)

    try:
        async with conversation_slot(conversation_key) as was_queued:
            if was_queued:
                await ctx.reply_text("Previous request is still running. Queued and starting soon...")
            generated = await run_completion_round(
                user_id=session_user_id,
                settings=settings,
                messages=messages,
                user_reasoning_effort=reasoning,
                show_thinking=show_thinking,
                tool_event_callback=_tool_event_callback,
            )

        send_final = getattr(ctx, "send_chat_reply", None)
        if send_final is not None:
            await send_final(generated["display_final"])
        else:
            await ctx.reply_text(generated["display_final"])
        final_delivery_confirmed = True

        add_user_message(session_id, save_msg)
        add_assistant_message(session_id, generated["final_text"], generated.get("reasoning_content"))
        if on_assistant_reply is not None:
            try:
                on_assistant_reply(generated["final_text"])
            except Exception:
                logger.debug("%s on_assistant_reply hook failed", ctx.log_context, exc_info=True)

        if get_session_message_count(session_id) <= 2:
            asyncio.create_task(
                generate_and_set_title(
                    session_user_id,
                    session_id,
                    save_msg,
                    generated["final_text"],
                    log_context=ctx.log_context,
                )
            )

        prompt_tokens = generated["prompt_tokens"] or _estimate_tokens(generated["messages"])
        completion_tokens = generated["completion_tokens"] or _estimate_tokens_str(generated["final_text"])
        if prompt_tokens or completion_tokens:
            add_token_usage(session_user_id, prompt_tokens, completion_tokens, persona_name=persona_name)

        latency_ms = int((time.monotonic() - request_start) * 1000)
        record_ai_interaction(
            session_user_id,
            settings["model"],
            prompt_tokens,
            completion_tokens,
            prompt_tokens + completion_tokens,
            None,
            latency_ms,
            persona_name,
        )

    except asyncio.CancelledError:
        logger.info("%s response cancelled", ctx.log_context)
        if not final_delivery_confirmed:
            await ctx.reply_text("(Response stopped)")
    except Exception as exc:
        logger.exception("%s AI API error", ctx.log_context)
        if not final_delivery_confirmed:
            await ctx.reply_text(build_retry_message())
            try:
                add_user_message(session_id, save_msg)
            except Exception:
                logger.debug("%s failed to persist user message after error", ctx.log_context, exc_info=True)
        record_error(session_user_id, str(exc), f"{platform} chat handler", settings.get("model"), persona_name)
    finally:
        if typing_stop is not None:
            typing_stop.set()
        if typing_task is not None:
            try:
                await typing_task
            except Exception:
                pass
        if outbound_token is not None:
            reset_outbound(outbound_token)
        unregister_response(response_key)


async def _safe_send(send: SendToolStatus, text: str, log_context: str) -> None:
    try:
        await send(text)
    except Exception:
        logger.debug("%s failed to send tool status", log_context, exc_info=True)
