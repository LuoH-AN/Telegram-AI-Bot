from __future__ import annotations

import asyncio
import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from infrastructure.ai import get_ai_client
from adapters.telegram.outbound import bind_outbound, reset_outbound
from adapters.telegram.rich_text import edit_rich_text
from adapters.telegram.rich_text import reply_rich_text
from adapters.telegram.ux.errors import error_panel
from adapters.telegram.ux.locale import language, pick
from adapters.telegram.sender import TelegramOutbound
from domain.services import add_user_message, conversation_slot, format_memories_for_prompt, get_system_prompt
from domain.services.log import record_error
from domain.services.queue import cancel_user_responses, conversation_queue_position, register_response, unregister_response
from infrastructure.config import normalize_telegram_busy_mode
from shared.utils.files import get_datetime_prompt
from shared.utils.platform import build_latex_guidance

from .generate import generate_with_tools
from .prepare import prepare_chat_request
from .render import setup_render_runtime
from .save import deliver_and_persist

logger = logging.getLogger(__name__)


def _cancel_previous_responses(chat_id: int, user_id: int, settings: dict, ctx: str) -> list[str]:
    if normalize_telegram_busy_mode(settings.get("busy_mode")) != "interrupt":
        return []
    cancelled = cancel_user_responses(chat_id, user_id, platform="telegram")
    if cancelled:
        logger.info("%s cancelled %d active Telegram response(s)", ctx, len(cancelled))
    return cancelled


def _build_messages(req: dict) -> list[dict]:
    system_prompt = get_system_prompt(req["user_id"], req["persona_name"])
    memory_prompt = format_memories_for_prompt(req["user_id"], req.get("user_content"))
    if memory_prompt:
        system_prompt += "\n\n" + memory_prompt
    system_prompt += "\n\n" + get_datetime_prompt() + build_latex_guidance()
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(req["conversation"])
    if not req.get("retry_existing"):
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
    retry_existing: bool = False,
) -> None:
    req = await prepare_chat_request(
        update,
        context,
        user_content=user_content,
        save_msg=save_msg,
        frozen_persona_name=frozen_persona_name,
        frozen_session_id=frozen_session_id,
        retry_existing=retry_existing,
    )
    if req is None:
        return
    runtime = await setup_render_runtime(
        update,
        context,
        bot_message,
        req["ctx"],
        tool_progress_mode=req["settings"].get("tool_progress"),
    )
    runtime.state.user_message_persisted = retry_existing
    context.user_data["ux_last_retry"] = {
        "user_content": req["user_content"],
        "save_msg": req["save_msg"],
        "persona_name": req["persona_name"],
        "session_id": req["session_id"],
    }
    _cancel_previous_responses(
        update.effective_chat.id,
        req["user_id"],
        req["settings"],
        req["ctx"],
    )
    request_token = update.effective_message.message_id or int(time.time() * 1000)
    conversation_key = f"telegram:{update.effective_chat.id}:{req['user_id']}:{req['session_id']}"
    response_key = f"{conversation_key}:{request_token}"
    current_task = asyncio.current_task()
    if current_task:
        register_response(response_key, task=current_task, pump=runtime.render_pump)
    outbound_token = bind_outbound(TelegramOutbound(update, context))
    try:
        queue_position = await conversation_queue_position(conversation_key)
        if queue_position:
            await runtime.status_update(
                pick(
                    language(update, context),
                    f"前面还有 {queue_position} 个请求，当前请求已排队。可点击下方按钮取消。",
                    f"{queue_position} request(s) ahead. This request is queued; use the button below to cancel.",
                )
            )
        async with conversation_slot(conversation_key):
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
        runtime.state.status_seed_cancelled = True
        runtime.status_seed_task.cancel()
        runtime.render_pump.force_stop()
        await runtime.clear_tool_status()
        try:
            if not runtime.state.user_message_persisted:
                add_user_message(req["session_id"], req["save_msg"])
                runtime.state.user_message_persisted = True
        except Exception:
            logger.debug("%s failed to persist user message after cancellation", req["ctx"], exc_info=True)
        if not runtime.state.final_delivery_confirmed and runtime.state.bot_message:
            try:
                runtime.state.finished = True
                await edit_rich_text(runtime.state.bot_message, pick(language(update, context), "（已停止生成）", "(Generation stopped)"), reply_markup=None)
            except Exception:
                pass
    except Exception as exc:
        logger.exception("%s AI API error", req["ctx"])
        runtime.state.status_seed_cancelled = True
        runtime.status_seed_task.cancel()
        try:
            await runtime.render_pump.stop()
        except Exception:
            logger.debug("%s failed to stop render pump during error handling", req["ctx"], exc_info=True)
        await runtime.clear_tool_status()
        if not runtime.state.final_delivery_confirmed:
            runtime.state.finished = True
            error_text, keyboard = error_panel(exc, language(update, context), user_id=req["user_id"])
            if runtime.state.bot_message:
                await edit_rich_text(runtime.state.bot_message, error_text, reply_markup=keyboard)
            else:
                runtime.state.bot_message = await reply_rich_text(update.effective_message, error_text, reply_markup=keyboard)
            try:
                if not runtime.state.user_message_persisted:
                    add_user_message(req["session_id"], req["save_msg"])
                    runtime.state.user_message_persisted = True
            except Exception:
                logger.debug("%s failed to persist user message after error", req["ctx"], exc_info=True)
        record_error(req["user_id"], str(exc), "chat handler", req["settings"].get("model"), req["persona_name"])
    finally:
        runtime.state.status_seed_cancelled = True
        runtime.status_seed_task.cancel()
        reset_outbound(outbound_token)
        unregister_response(response_key)
        try:
            await runtime.render_pump.stop()
        except Exception:
            logger.debug("%s failed to stop render pump in finally", req["ctx"], exc_info=True)
