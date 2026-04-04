"""Text message handler with streaming output."""

import asyncio
import logging
import re
import time

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import (
    MAX_MESSAGE_LENGTH,
    STREAM_UPDATE_MODE,
    VALID_REASONING_EFFORTS,
    SHOW_THINKING_MAX_CHARS,
)
from services import (
    get_user_settings,
    ensure_session,
    get_conversation,
    add_user_message,
    add_assistant_message,
    add_token_usage,
    has_api_key,
    get_system_prompt,
    get_remaining_tokens,
    get_current_persona_name,
    get_session_message_count,
    generate_session_title,
    conversation_slot,
    handle_skill_command,
    ensure_skill_terminal,
    call_skill,
)
from services.log import record_ai_interaction, record_error
from services.refresh import ensure_user_state
from services.runtime_queue import register_response, unregister_response
from ai import get_ai_client
from cache import cache
from utils import (
    filter_thinking_content,
    extract_thinking_blocks,
    format_thinking_block,
    send_message_safe,
    edit_message_safe,
    get_datetime_prompt,
    ChatEventPump,
    StreamOutboundAdapter,
)
from utils.ai_helpers import (
    estimate_tokens as _estimate_tokens,
    estimate_tokens_str as _estimate_tokens_str,
)
from handlers.common import should_respond_in_group, get_log_context
from utils.platform_parity import (
    build_api_key_required_message,
    build_latex_guidance,
    build_retry_message,
    build_token_limit_reached_message,
    format_log_context,
)

from .streaming import stream_response

logger = logging.getLogger(__name__)

def _make_thinking_prefix(seconds: int | float) -> str:
    if seconds > 0:
        return f"_Thinking for {int(seconds)}s_\n\n"
    return ""


