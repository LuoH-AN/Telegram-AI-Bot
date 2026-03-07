"""Text message handler with streaming output.

This module is the main orchestrator for the AI chat loop.  The heavy
lifting is delegated to sub-modules:

- ``streaming``      – AI response streaming engine
- ``tool_dispatch``  – tool call execution, dedup, status animation
- ``delivery``       – pending voice / screenshot delivery
"""

import asyncio
import logging
import time

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import (
    MAX_MESSAGE_LENGTH,
    STREAM_UPDATE_MODE,
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
)
from services.log_service import record_ai_interaction, record_error
from tools import (
    get_all_tools,
    get_tool_instructions,
    enrich_system_prompt,
    post_process_response,
)
from ai import get_ai_client, ToolCall
from cache import cache
from utils import (
    filter_thinking_content,
    parse_raw_tool_calls,
    send_message_safe,
    edit_message_safe,
    get_datetime_prompt,
    ChatEventPump,
    StreamOutboundAdapter,
)
from utils.ai_helpers import (
    estimate_tokens as _estimate_tokens,
    estimate_tokens_str as _estimate_tokens_str,
    tool_dedup_key as _tool_dedup_key,
)
from handlers.common import should_respond_in_group, get_log_context
from utils.platform_parity import (
    build_api_key_required_message,
    build_latex_guidance,
    build_retry_message,
    build_token_limit_reached_message,
    format_log_context,
)

from .streaming import stream_response, stable_text_before_tool_call
from .tool_dispatch import (
    MAX_TOOL_ROUNDS,
    build_tool_status_lines,
    build_empty_response_fallback,
    execute_tool_round,
    collect_tool_error_snippets,
)
from .delivery import deliver_pending_voices, deliver_pending_screenshots

logger = logging.getLogger(__name__)

VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


