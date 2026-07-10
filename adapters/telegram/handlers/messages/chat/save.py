"""Final delivery, persistence, and usage logging."""

from __future__ import annotations

import asyncio
import logging
import time

from domain.services import (
    add_assistant_message,
    add_token_usage,
    add_user_message,
    get_session_message_count,
)
from domain.services.log import record_ai_interaction
from shared.utils.ai import estimate_tokens as _estimate_tokens
from shared.utils.ai import estimate_tokens_str as _estimate_tokens_str

from .title import generate_and_set_title

logger = logging.getLogger(__name__)

# Hold strong refs to background title tasks so the GC can't cancel them mid-run.
_title_tasks: set = set()


def _spawn_title_task(user_id: int, session_id: int, user_message: str, ai_response: str) -> None:
    task = asyncio.create_task(generate_and_set_title(user_id, session_id, user_message, ai_response))
    _title_tasks.add(task)
    task.add_done_callback(_title_tasks.discard)


async def deliver_and_persist(
    *,
    generated: dict,
    runtime,
    req: dict,
    request_start: float,
) -> None:
    runtime.state.status_seed_cancelled = True
    runtime.state.finished = True
    if runtime.status_seed_task and not runtime.status_seed_task.done():
        runtime.status_seed_task.cancel()

    await runtime.render_pump.drain()
    await runtime.render_pump.stop()
    clear_tool_status = getattr(runtime, "clear_tool_status", None)
    if clear_tool_status is not None:
        await clear_tool_status()
    display_final = generated["display_final"]
    thinking_block = generated["thinking_block"]
    final_delivery_ok = False
    if display_final == "(Empty response)" and not thinking_block:
        final_delivery_ok = True
        runtime.state.final_delivery_confirmed = True
        if runtime.state.bot_message:
            try:
                await runtime.state.bot_message.delete()
            except Exception:
                logger.debug("%s failed to delete placeholder for empty response", req["ctx"], exc_info=True)
            runtime.state.bot_message = None
    else:
        final_delivery_ok = await runtime.outbound.deliver_final(display_final)
        runtime.state.final_delivery_confirmed = final_delivery_ok

    if not runtime.state.user_message_persisted:
        add_user_message(req["session_id"], req["save_msg"])
        runtime.state.user_message_persisted = True

    has_assistant_text = generated["final_text"] != "(Empty response)"
    if final_delivery_ok and has_assistant_text:
        add_assistant_message(req["session_id"], generated["final_text"], generated.get("reasoning_content"))
        if get_session_message_count(req["session_id"]) <= 2:
            _spawn_title_task(req["user_id"], req["session_id"], req["save_msg"], generated["final_text"])
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
