from __future__ import annotations

import asyncio
import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from ai import get_ai_client
from services import conversation_slot, get_system_prompt
from services.log import record_error
from services.runtime_queue import cancel_user_responses, register_response, unregister_response
from utils import get_datetime_prompt
from utils.platform_parity import build_latex_guidance, build_retry_message

from .generation import generate_with_tools
from .persistence import deliver_and_persist
from .preflight import prepare_chat_request
from .rendering import setup_render_runtime
logger = logging.getLogger(__name__)

def _build_messages(req: dict) -> list[dict]:
    system_prompt = get_system_prompt(req["user_id"], req["persona_name"])
    system_prompt += "\n\n" + get_datetime_prompt() + build_latex_guidance()
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(req["conversation"])
    messages.append({"role": "user", "content": req["user_content"]})
    return messages
async def chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_content=None,
    save_msg=None,
    bot_message=None,
    frozen_persona_name: str | None = None,
    frozen_session_id: int | None = None,
) -> None:
    req = await prepare_chat_request(
        update,
        context,
        user_content=user_content,
        save_msg=save_msg,
        frozen_persona_name=frozen_persona_name,
        frozen_session_id=frozen_session_id,
    )
    if req is None:
        return
    runtime = await setup_render_runtime(update, bot_message, req["ctx"])
    cancelled = cancel_user_responses(update.effective_chat.id, req["user_id"], platform="telegram")
    if cancelled:
        logger.info("%s cancelled %d active Telegram response(s) due to new incoming message", req["ctx"], len(cancelled))
    request_token = update.message.message_id or int(time.time() * 1000)
    slot_key = f"telegram:{update.effective_chat.id}:{req['user_id']}:{req['session_id']}:{request_token}"
    slot_cm = conversation_slot(slot_key)
    was_queued = await slot_cm.__aenter__()
    try:
        current_task = asyncio.current_task()
        if current_task:
            register_response(slot_key, task=current_task, pump=runtime.render_pump)
        if was_queued:
            await runtime.status_update("Previous request is still running. Queued and starting soon...")
        client = get_ai_client(req["user_id"])
        request_start = time.monotonic()
        generated = await generate_with_tools(
            client=client,
            messages=_build_messages(req),
            settings=req["settings"],
            user_id=req["user_id"],
            ctx=req["ctx"],
            runtime=runtime,
        )
        await deliver_and_persist(generated=generated, runtime=runtime, req=req, request_start=request_start)
    except asyncio.CancelledError:
        logger.info("%s response cancelled by /stop", req["ctx"])
        runtime.render_pump.force_stop()
        if not runtime.state.final_delivery_confirmed and runtime.state.bot_message:
            try:
                await runtime.state.bot_message.edit_text("(Response stopped)")
            except Exception:
                pass
    except Exception as exc:
        logger.exception("%s AI API error", req["ctx"])
        try:
            await runtime.render_pump.stop()
        except Exception:
            logger.debug("%s failed to stop render pump during error handling", req["ctx"], exc_info=True)
        if not runtime.state.final_delivery_confirmed:
            await runtime.outbound.deliver_final(build_retry_message())
        record_error(req["user_id"], str(exc), "chat handler", req["settings"].get("model"), req["persona_name"])
    finally:
        runtime.state.status_seed_cancelled = True
        runtime.status_seed_task.cancel()
        unregister_response(slot_key)
        try:
            await runtime.render_pump.stop()
        except Exception:
            logger.debug("%s failed to stop render pump in finally", req["ctx"], exc_info=True)
        await slot_cm.__aexit__(None, None, None)
