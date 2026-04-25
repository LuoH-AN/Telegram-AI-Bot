"""Final delivery, persistence, and usage logging."""

from __future__ import annotations

import asyncio
import logging
import time

from services import (
    add_assistant_message,
    add_token_usage,
    add_user_message,
    get_session_message_count,
)
from services.log import record_ai_interaction
from utils.ai_helpers import estimate_tokens as _estimate_tokens
from utils.ai_helpers import estimate_tokens_str as _estimate_tokens_str

from .title import generate_and_set_title

logger = logging.getLogger(__name__)


async def deliver_and_persist(
    *,
    generated: dict,
    runtime,
    req: dict,
    request_start: float,
) -> None:
    runtime.state.status_seed_cancelled = True
    if runtime.status_seed_task and not runtime.status_seed_task.done():
        runtime.status_seed_task.cancel()

    await runtime.render_pump.drain()
    await runtime.render_pump.stop()
    display_final = generated["display_final"]
    thinking_block = generated["thinking_block"]
    final_delivery_ok = False
    if display_final == "(Empty response)" and not thinking_block:
        final_delivery_ok = True
        if runtime.state.bot_message:
            await runtime.state.bot_message.delete()
            runtime.state.bot_message = None
    else:
        final_delivery_ok = await runtime.outbound.deliver_final(display_final)
    runtime.state.final_delivery_confirmed = final_delivery_ok

    if not runtime.state.user_message_persisted:
        add_user_message(req["session_id"], req["save_msg"])
        runtime.state.user_message_persisted = True

    has_assistant_text = generated["final_text"] != "(Empty response)"
    if final_delivery_ok and has_assistant_text:
        add_assistant_message(req["session_id"], generated["final_text"])
        if get_session_message_count(req["session_id"]) <= 2:
            asyncio.create_task(
                generate_and_set_title(req["user_id"], req["session_id"], req["save_msg"], generated["final_text"])
            )
    elif not final_delivery_ok:
        logger.error(
            "%s final response was not delivered (stream_ack=%d/%d); persisted user message only",
            req["ctx"],
            runtime.outbound.stream_successes,
            runtime.outbound.stream_attempts,
        )

    prompt_tokens = generated["total_prompt_tokens"]
    completion_tokens = generated["total_completion_tokens"]
    if not prompt_tokens and not completion_tokens:
        prompt_tokens = _estimate_tokens(generated["messages"])
        completion_tokens = _estimate_tokens_str(generated["final_text"])
    if prompt_tokens or completion_tokens:
        add_token_usage(req["user_id"], prompt_tokens, completion_tokens, persona_name=req["persona_name"])

    latency_ms = int((time.monotonic() - request_start) * 1000)
    record_ai_interaction(
        req["user_id"],
        req["settings"]["model"],
        prompt_tokens,
        completion_tokens,
        prompt_tokens + completion_tokens,
        None,
        latency_ms,
        req["persona_name"],
    )
