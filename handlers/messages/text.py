"""Text message handler with streaming output."""

import asyncio
import io
import json
import logging
import time

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import (
    MAX_MESSAGE_LENGTH,
    STREAM_UPDATE_INTERVAL,
    STREAM_MIN_UPDATE_CHARS,
    STREAM_FORCE_UPDATE_INTERVAL,
    STREAM_UPDATE_MODE,
    STREAM_TIME_MODE_INTERVAL,
    STREAM_CHARS_MODE_INTERVAL,
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
)
from tools import (
    get_all_tools,
    process_tool_calls,
    get_tool_instructions,
    enrich_system_prompt,
    post_process_response,
    drain_pending_voice_jobs,
    drain_pending_screenshot_jobs,
)
from ai import get_ai_client, ToolCall
from utils import filter_thinking_content, parse_raw_tool_calls, send_message_safe, edit_message_safe, get_datetime_prompt
from handlers.common import should_respond_in_group, get_log_context

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
TOOL_TIMEOUT = 30  # seconds (default, may be extended by shell_exec)


def _effective_tool_timeout(tool_calls) -> int:
    """Return timeout for the handler-level wait_for.

    If any tool call is shell_exec with a custom timeout, use that (+ 5s buffer).
    Playwright tools get an extended timeout for page load + CF challenge wait.
    Otherwise fall back to the default TOOL_TIMEOUT.
    """
    _PLAYWRIGHT_TOOLS = {"page_screenshot", "page_content"}
    timeout = TOOL_TIMEOUT
    for tc in tool_calls:
        if tc.name == "shell_exec":
            try:
                args = json.loads(tc.arguments)
                requested = int(args.get("timeout", 0))
                if requested > timeout:
                    timeout = min(requested + 5, 125)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        elif tc.name in _PLAYWRIGHT_TOOLS:
            timeout = max(timeout, 60)
    return timeout

TOOL_STATUS_MAP = {
    "web_search": "🔍 Searching...",
    "url_fetch": "🌐 Fetching page...",
    "save_memory": "💾 Saving to memory...",
    "tts_speak": "🎤 Generating voice...",
    "tts_list_voices": "🎙️ Loading voices...",
    "shell_exec": "💻 Running command...",
    "cron_create": "⏰ Creating scheduled task...",
    "cron_list": "📋 Listing scheduled tasks...",
    "cron_delete": "🗑️ Deleting scheduled task...",
    "cron_run": "▶️ Running scheduled task...",
    "page_screenshot": "📸 Taking screenshot...",
    "page_content": "🌐 Extracting page content...",
}

STREAM_BOUNDARY_CHARS = set(" \n\t.,!?;:)]}，。！？；：）】」》")