def _normalize_reasoning_effort(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in VALID_REASONING_EFFORTS else ""


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE, *,
               user_content=None, save_msg=None, bot_message=None,
               frozen_persona_name: str | None = None,
               frozen_session_id: int | None = None) -> None:
    """Handle chat messages with streaming output.

    Can be called from photo/document handlers with pre-processed content:
      user_content: str or list[dict] to send to the AI
      save_msg: text to store in conversation history
      bot_message: existing placeholder message to update
    """
    internal_call = user_content is not None

    if not internal_call:
        if not await should_respond_in_group(update, context):
            return
        if update.message.forward_origin:
            return

    user_id = update.effective_user.id
    ctx = get_log_context(update)

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
    enabled_tools = settings.get("enabled_tools", "memory,search,fetch,wikipedia,tts")

    if not internal_call:
        if not has_api_key(user_id):
            await update.message.reply_text(build_api_key_required_message("/"))
            return

    # Freeze persona/session snapshot for this request
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
        bot_message = await update.message.reply_text("…")

    # --- Set up streaming output plumbing ---
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
        empty_placeholder_text="…",
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
        if was_queued:
            await _status_update("Previous request is still running. Queued and starting soon...")

        client = get_ai_client(user_id)
        request_start = time.monotonic()

        # --- Build system prompt ---
        system_prompt = get_system_prompt(user_id, persona_name)
        system_prompt += "\n\n" + get_datetime_prompt()

        if isinstance(user_content, str):
            query_text = user_content
        elif isinstance(user_content, list):
            query_text = next(
                (p["text"] for p in user_content if isinstance(p, dict) and p.get("type") == "text"),
                save_msg or "",
            )
        else:
            query_text = save_msg or ""

        system_prompt = enrich_system_prompt(
            user_id, system_prompt, enabled_tools=enabled_tools, query=query_text
        )
        system_prompt += get_tool_instructions(enabled_tools=enabled_tools)
        system_prompt += build_latex_guidance()

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation)
        messages.append({"role": "user", "content": user_content})

        tools = get_all_tools(enabled_tools=enabled_tools)

        # --- Accumulate token usage across rounds ---
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_thinking_seconds = 0

        user_stream_mode = settings.get("stream_mode", "") or STREAM_UPDATE_MODE
        user_reasoning_effort = _normalize_reasoning_effort(settings.get("reasoning_effort", ""))

        # --- Tool call loop ---
        last_text_response = ""
        seen_tool_keys: set[str] = set()
        tool_results_pending = False
        tool_error_snippets: list[str] = []
        truncated_prefix = ""
        for round_num in range(MAX_TOOL_ROUNDS + 1):

            full_response, usage_info, tool_calls, thinking_seconds, finish_reason = await stream_response(
                client, messages, settings["model"], settings["temperature"], user_reasoning_effort,
                tools, _stream_update, _status_update,
                show_waiting=(round_num == 0),
                stream_mode=user_stream_mode,
                include_thought_prefix=True,
                stream_cursor=True,
            )
            total_thinking_seconds += thinking_seconds

            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens") or 0
                total_completion_tokens += usage_info.get("completion_tokens") or 0

            # Parse raw tool call markup from content
            if not tool_calls and full_response:
                parsed_calls, cleaned = parse_raw_tool_calls(full_response)
                if parsed_calls:
                    tool_calls = [
                        ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                        for tc in parsed_calls
                    ]
                    full_response = cleaned
                    logger.info("%s parsed %d raw tool call(s) from content", ctx, len(tool_calls))

            if full_response.strip():
                last_text_response = full_response

            if filter_thinking_content(full_response).strip():
                tool_results_pending = False

            if not tool_calls:
                if finish_reason == "length" and round_num < MAX_TOOL_ROUNDS:
                    logger.info("%s response truncated (finish_reason=length), requesting continuation", ctx)
                    truncated_text = full_response or ""
                    truncated_prefix += truncated_text
                    messages.append({"role": "assistant", "content": truncated_text})
                    messages.append({"role": "user", "content": "Please continue and complete your response concisely."})
                    continue
                break

            # Show tool call status to user
            raw_display_text = filter_thinking_content(full_response, streaming=True)
            display_text = stable_text_before_tool_call(raw_display_text)
            status_lines = build_tool_status_lines(tool_calls)
            status_text = "\n".join(status_lines)
            thinking_prefix = (
                f"_Thought for {total_thinking_seconds}s_\n\n" if total_thinking_seconds > 0 else ""
            )
            if display_text:
                await _stream_update(thinking_prefix + display_text + "\n\n" + status_text)
            else:
                await _status_update(thinking_prefix + status_text if thinking_prefix else status_text)

            # Deduplicate tool calls
            new_tool_calls = []
            dup_indices: set[int] = set()
            for i, tc in enumerate(tool_calls):
                key = _tool_dedup_key(tc)
                if key in seen_tool_keys:
                    dup_indices.add(i)
                else:
                    seen_tool_keys.add(key)
                    new_tool_calls.append(tc)
            no_new_tool_calls = not new_tool_calls and bool(tool_calls)

            # Execute tool calls
            tool_results = await execute_tool_round(
                user_id=user_id,
                tool_calls=tool_calls,
                new_tool_calls=new_tool_calls,
                dup_indices=dup_indices,
                enabled_tools=enabled_tools,
                display_text=display_text,
                thinking_prefix=thinking_prefix,
                stream_update=_stream_update,
                ctx=ctx,
            )

            if not tool_results:
                logger.warning("%s tool calls produced no results", ctx)
                break

            tool_error_snippets = collect_tool_error_snippets(tool_results, tool_error_snippets)

            # Build assistant message with tool_calls for the conversation
            visible_content = filter_thinking_content(full_response).strip() or None
            assistant_msg = {
                "role": "assistant",
                "content": visible_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)
            messages.extend(tool_results)
            tool_results_pending = True
            if no_new_tool_calls:
                logger.info(
                    "%s no new executable tool calls in round %d; forcing final response without tools",
                    ctx,
                    round_num + 1,
                )
                break

        # Force a final text response if tool results are still pending
        if tool_results_pending:
            logger.info("%s tool results pending, retrying without tools", ctx)
            messages.append({
                "role": "user",
                "content": (
                    "Please respond to the user based on the information you have gathered above. "
                    "Do not attempt to call any more tools. "
                    "Provide a complete final answer and do not end mid-sentence."
                ),
            })
            full_response, usage_info, _, thinking_seconds, _ = await stream_response(
                client, messages, settings["model"], settings["temperature"], user_reasoning_effort,
                None, _stream_update, _status_update,
                show_waiting=False,
                stream_mode=user_stream_mode,
                include_thought_prefix=True,
                stream_cursor=True,
            )
            total_thinking_seconds += thinking_seconds
            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens") or 0
                total_completion_tokens += usage_info.get("completion_tokens") or 0
            if full_response.strip():
                last_text_response = full_response

        # --- Deliver pending media ---
        await deliver_pending_voices(update, user_id)
        await deliver_pending_screenshots(update, user_id)

        # --- Build and deliver final response ---
        combined_response = truncated_prefix + full_response if truncated_prefix else full_response
        final_text = filter_thinking_content(combined_response)

        if not final_text and last_text_response:
            final_text = filter_thinking_content(last_text_response)

        final_text = post_process_response(user_id, final_text, enabled_tools=enabled_tools).strip()

        if not final_text:
            logger.warning(
                "%s model returned empty visible response (tool_calls=%d tool_errors=%d last_text_len=%d truncated_len=%d)",
                ctx,
                len(seen_tool_keys),
                len(tool_error_snippets),
                len(last_text_response),
                len(truncated_prefix),
            )
            final_text = build_empty_response_fallback(tool_error_snippets)

        thinking_prefix = (
            f"_Thought for {total_thinking_seconds}s_\n\n" if total_thinking_seconds > 0 else ""
        )
        display_final = thinking_prefix + final_text

        await render_pump.drain()
        await render_pump.stop()
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

        # --- Record token usage ---
        if not total_prompt_tokens and not total_completion_tokens:
            total_prompt_tokens = _estimate_tokens(messages)
            total_completion_tokens = _estimate_tokens_str(final_text)
        if total_prompt_tokens or total_completion_tokens:
            add_token_usage(
                user_id, total_prompt_tokens, total_completion_tokens, persona_name=persona_name
            )

        # --- Record AI interaction log ---
        latency_ms = int((time.monotonic() - request_start) * 1000)
        tool_name_list = list({k.split(":")[0] for k in seen_tool_keys}) if seen_tool_keys else None
        record_ai_interaction(
            user_id, settings["model"], total_prompt_tokens, total_completion_tokens,
            total_prompt_tokens + total_completion_tokens, tool_name_list, latency_ms, persona_name,
        )

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
        try:
            await render_pump.stop()
        except Exception:
            logger.debug("%s failed to stop render pump in finally", ctx, exc_info=True)
        await slot_cm.__aexit__(None, None, None)


async def _generate_and_set_title(user_id: int, session_id: int, user_message: str, ai_response: str) -> None:
    """Generate and set a title for a session (runs as background task)."""
    try:
        title = await generate_session_title(user_id, user_message, ai_response)
        if title:
            cache.update_session_title(session_id, title)
            sctx = format_log_context(platform="telegram", user_id=user_id, scope="system", chat_id=0)
            logger.info("%s auto-generated session title: %s", sctx, title)
    except Exception as e:
        sctx = format_log_context(platform="telegram", user_id=user_id, scope="system", chat_id=0)
        logger.warning("%s failed to auto-generate title: %s", sctx, e)