def _normalize_reasoning_effort(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in VALID_REASONING_EFFORTS else ""


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE, *,
               user_content=None, save_msg=None, bot_message=None,
               frozen_persona_name: str | None = None,
               frozen_session_id: int | None = None) -> None:
    internal_call = user_content is not None

    if not internal_call:
        if not await should_respond_in_group(update, context):
            return
        if update.message.forward_origin:
            return

    user_id = update.effective_user.id
    ctx = get_log_context(update)
    ensure_user_state(user_id)

    if not internal_call:
        user_message = update.message.text
        logger.info("%s text: %s", ctx, user_message[:80])

        bot_username = context.bot.username
        if bot_username and f"@{bot_username}" in user_message:
            user_message = user_message.replace(f"@{bot_username}", "").strip()

        reply_msg = update.message.reply_to_message
        if reply_msg:
            quoted_text = reply_msg.text or reply_msg.caption or ""
            if quoted_text:
                sender = reply_msg.from_user
                sender_name = sender.first_name if sender else "Unknown"
                user_message = f"[Quoted message from {sender_name}]:\n{quoted_text}\n\n{user_message}"

        user_content = user_message
        save_msg = user_message
    else:
        logger.info("%s media: %s", ctx, (save_msg or "")[:80])

    settings = get_user_settings(user_id)

    if not internal_call and not has_api_key(user_id):
        await update.message.reply_text(build_api_key_required_message("/"))
        return

    persona_name = frozen_persona_name or get_current_persona_name(user_id)
    session_id = frozen_session_id or ensure_session(user_id, persona_name)
    if session_id is None:
        await update.message.reply_text(build_retry_message())
        return
    conversation = list(get_conversation(session_id))

    if not internal_call:
        remaining = get_remaining_tokens(user_id, persona_name)
        if remaining is not None and remaining <= 0:
            await update.message.reply_text(build_token_limit_reached_message("/", persona_name))
            return
        await update.message.chat.send_action(ChatAction.TYPING)
        bot_message = await update.message.reply_text("Thinking...")

    async def _edit_placeholder(text: str) -> bool:
        if bot_message is None:
            return False
        return await edit_message_safe(bot_message, text)

    async def _send_text(text: str) -> bool:
        sent_messages = await send_message_safe(update.message, text)
        return bool(sent_messages)

    async def _delete_placeholder() -> None:
        nonlocal bot_message
        if bot_message is None:
            return
        await bot_message.delete()
        bot_message = None

    outbound = StreamOutboundAdapter(
        max_message_length=MAX_MESSAGE_LENGTH,
        has_placeholder=lambda: bot_message is not None,
        edit_placeholder=_edit_placeholder,
        send_text=_send_text,
        delete_placeholder=_delete_placeholder,
        empty_placeholder_text="Thinking...",
    )

    async def _render_event(event) -> None:
        await outbound.stream_update(event.text)

    render_pump = ChatEventPump(_render_event)
    render_pump.start()

    async def _stream_update(text: str) -> bool:
        return await render_pump.emit("stream", text)

    async def _status_update(text: str) -> bool:
        return await render_pump.emit("status", text)

    slot_key = f"telegram:{update.effective_chat.id}:{user_id}:{session_id}"
    slot_cm = conversation_slot(slot_key)
    was_queued = await slot_cm.__aenter__()
    final_delivery_confirmed = False

    try:
        # Register active response for /stop cancellation
        current_task = asyncio.current_task()
        if current_task:
            register_response(slot_key, task=current_task, pump=render_pump)

        if was_queued:
            await _status_update("Previous request is still running. Queued and starting soon...")

        client = get_ai_client(user_id)
        request_start = time.monotonic()

        system_prompt = get_system_prompt(user_id, persona_name)
        system_prompt += "\n\n" + get_datetime_prompt()
        system_prompt += build_latex_guidance()

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation)
        messages.append({"role": "user", "content": user_content})

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_thinking_seconds = 0
        truncated_prefix = ""
        last_text_response = ""
        thinking_segments: list[str] = []

        user_stream_mode = settings.get("stream_mode", "") or STREAM_UPDATE_MODE
        user_reasoning_effort = _normalize_reasoning_effort(settings.get("reasoning_effort", ""))
        show_thinking = bool(settings.get("show_thinking"))

        # Get tool definitions
        from tools import get_all_tools, process_tool_calls
        tool_definitions = get_all_tools(enabled_tools="all")

        while True:
            full_response, usage_info, thinking_seconds, finish_reason, reasoning_content, tool_calls = await stream_response(
                client,
                messages,
                settings["model"],
                settings["temperature"],
                user_reasoning_effort,
                _stream_update,
                _status_update,
                show_waiting=(not truncated_prefix),
                stream_mode=user_stream_mode,
                include_thought_prefix=True,
                stream_cursor=True,
                show_thinking=show_thinking,
                thinking_max_chars=SHOW_THINKING_MAX_CHARS,
                tools=tool_definitions,
            )
            total_thinking_seconds += thinking_seconds

            if show_thinking:
                tag_thinking, _ = extract_thinking_blocks(full_response)
                for segment in (reasoning_content, tag_thinking):
                    cleaned = (segment or "").strip()
                    if not cleaned:
                        continue
                    if thinking_segments and thinking_segments[-1] == cleaned:
                        continue
                    thinking_segments.append(cleaned)

            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens") or 0
                total_completion_tokens += usage_info.get("completion_tokens") or 0

            if full_response.strip():
                last_text_response = full_response

            # Handle tool calls
            if tool_calls:
                logger.info("%s model requested %d tool calls", ctx, len(tool_calls))

                # Deliver current response first (if any)
                if full_response.strip():
                    await render_pump.drain()
                    await render_pump.stop()
                    display_text = filter_thinking_content(full_response).strip()
                    if display_text:
                        await outbound.deliver_final(display_text)

                # Execute tools
                tool_results = process_tool_calls(user_id, tool_calls, enabled_tools="all")

                # Add assistant message with tool calls
                messages.append({
                    "role": "assistant",
                    "content": full_response or "",
                    "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}} for tc in tool_calls]
                })

                # Add tool results
                for result in tool_results:
                    messages.append(result)

                # Create new message for final response
                # Delete old placeholder message if exists (from previous tool call iteration)
                if bot_message:
                    try:
                        await bot_message.delete()
                    except Exception:
                        pass
                bot_message = await update.message.reply_text("Generating response...")

                # Reset outbound adapter for new message
                async def _edit_new_placeholder(text: str) -> bool:
                    nonlocal bot_message
                    if bot_message is None:
                        return False
                    return await edit_message_safe(bot_message, text)

                async def _send_new_text(text: str) -> bool:
                    sent_messages = await send_message_safe(update.message, text)
                    return bool(sent_messages)

                async def _delete_new_placeholder() -> None:
                    nonlocal bot_message
                    if bot_message is None:
                        return
                    await bot_message.delete()
                    bot_message = None

                outbound = StreamOutboundAdapter(
                    max_message_length=MAX_MESSAGE_LENGTH,
                    has_placeholder=lambda: bot_message is not None,
                    edit_placeholder=_edit_new_placeholder,
                    send_text=_send_new_text,
                    delete_placeholder=_delete_new_placeholder,
                    empty_placeholder_text="Generating response...",
                )

                # Recreate render event handler with new outbound
                async def _render_event_new(event) -> None:
                    await outbound.stream_update(event.text)

                render_pump = ChatEventPump(_render_event_new)
                render_pump.start()

                # Continue to get final response
                continue

            if finish_reason == "length":
                logger.info("%s response truncated (finish_reason=length), requesting continuation", ctx)
                truncated_text = full_response or ""
                truncated_prefix += truncated_text
                messages.append({"role": "assistant", "content": truncated_text})
                messages.append({"role": "user", "content": "Please continue and complete your response concisely."})
                continue
            break

        combined_response = truncated_prefix + full_response if truncated_prefix else full_response
        final_text = filter_thinking_content(combined_response).strip()

        if not final_text and last_text_response:
            final_text = filter_thinking_content(last_text_response).strip()

        if not final_text:
            logger.warning("%s model returned empty visible response", ctx)
            final_text = "(Empty response)"

        thinking_block = ""
        if show_thinking and thinking_segments:
            thinking_text = "\n\n".join(thinking_segments).strip()
            thinking_block = format_thinking_block(
                thinking_text,
                seconds=total_thinking_seconds,
                max_chars=SHOW_THINKING_MAX_CHARS,
            )

        if thinking_block:
            display_final = thinking_block + final_text
        elif final_text and total_thinking_seconds > 0 and final_text != "(Empty response)":
            thinking_prefix = _make_thinking_prefix(total_thinking_seconds)
            display_final = thinking_prefix + final_text
        else:
            display_final = final_text

        await render_pump.drain()
        await render_pump.stop()

        # Skip delivery if only empty response with no thinking block
        if display_final == "(Empty response)" and not thinking_block:
            final_delivery_ok = True
            if bot_message:
                await bot_message.delete()
                bot_message = None
        else:
            final_delivery_ok = await outbound.deliver_final(display_final)
        final_delivery_confirmed = final_delivery_ok
        if final_delivery_ok:
            add_user_message(session_id, save_msg)
            add_assistant_message(session_id, final_text)

            if get_session_message_count(session_id) <= 2:
                asyncio.create_task(_generate_and_set_title(user_id, session_id, save_msg, final_text))
        else:
            logger.error(
                "%s final response was not delivered (stream_ack=%d/%d); skip conversation persistence",
                ctx,
                outbound.stream_successes,
                outbound.stream_attempts,
            )

        if not total_prompt_tokens and not total_completion_tokens:
            total_prompt_tokens = _estimate_tokens(messages)
            total_completion_tokens = _estimate_tokens_str(final_text)
        if total_prompt_tokens or total_completion_tokens:
            add_token_usage(
                user_id, total_prompt_tokens, total_completion_tokens, persona_name=persona_name
            )

        latency_ms = int((time.monotonic() - request_start) * 1000)
        record_ai_interaction(
            user_id,
            settings["model"],
            total_prompt_tokens,
            total_completion_tokens,
            total_prompt_tokens + total_completion_tokens,
            None,
            latency_ms,
            persona_name,
        )

    except asyncio.CancelledError:
        logger.info("%s response cancelled by /stop", ctx)
        try:
            render_pump.force_stop()
        except Exception:
            pass
        if not final_delivery_confirmed and bot_message:
            try:
                await bot_message.edit_text("(Response stopped)")
            except Exception:
                pass
    except Exception as e:
        logger.exception("%s AI API error", ctx)
        try:
            await render_pump.stop()
        except Exception:
            logger.debug("%s failed to stop render pump during error handling", ctx, exc_info=True)
        if not final_delivery_confirmed:
            await outbound.deliver_final(build_retry_message())
        record_error(user_id, str(e), "chat handler", settings.get("model"), persona_name)
    finally:
        unregister_response(slot_key)
        try:
            await render_pump.stop()
        except Exception:
            logger.debug("%s failed to stop render pump in finally", ctx, exc_info=True)
        await slot_cm.__aexit__(None, None, None)


async def _generate_and_set_title(user_id: int, session_id: int, user_message: str, ai_response: str) -> None:
    try:
        title = await generate_session_title(user_id, user_message, ai_response)
        if title:
            cache.update_session_title(session_id, title)
            sctx = format_log_context(platform="telegram", user_id=user_id, scope="system", chat_id=0)
            logger.info("%s auto-generated session title: %s", sctx, title)
    except Exception as e:
        sctx = format_log_context(platform="telegram", user_id=user_id, scope="system", chat_id=0)
        logger.warning("%s failed to auto-generate title: %s", sctx, e)
