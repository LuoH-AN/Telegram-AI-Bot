"""Text message handler with streaming output."""

import asyncio
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
)
from ai import get_ai_client
from utils import filter_thinking_content, send_message_safe, edit_message_safe
from handlers.common import should_respond_in_group

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
TOOL_TIMEOUT = 30  # seconds

TOOL_STATUS_MAP = {
    "web_search": "🔍 Searching...",
    "url_fetch": "🌐 Fetching page...",
    "save_memory": "💾 Saving to memory...",
}


async def _stream_response(client, messages, model, temperature, tools, bot_message):
    """Stream an AI response, updating bot_message in real-time.

    Returns:
        (full_response, usage_info, all_tool_calls)
    """
    stream = client.chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        stream=True,
        tools=tools,
    )

    full_response = ""
    last_update_time = 0
    last_update_length = 0
    usage_info = None
    all_tool_calls = []
    shown_thinking = False
    first_chunk = True

    for chunk in stream:
        if chunk.usage is not None:
            usage_info = chunk.usage

        # Detect thinking/reasoning (separate field, e.g. DeepSeek R1)
        if chunk.reasoning and not shown_thinking:
            await edit_message_safe(bot_message, "Thinking...")
            shown_thinking = True

        if chunk.content:
            full_response += chunk.content

            display_text = filter_thinking_content(full_response, streaming=True)

            current_time = asyncio.get_event_loop().time()

            # Detect thinking via <think> tags in content
            if not display_text and full_response.strip() and not shown_thinking:
                await edit_message_safe(bot_message, "Thinking...")
                shown_thinking = True
                last_update_time = current_time

            # First visible chunk: update immediately, skip throttle interval
            if first_chunk and display_text:
                await edit_message_safe(bot_message, display_text + " ▌")
                last_update_time = current_time
                last_update_length = len(display_text)
                first_chunk = False
            elif (
                current_time - last_update_time >= STREAM_UPDATE_INTERVAL
                and len(display_text) > last_update_length
                and display_text
            ):
                await edit_message_safe(bot_message, display_text + " ▌")
                last_update_time = current_time
                last_update_length = len(display_text)

        if chunk.tool_calls:
            all_tool_calls.extend(chunk.tool_calls)

    return full_response, usage_info, all_tool_calls


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle chat messages with streaming output."""
    # In groups, only respond when replied to or mentioned
    if not await should_respond_in_group(update, context):
        return

    user_id = update.effective_user.id
    user_message = update.message.text

    # Remove bot mention from message if present
    bot_username = context.bot.username
    if bot_username and f"@{bot_username}" in user_message:
        user_message = user_message.replace(f"@{bot_username}", "").strip()

    settings = get_user_settings(user_id)
    conversation = get_conversation(user_id)

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

        # Let tools enrich system prompt (e.g. inject memories via vector search)
        system_prompt = enrich_system_prompt(user_id, system_prompt, query=user_message)

        # Add tool instructions (fallback hints)
        system_prompt += get_tool_instructions()

        # Build messages with system prompt
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation)
        messages.append({"role": "user", "content": user_message})

        # Get tool definitions
        tools = get_all_tools()

        # Accumulate token usage across rounds
        total_prompt_tokens = 0
        total_completion_tokens = 0

        # Tool call loop: stream response, process tools, re-call if needed
        for _ in range(MAX_TOOL_ROUNDS + 1):
            full_response, usage_info, tool_calls = await _stream_response(
                client, messages, settings["model"], settings["temperature"],
                tools, bot_message,
            )

            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens", 0)
                total_completion_tokens += usage_info.get("completion_tokens", 0)

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
            if display_text:
                await edit_message_safe(bot_message, display_text + "\n\n" + status_text)
            else:
                await edit_message_safe(bot_message, status_text)

            # Execute tool calls with timeout
            try:
                tool_results = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: process_tool_calls(user_id, tool_calls)
                    ),
                    timeout=TOOL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning("Tool execution timed out after %ds", TOOL_TIMEOUT)
                await edit_message_safe(
                    bot_message,
                    (display_text + "\n\n" if display_text else "")
                    + "⚠️ Tool execution timed out."
                )
                break

            if not tool_results:
                # All fire-and-forget — no need for another round
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

        # Final update with complete response
        final_text = filter_thinking_content(full_response)

        # Post-process response (e.g. regex fallback for memory extraction)
        final_text = post_process_response(user_id, final_text)

        if not final_text:
            final_text = "(Empty response)"

        # Check if response exceeds single message limit
        if len(final_text) > MAX_MESSAGE_LENGTH:
            # Delete the placeholder and send multiple messages
            await bot_message.delete()
            await send_message_safe(update.message, final_text)
        else:
            await edit_message_safe(bot_message, final_text)

        # Save conversation to database
        add_user_message(user_id, user_message)
        add_assistant_message(user_id, final_text)

        # Save last message for /retry
        context.user_data["last_message"] = user_message

        # Record token usage if available
        if total_prompt_tokens or total_completion_tokens:
            add_token_usage(user_id, total_prompt_tokens, total_completion_tokens)

    except Exception as e:
        logger.exception("Error calling AI API")
        await edit_message_safe(bot_message, f"Error: {str(e)}")
