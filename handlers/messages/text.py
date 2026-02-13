"""Text message handler with streaming output."""

import asyncio
import io
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import MAX_MESSAGE_LENGTH, STREAM_UPDATE_INTERVAL
from services import (
    get_user_settings,
    get_conversation,
    add_user_message,
    add_assistant_message,
    add_token_usage,
    has_api_key,
    get_system_prompt,
    get_remaining_tokens,
)
from tools import (
    get_all_tools,
    process_tool_calls,
    get_tool_instructions,
    enrich_system_prompt,
    post_process_response,
    drain_pending_voice_jobs,
)
from ai import get_ai_client
from utils import filter_thinking_content, send_message_safe, edit_message_safe, get_datetime_prompt
from handlers.common import should_respond_in_group, get_log_context

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
TOOL_TIMEOUT = 30  # seconds

TOOL_STATUS_MAP = {
    "web_search": "🔍 Searching...",
    "url_fetch": "🌐 Fetching page...",
    "save_memory": "💾 Saving to memory...",
    "tts_speak": "🎤 Generating voice...",
    "tts_list_voices": "🎙️ Loading voices...",
}


async def _stream_response(client, messages, model, temperature, tools, bot_message):
    """Stream an AI response, updating bot_message in real-time.

    The synchronous OpenAI streaming iterator is wrapped with run_in_executor
    so that waiting for each chunk does not block the async event loop.

    Returns:
        (full_response, usage_info, all_tool_calls, thinking_seconds)
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

    # Thinking/reasoning tracking
    thinking_start_time = None
    thinking_seconds = 0

    # Generic waiting indicator ("Thinking for Xs" before content/reasoning arrives)
    waiting_start_time = loop.time()
    waiting_active = True

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

    waiting_task = asyncio.create_task(_update_waiting())

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
                # Finalize thinking duration when content first appears
                thinking_seconds = max(1, int(current_time - thinking_start_time))
                thinking_prefix = f"_Thought for {thinking_seconds}s_\n\n"

            # First visible chunk: update immediately, skip throttle interval
            if first_chunk and display_text:
                waiting_active = False
                await edit_message_safe(bot_message, thinking_prefix + display_text + " ▌")
                last_update_time = current_time
                last_update_length = len(display_text)
                first_chunk = False
            elif (
                current_time - last_update_time >= STREAM_UPDATE_INTERVAL
                and len(display_text) > last_update_length
                and display_text
            ):
                await edit_message_safe(bot_message, thinking_prefix + display_text + " ▌")
                last_update_time = current_time
                last_update_length = len(display_text)

        if chunk.tool_calls:
            all_tool_calls.extend(chunk.tool_calls)

    # Clean up waiting indicator
    waiting_active = False
    if not waiting_task.done():
        waiting_task.cancel()

    # Finalize thinking seconds at stream end
    if thinking_start_time is not None:
        thinking_seconds = max(1, int(loop.time() - thinking_start_time))

    return full_response, usage_info, all_tool_calls, thinking_seconds


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle chat messages with streaming output."""
    # In groups, only respond when replied to or mentioned
    if not await should_respond_in_group(update, context):
        return

    # Skip forwarded messages (user can reply to them to trigger a response)
    if update.message.forward_origin:
        return

    user_id = update.effective_user.id
    user_message = update.message.text
    ctx = get_log_context(update)

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

    settings = get_user_settings(user_id)
    conversation = get_conversation(user_id)
    enabled_tools = settings.get("enabled_tools", "memory,search,fetch,wikipedia,tts")

    # Check if API key is set
    if not has_api_key(user_id):
        await update.message.reply_text(
            "Please set your OpenAI API key first:\n/set api_key YOUR_API_KEY"
        )
        return

    # Check token limit
    remaining = get_remaining_tokens(user_id)
    if remaining is not None and remaining <= 0:
        await update.message.reply_text(
            "You've reached your token limit. "
            "Use /usage to check usage or /set token_limit <number> to increase it."
        )
        return

    # Show typing indicator
    await update.message.chat.send_action(ChatAction.TYPING)

    # Send initial placeholder message
    bot_message = await update.message.reply_text("…")

    try:
        client = get_ai_client(user_id)

        # Build system prompt from current persona
        system_prompt = get_system_prompt(user_id)
        system_prompt += "\n\n" + get_datetime_prompt()

        # Let tools enrich system prompt (e.g. inject memories via vector search)
        system_prompt = enrich_system_prompt(
            user_id, system_prompt, enabled_tools=enabled_tools, query=user_message
        )

        # Add tool instructions (fallback hints)
        system_prompt += get_tool_instructions(enabled_tools=enabled_tools)

        # Build messages with system prompt
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation)
        messages.append({"role": "user", "content": user_message})

        # Get tool definitions
        tools = get_all_tools(enabled_tools=enabled_tools)

        # Accumulate token usage across rounds
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_thinking_seconds = 0

        # Tool call loop: stream response, process tools, re-call if needed
        last_text_response = ""  # fallback if final round is empty
        for _ in range(MAX_TOOL_ROUNDS + 1):
            full_response, usage_info, tool_calls, thinking_seconds = await _stream_response(
                client, messages, settings["model"], settings["temperature"],
                tools, bot_message,
            )
            total_thinking_seconds += thinking_seconds

            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens", 0)
                total_completion_tokens += usage_info.get("completion_tokens", 0)

            if full_response.strip():
                last_text_response = full_response

            if not tool_calls:
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

            # Execute tool calls with timeout
            try:
                tool_results = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: process_tool_calls(user_id, tool_calls, enabled_tools=enabled_tools)
                    ),
                    timeout=TOOL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning("%s tool timeout after %ds", ctx, TOOL_TIMEOUT)
                await edit_message_safe(
                    bot_message,
                    (display_text + "\n\n" if display_text else "")
                    + "⚠️ Tool execution timed out."
                )
                break

            if not tool_results:
                break

            # Build assistant message with tool_calls for the conversation
            assistant_msg = {
                "role": "assistant",
                "content": full_response or None,
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

        # Final update with complete response
        final_text = filter_thinking_content(full_response)

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
            await edit_message_safe(bot_message, display_final)

        # Save conversation to database (clean text without thinking prefix)
        add_user_message(user_id, user_message)
        add_assistant_message(user_id, final_text)

        # Record token usage if available
        if total_prompt_tokens or total_completion_tokens:
            add_token_usage(user_id, total_prompt_tokens, total_completion_tokens)

    except Exception as e:
        logger.exception("%s AI API error", ctx)
        await edit_message_safe(bot_message, f"Error: {str(e)}")