def _estimate_tokens_str(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK."""
    if not text:
        return 0
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u30ff')
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4))


def _estimate_tokens(messages: list[dict]) -> int:
    """Estimate total prompt tokens from a list of messages."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            )
        total += _estimate_tokens_str(str(content)) + 4  # overhead per message
    return total


def _tool_dedup_key(tc):
    """Extract dedup key from a tool call (name + primary argument).

    For url_fetch the key is the URL (ignoring method/max_length variants).
    For web_search the key is the query.  Other tools use full arguments.
    """
    try:
        args = json.loads(tc.arguments)
    except Exception:
        return f"{tc.name}:{tc.arguments}"
    if tc.name == "url_fetch":
        return f"url_fetch:{args.get('url', '')}"
    if tc.name == "web_search":
        return f"web_search:{args.get('query', '')}"
    return f"{tc.name}:{tc.arguments}"


async def _stream_response(client, messages, model, temperature, tools, bot_message, show_waiting=True, stream_mode="default"):
    """Stream an AI response, updating bot_message in real-time.

    The synchronous OpenAI streaming iterator is wrapped with run_in_executor
    so that waiting for each chunk does not block the async event loop.

    Args:
        show_waiting: Show "Thinking for Xs" waiting indicator.  Set to False
                      on subsequent tool rounds to reduce Telegram message edits.
        stream_mode: Update mode for streaming:
                     - "default": original behavior (time + chars conditions)
                     - "time": update every second regardless of chars
                     - "chars": update every 100 chars regardless of time

    Returns:
        (full_response, usage_info, all_tool_calls, thinking_seconds, finish_reason)
    """
    loop = asyncio.get_event_loop()

    # Start the streaming request in a thread to avoid blocking
    stream = await loop.run_in_executor(
        None,
        lambda: client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            stream=True,
            tools=tools,
        ),
    )

    full_response = ""
    last_update_time = 0
    last_update_length = 0
    usage_info = None
    all_tool_calls = []
    first_chunk = True
    finish_reason = None

    # Thinking/reasoning tracking
    thinking_start_time = None
    thinking_seconds = 0
    thinking_locked = False

    # Generic waiting indicator ("Thinking for Xs" before content/reasoning arrives)
    waiting_start_time = loop.time()
    waiting_active = show_waiting

    async def _update_waiting():
        try:
            while True:
                await asyncio.sleep(1)
                if not waiting_active:
                    break
                elapsed = max(1, int(loop.time() - waiting_start_time))
                await edit_message_safe(bot_message, f"Thinking for {elapsed}s")
        except asyncio.CancelledError:
            pass

    waiting_task = asyncio.create_task(_update_waiting()) if show_waiting else None

    # Use a sentinel to detect end of iterator without StopIteration
    _end = object()
    it = iter(stream)

    while True:
        chunk = await loop.run_in_executor(None, next, it, _end)
        if chunk is _end:
            break

        if chunk.usage is not None:
            usage_info = chunk.usage

        current_time = loop.time()

        # Detect thinking/reasoning (separate field, e.g. DeepSeek R1)
        if chunk.reasoning and thinking_start_time is None:
            waiting_active = False
            thinking_start_time = current_time
            thinking_seconds = 1
            await edit_message_safe(bot_message, "Thought for 1s")
            last_update_time = current_time

        # Update thinking counter while still in thinking phase
        if thinking_start_time is not None:
            new_seconds = max(1, int(current_time - thinking_start_time))
            display_text_now = filter_thinking_content(full_response, streaming=True) if full_response else ""
            if not display_text_now and new_seconds > thinking_seconds:
                thinking_seconds = new_seconds
                if current_time - last_update_time >= 1.0:
                    await edit_message_safe(bot_message, f"Thought for {thinking_seconds}s")
                    last_update_time = current_time

        if chunk.content:
            full_response += chunk.content

            display_text = filter_thinking_content(full_response, streaming=True)

            # Detect thinking via <think> tags in content
            if not display_text and full_response.strip() and thinking_start_time is None:
                waiting_active = False
                thinking_start_time = current_time
                thinking_seconds = 1
                await edit_message_safe(bot_message, "Thought for 1s")
                last_update_time = current_time

            # Build thinking prefix for display
            thinking_prefix = ""
            if thinking_start_time is not None and display_text:
                # Lock thinking duration when visible content first appears.
                # Do not keep extending it while normal content continues streaming.
                if not thinking_locked:
                    thinking_seconds = max(1, int(current_time - thinking_start_time))
                    thinking_locked = True
                thinking_prefix = f"_Thought for {thinking_seconds}s_\n\n"

            # First visible chunk: update immediately, skip throttle interval
            if first_chunk and display_text:
                waiting_active = False
                await edit_message_safe(bot_message, thinking_prefix + display_text + " ▌")
                last_update_time = current_time
                last_update_length = len(display_text)
                first_chunk = False
            elif display_text and len(display_text) > last_update_length:
                new_chars = len(display_text) - last_update_length
                elapsed = current_time - last_update_time
                ends_with_boundary = display_text[-1] in STREAM_BOUNDARY_CHARS

                # Determine if we should update based on stream_mode
                if stream_mode == "time":
                    # Time mode: update every STREAM_TIME_MODE_INTERVAL seconds
                    should_update = elapsed >= STREAM_TIME_MODE_INTERVAL
                elif stream_mode == "chars":
                    # Chars mode: update every STREAM_CHARS_MODE_INTERVAL characters
                    should_update = new_chars >= STREAM_CHARS_MODE_INTERVAL
                else:
                    # Default mode: original behavior (time + chars OR force update)
                    should_update = (
                        (elapsed >= STREAM_UPDATE_INTERVAL and new_chars >= STREAM_MIN_UPDATE_CHARS)
                        or (elapsed >= STREAM_UPDATE_INTERVAL and ends_with_boundary)
                        or (elapsed >= STREAM_FORCE_UPDATE_INTERVAL)
                    )

                if should_update:
                    await edit_message_safe(bot_message, thinking_prefix + display_text + " ▌")
                    last_update_time = current_time
                    last_update_length = len(display_text)

        if chunk.tool_calls:
            all_tool_calls.extend(chunk.tool_calls)

        if chunk.finish_reason:
            finish_reason = chunk.finish_reason

    # Clean up waiting indicator
    waiting_active = False
    if waiting_task and not waiting_task.done():
        waiting_task.cancel()

    # Finalize thinking seconds at stream end only if no visible content ever appeared.
    if thinking_start_time is not None and not thinking_locked:
        thinking_seconds = max(1, int(loop.time() - thinking_start_time))

    return full_response, usage_info, all_tool_calls, thinking_seconds, finish_reason


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE, *,
               user_content=None, save_msg=None, bot_message=None) -> None:
    """Handle chat messages with streaming output.

    Can be called from photo/document handlers with pre-processed content:
      user_content: str or list[dict] to send to the AI
      save_msg: text to store in conversation history
      bot_message: existing placeholder message to update
    """
    internal_call = user_content is not None

    if not internal_call:
        # In groups, only respond when replied to or mentioned
        if not await should_respond_in_group(update, context):
            return

        # Skip forwarded messages (user can reply to them to trigger a response)
        if update.message.forward_origin:
            return

    user_id = update.effective_user.id
    ctx = get_log_context(update)

    if not internal_call:
        user_message = update.message.text
        logger.info("%s text: %s", ctx, user_message[:80])

        # Remove bot mention from message if present
        bot_username = context.bot.username
        if bot_username and f"@{bot_username}" in user_message:
            user_message = user_message.replace(f"@{bot_username}", "").strip()

        # Include quoted message content when replying to a message
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
        # Check if API key is set
        if not has_api_key(user_id):
            await update.message.reply_text(
                "Please set your OpenAI API key first:\n/set api_key YOUR_API_KEY"
            )
            return

    # Freeze persona/session snapshot for this request to avoid cross-session writes.
    persona_name = get_current_persona_name(user_id)
    session_id = ensure_session(user_id, persona_name)
    if session_id is None:
        await update.message.reply_text("Error. Please retry.")
        return
    conversation = list(get_conversation(session_id))

    if not internal_call:
        # Check token limit (per-persona)
        remaining = get_remaining_tokens(user_id, persona_name)
        if remaining is not None and remaining <= 0:
            await update.message.reply_text(
                f"Persona '{persona_name}' 已达到 token 上限。\n"
                "使用 /usage 查看用量，或 /set token_limit <数字> 调整上限。"
            )
            return

        # Show typing indicator
        await update.message.chat.send_action(ChatAction.TYPING)

        # Send initial placeholder message
        bot_message = await update.message.reply_text("…")

    try:
        client = get_ai_client(user_id)
        request_start = time.monotonic()

        # Build system prompt from current persona
        system_prompt = get_system_prompt(user_id)
        system_prompt += "\n\n" + get_datetime_prompt()

        # Derive query text for memory enrichment
        if isinstance(user_content, str):
            query_text = user_content
        elif isinstance(user_content, list):
            query_text = next(
                (p["text"] for p in user_content if isinstance(p, dict) and p.get("type") == "text"),
                save_msg or "",
            )
        else:
            query_text = save_msg or ""

        # Let tools enrich system prompt (e.g. inject memories via vector search)
        system_prompt = enrich_system_prompt(
            user_id, system_prompt, enabled_tools=enabled_tools, query=query_text
        )

        # Add tool instructions (fallback hints)
        system_prompt += get_tool_instructions(enabled_tools=enabled_tools)

        # Instruct AI to avoid LaTeX (Telegram cannot render it)
        system_prompt += (
            "\n\nIMPORTANT: Do NOT use LaTeX math notation ($...$ or $$...$$) in your responses. "
            "Telegram cannot render LaTeX. Instead, use plain text and Unicode symbols for math: "
            "use × instead of \\times, ÷ instead of \\div, √ instead of \\sqrt, "
            "use a/b instead of \\frac{a}{b}, use superscript characters (²³) and subscript characters (₁₂) when possible, "
            "use → ≤ ≥ ≠ ≈ ∞ π α β etc. directly."
        )

        # Build messages with system prompt
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation)
        messages.append({"role": "user", "content": user_content})

        # Get tool definitions
        tools = get_all_tools(enabled_tools=enabled_tools)

        # Accumulate token usage across rounds
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_thinking_seconds = 0

        # Get user's stream_mode setting (default/time/chars)
        user_stream_mode = settings.get("stream_mode", "") or STREAM_UPDATE_MODE

        # Tool call loop: stream response, process tools, re-call if needed
        last_text_response = ""  # fallback if final round is empty
        seen_tool_keys = set()   # dedup: prevent re-executing the same operation
        tool_results_pending = False
        truncated_prefix = ""    # accumulated text from truncated responses
        for round_num in range(MAX_TOOL_ROUNDS + 1):

            full_response, usage_info, tool_calls, thinking_seconds, finish_reason = await _stream_response(
                client, messages, settings["model"], settings["temperature"],
                tools, bot_message, show_waiting=(round_num == 0),
                stream_mode=user_stream_mode,
            )
            total_thinking_seconds += thinking_seconds

            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens") or 0
                total_completion_tokens += usage_info.get("completion_tokens") or 0

            # Parse raw tool call markup from content (some models output
            # tool calls as text instead of using the API tool_calls field)
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

            # Clear tool_results_pending only when we get visible (non-thinking) content
            if filter_thinking_content(full_response).strip():
                tool_results_pending = False

            if not tool_calls:
                # If response was truncated (output token limit), ask the model to continue
                if finish_reason == "length" and round_num < MAX_TOOL_ROUNDS:
                    logger.info("%s response truncated (finish_reason=length), requesting continuation", ctx)
                    truncated_text = full_response or ""
                    truncated_prefix += truncated_text
                    messages.append({"role": "assistant", "content": truncated_text})
                    messages.append({"role": "user", "content": "Please continue and complete your response concisely."})
                    continue
                break

            # Show tool call status to user
            display_text = filter_thinking_content(full_response, streaming=True)
            tool_names = [tc.name for tc in tool_calls]
            status_lines = [
                TOOL_STATUS_MAP.get(name, f"⚙️ Running {name}...")
                for name in tool_names
            ]
            status_text = "\n".join(status_lines)
            thinking_prefix = f"_Thought for {total_thinking_seconds}s_\n\n" if total_thinking_seconds > 0 else ""
            if display_text:
                await edit_message_safe(bot_message, thinking_prefix + display_text + "\n\n" + status_text)
            else:
                await edit_message_safe(bot_message, thinking_prefix + status_text)

            # Deduplicate tool calls (same tool + same primary argument)
            new_tool_calls = []
            dup_indices = set()
            for i, tc in enumerate(tool_calls):
                key = _tool_dedup_key(tc)
                if key in seen_tool_keys:
                    dup_indices.add(i)
                else:
                    seen_tool_keys.add(key)
                    new_tool_calls.append(tc)

            # Execute only non-duplicate tool calls
            if new_tool_calls:
                effective_timeout = _effective_tool_timeout(new_tool_calls)

                # Animate status message while tools run
                _anim_active = True
                async def _animate_tool_status():
                    elapsed = 0
                    try:
                        while _anim_active:
                            await asyncio.sleep(2)
                            if not _anim_active:
                                break
                            elapsed += 2
                            lines = []
                            for name in tool_names:
                                base = TOOL_STATUS_MAP.get(name, f"⚙️ Running {name}...")
                                lines.append(f"{base} ({elapsed}s)")
                            animated_text = "\n".join(lines)
                            if display_text:
                                await edit_message_safe(bot_message, thinking_prefix + display_text + "\n\n" + animated_text)
                            else:
                                await edit_message_safe(bot_message, thinking_prefix + animated_text)
                    except asyncio.CancelledError:
                        pass

                anim_task = asyncio.create_task(_animate_tool_status())

                try:
                    executed_results = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: process_tool_calls(user_id, new_tool_calls, enabled_tools=enabled_tools)
                        ),
                        timeout=effective_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning("%s tool timeout after %ds", ctx, effective_timeout)
                    # Feed timeout error back as tool results so the AI can respond
                    executed_results = [
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Error: Tool execution timed out after {effective_timeout}s.",
                        }
                        for tc in new_tool_calls
                    ]
                finally:
                    _anim_active = False
                    anim_task.cancel()
            else:
                executed_results = []

            # Merge results in tool_calls order (dupes get immediate response)
            tool_results = []
            exec_idx = 0
            for i, tc in enumerate(tool_calls):
                if i in dup_indices:
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "Already called with the same target. The result is in the conversation above. Please use it directly.",
                    })
                else:
                    tool_results.append(executed_results[exec_idx])
                    exec_idx += 1

            if not tool_results:
                logger.warning("%s tool calls produced no results", ctx)
                break

            # Build assistant message with tool_calls for the conversation
            # Strip thinking content — sending <think> tags back as content
            # confuses models into believing they already responded.
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

        # If loop exhausted while AI was still calling tools, tool results
        # are in messages but the AI never got to process them.
        # Make one final call WITHOUT tools to force a proper text response.
        if tool_results_pending:
            logger.info("%s tool results pending, retrying without tools", ctx)
            messages.append({
                "role": "user",
                "content": "Please respond to the user based on the information you have gathered above. Do not attempt to call any more tools.",
            })
            full_response, usage_info, _, thinking_seconds, _ = await _stream_response(
                client, messages, settings["model"], settings["temperature"],
                None, bot_message, show_waiting=False,
                stream_mode=user_stream_mode,
            )
            total_thinking_seconds += thinking_seconds
            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens") or 0
                total_completion_tokens += usage_info.get("completion_tokens") or 0
            if full_response.strip():
                last_text_response = full_response

        # Deliver pending voice messages generated by tts tool
        pending_voices = drain_pending_voice_jobs(user_id)
        for idx, job in enumerate(pending_voices, 1):
            audio_data = job.get("audio")
            if not audio_data:
                continue

            voice_file = io.BytesIO(audio_data)
            voice_file.name = job.get("filename", f"tts_{idx}.ogg")

            try:
                await update.message.reply_voice(
                    voice=voice_file,
                    caption=job.get("caption"),
                )
            except Exception:
                logger.exception("Failed to send pending tts voice")

        # Deliver pending screenshots from playwright tool
        pending_screenshots = drain_pending_screenshot_jobs(user_id)
        for idx, job in enumerate(pending_screenshots, 1):
            image_data = job.get("image")
            if not image_data:
                continue
            photo_file = io.BytesIO(image_data)
            photo_file.name = job.get("filename", f"screenshot_{idx}.png")
            try:
                await update.message.reply_photo(
                    photo=photo_file,
                    caption=job.get("caption"),
                )
            except Exception:
                logger.exception("Failed to send pending screenshot")

        # Final update with complete response
        # If there was a truncated response followed by continuation, combine them
        combined_response = truncated_prefix + full_response if truncated_prefix else full_response
        final_text = filter_thinking_content(combined_response)

        # Fall back to earlier round's text if final round was empty (e.g. after tool calls)
        if not final_text and last_text_response:
            final_text = filter_thinking_content(last_text_response)

        # Post-process response (e.g. regex fallback for memory extraction)
        final_text = post_process_response(user_id, final_text, enabled_tools=enabled_tools)

        if not final_text:
            final_text = "(Empty response)"

        # Build display text with thinking duration prefix (italic)
        thinking_prefix = f"_Thought for {total_thinking_seconds}s_\n\n" if total_thinking_seconds > 0 else ""
        display_final = thinking_prefix + final_text

        # Check if response exceeds single message limit
        if len(display_final) > MAX_MESSAGE_LENGTH:
            # Delete the placeholder and send multiple messages
            await bot_message.delete()
            await send_message_safe(update.message, display_final)
        else:
            success = await edit_message_safe(bot_message, display_final)
            if not success:
                # Edit failed (likely rate-limited after many tool rounds),
                # fall back to a new message so the user always gets a response.
                try:
                    await bot_message.delete()
                except Exception:
                    pass
                await send_message_safe(update.message, display_final)

        # Save conversation to database (clean text without thinking prefix)
        add_user_message(session_id, save_msg)
        add_assistant_message(session_id, final_text)

        # Auto-generate session title after first exchange
        if get_session_message_count(session_id) <= 2:
            asyncio.create_task(_generate_and_set_title(user_id, session_id, save_msg, final_text))

        # Record token usage if available
        # If the API didn't return usage (many providers ignore stream_options),
        # estimate from message content so usage is never zero.
        if not total_prompt_tokens and not total_completion_tokens:
            total_prompt_tokens = _estimate_tokens(messages)
            total_completion_tokens = _estimate_tokens_str(final_text)
        if total_prompt_tokens or total_completion_tokens:
            add_token_usage(
                user_id, total_prompt_tokens, total_completion_tokens, persona_name=persona_name
            )

        # Record AI interaction log
        latency_ms = int((time.monotonic() - request_start) * 1000)
        tool_name_list = list({k.split(":")[0] for k in seen_tool_keys}) if seen_tool_keys else None
        from services.log_service import record_ai_interaction
        record_ai_interaction(
            user_id, settings["model"], total_prompt_tokens, total_completion_tokens,
            total_prompt_tokens + total_completion_tokens, tool_name_list, latency_ms, persona_name,
        )

    except Exception as e:
        logger.exception("%s AI API error", ctx)
        await edit_message_safe(bot_message, "Error. Please retry.")
        from services.log_service import record_error
        record_error(user_id, str(e), "chat handler", settings.get("model"), persona_name)


async def _generate_and_set_title(user_id: int, session_id: int, user_message: str, ai_response: str) -> None:
    """Generate and set a title for a session (runs as background task)."""
    try:
        from cache import cache
        title = await generate_session_title(user_id, user_message, ai_response)
        if title:
            cache.update_session_title(session_id, title)
            logger.info("[user=%d] Auto-generated session title: %s", user_id, title)
    except Exception as e:
        logger.warning("[user=%d] Failed to auto-generate title: %s", user_id, e)
