"""Finalize Discord chat result: deliver, persist, and meter usage."""

from __future__ import annotations

import asyncio
import time

from services import add_assistant_message, add_token_usage, add_user_message, get_session_message_count
from services.log import record_ai_interaction
from utils import filter_thinking_content, format_thinking_block
from utils.ai_helpers import estimate_tokens as _estimate_tokens
from utils.ai_helpers import estimate_tokens_str as _estimate_tokens_str

from ..config import SHOW_THINKING_MAX_CHARS, logger
from .title import generate_and_set_title


async def finalize_chat_result(
    *,
    log_ctx: str,
    runtime,
    result: dict,
    user_id: int,
    session_id: int,
    save_msg: str,
    persona_name: str,
    settings: dict,
    request_start: float,
) -> bool:
    combined_response = result["final_text_raw"]
    last_text_response = result["last_text_response"]
    final_text = filter_thinking_content(combined_response).strip()
    if not final_text and last_text_response:
        final_text = filter_thinking_content(last_text_response).strip()
    if not final_text:
        logger.warning("%s model returned empty visible response", log_ctx)
        final_text = "(Empty response)"
    thinking_block = ""
    if settings.get("show_thinking") and result["thinking_segments"]:
        thinking_text = "\n\n".join(result["thinking_segments"]).strip()
        thinking_block = format_thinking_block(thinking_text, seconds=result["thinking_seconds"], max_chars=SHOW_THINKING_MAX_CHARS)
    display_final = thinking_block + final_text if thinking_block else final_text
    await runtime.render_pump.drain()
    await runtime.render_pump.stop()
    final_delivery_ok = await runtime.outbound.deliver_final(display_final)
    if final_delivery_ok:
        add_user_message(session_id, save_msg)
        add_assistant_message(session_id, final_text)
        if get_session_message_count(session_id) <= 2:
            asyncio.create_task(generate_and_set_title(user_id, session_id, save_msg, final_text))
    else:
        logger.error("%s final response was not delivered (stream_ack=%d/%d); skip conversation persistence", log_ctx, runtime.outbound.stream_successes, runtime.outbound.stream_attempts)
    prompt_tokens = result["prompt_tokens"] or _estimate_tokens(result["messages"])
    completion_tokens = result["completion_tokens"] or _estimate_tokens_str(final_text)
    if prompt_tokens or completion_tokens:
        add_token_usage(user_id, prompt_tokens, completion_tokens, persona_name=persona_name)
    latency_ms = int((time.monotonic() - request_start) * 1000)
    record_ai_interaction(
        user_id,
        settings["model"],
        prompt_tokens,
        completion_tokens,
        prompt_tokens + completion_tokens,
        None,
        latency_ms,
        persona_name,
    )
    return final_delivery_ok
