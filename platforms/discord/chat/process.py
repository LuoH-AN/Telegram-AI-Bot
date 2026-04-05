"""Discord chat message processing with streaming/tool-calls."""

from __future__ import annotations

import asyncio
import time

import discord
from discord.ext import commands

from services import conversation_slot, get_system_prompt
from services.log import record_error
from services.runtime_queue import cancel_user_responses, register_response, unregister_response
from utils import get_datetime_prompt
from utils.platform_parity import build_latex_guidance, build_retry_message

from ..config import logger
from .finalize import finalize_chat_result
from .preflight import run_preflight
from .runtime import ChatRuntime
from .stream_loop import run_stream_loop

async def process_chat_message(bot: commands.Bot, message: discord.Message) -> None:
    req = await run_preflight(bot, message)
    if req is None:
        return
    try:
        await message.add_reaction("👁️")
    except Exception:
        pass
    runtime = ChatRuntime(message, log_ctx=req.log_ctx)
    cancelled = cancel_user_responses(message.channel.id, req.user_id, platform="discord")
    if cancelled:
        logger.info("%s cancelled %d active Discord response(s) due to new incoming message", req.log_ctx, len(cancelled))
    request_token = message.id or int(time.time() * 1000)
    slot_key = f"discord:{message.channel.id}:{req.user_id}:{req.session_id}:{request_token}"
    slot_cm = conversation_slot(slot_key)
    was_queued = await slot_cm.__aenter__()
    final_delivery_confirmed = False
    try:
        current_task = asyncio.current_task()
        if current_task:
            register_response(slot_key, task=current_task, pump=runtime.render_pump)
        if was_queued:
            await runtime.status_update("Previous request is still running. Queued and starting soon...")
        system_prompt = get_system_prompt(req.user_id, req.persona_name) + "\n\n" + get_datetime_prompt() + build_latex_guidance()
        messages: list[dict] = [{"role": "system", "content": system_prompt}] + list(req.conversation) + [{"role": "user", "content": req.user_content}]
        result = await run_stream_loop(
            user_id=req.user_id,
            log_ctx=req.log_ctx,
            settings=req.settings,
            messages=messages,
            reasoning_effort=req.reasoning_effort,
            stream_mode=req.stream_mode,
            show_thinking=req.show_thinking,
            runtime=runtime,
        )
        final_delivery_confirmed = await finalize_chat_result(
            log_ctx=req.log_ctx,
            runtime=runtime,
            result=result,
            user_id=req.user_id,
            session_id=req.session_id,
            save_msg=req.save_msg,
            persona_name=req.persona_name,
            settings=req.settings,
            request_start=req.request_start,
        )
    except asyncio.CancelledError:
        logger.info("%s response cancelled by !stop", req.log_ctx)
        try:
            runtime.render_pump.force_stop()
        except Exception:
            pass
        if not final_delivery_confirmed and runtime.bot_message:
            try:
                await runtime.bot_message.edit(content="(Response stopped)")
            except Exception:
                pass
    except Exception as e:
        logger.exception("%s AI API error", req.log_ctx)
        try:
            await runtime.render_pump.stop()
        except Exception:
            pass
        if not final_delivery_confirmed:
            await runtime.outbound.deliver_final(build_retry_message())
        record_error(req.user_id, str(e), "discord chat handler", req.settings.get("model"), req.persona_name)
    finally:
        unregister_response(slot_key)
        try:
            await runtime.render_pump.stop()
        except Exception:
            pass
        await slot_cm.__aexit__(None, None, None)


def stop_active_chat(*, channel_id: int, user_id: int) -> int:
    cancelled = cancel_user_responses(channel_id, user_id, platform="discord")
    return len(cancelled)
