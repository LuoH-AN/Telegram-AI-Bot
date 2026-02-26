"""Discord AI Bot entry point."""

import asyncio
import base64
import io
import json
import logging
import threading
import time
from typing import Sequence

import discord
import uvicorn
from discord.ext import commands

from config import (
    DISCORD_BOT_TOKEN,
    DISCORD_COMMAND_PREFIX,
    HEALTH_CHECK_PORT,
    STREAM_UPDATE_INTERVAL,
    STREAM_MIN_UPDATE_CHARS,
    STREAM_FORCE_UPDATE_INTERVAL,
    STREAM_UPDATE_MODE,
    STREAM_TIME_MODE_INTERVAL,
    STREAM_CHARS_MODE_INTERVAL,
    MAX_FILE_SIZE,
    MAX_TEXT_CONTENT_LENGTH,
    MIME_TYPE_MAP,
    WEB_BASE_URL,
)
from cache import init_database
from web.app import create_app
from web.auth import create_short_token
from services import (
    get_user_settings,
    update_user_setting,
    ensure_session,
    get_conversation,
    add_user_message,
    add_assistant_message,
    add_token_usage,
    has_api_key,
    get_system_prompt,
    get_remaining_tokens,
    get_current_persona_name,
    get_current_persona,
    get_personas,
    switch_persona,
    create_persona,
    delete_persona,
    update_current_prompt,
    persona_exists,
    get_token_usage,
    get_total_tokens_all_personas,
    get_token_limit,
    get_usage_percentage,
    export_to_markdown,
    set_token_limit,
    reset_token_usage,
    get_memories,
    add_memory,
    delete_memory,
    clear_memories,
    get_sessions,
    get_current_session,
    get_current_session_id,
    create_session,
    delete_chat_session,
    switch_session,
    rename_session,
    get_session_count,
    get_session_message_count,
    normalize_tts_endpoint,
    clear_conversation,
    generate_session_title,
)
from services.log_service import record_ai_interaction, record_error
from services.cron_service import start_cron_scheduler, set_main_loop
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
from utils import (
    filter_thinking_content,
    parse_raw_tool_calls,
    get_datetime_prompt,
    split_message,
    get_file_extension,
    is_text_file,
    is_image_file,
    is_likely_text,
    decode_file_content,
)


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

DISCORD_MAX_MESSAGE_LENGTH = 2000
MAX_TOOL_ROUNDS = 3
TOOL_TIMEOUT = 30
STREAM_BOUNDARY_CHARS = set(" \n\t.,!?;:)]}，。！？；：）】」》")
STREAM_PREVIEW_PREFIX = "[...]\n"
CRON_SCHEDULER_STARTED = False

AVAILABLE_TOOLS = ["memory", "search", "fetch", "wikipedia", "tts", "shell", "cron", "playwright"]
TOOL_STATUS_MAP = {
    "web_search": "Searching...",
    "url_fetch": "Fetching page...",
    "save_memory": "Saving to memory...",
    "tts_speak": "Generating voice...",
    "tts_list_voices": "Loading voices...",
    "shell_exec": "Running command...",
    "cron_create": "Creating scheduled task...",
    "cron_list": "Listing scheduled tasks...",
    "cron_delete": "Deleting scheduled task...",
    "cron_run": "Running scheduled task...",
    "page_screenshot": "Taking screenshot...",
    "page_content": "Extracting page content...",
}


def start_web_server() -> None:
    """Start the FastAPI web server (runs in a daemon thread)."""
    app = create_app()
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=HEALTH_CHECK_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("Web server started on port %d", HEALTH_CHECK_PORT)
    server.run()


def _discord_ctx(guild_id: int | None, channel_id: int, user_id: int) -> str:
    if guild_id is None:
        return f"[user={user_id} dm={channel_id}]"
    return f"[user={user_id} guild={guild_id} channel={channel_id}]"


def _mask_key(api_key: str) -> str:
    if not api_key:
        return "(empty)"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}...{api_key[-4:]}"


def _normalize_tools_csv(raw: str) -> str:
    seen = set()
    ordered: list[str] = []
    for item in (raw or "").split(","):
        name = item.strip().lower()
        if not name or name not in AVAILABLE_TOOLS or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ",".join(ordered)


def _resolve_enabled_tools_for_discord(settings: dict) -> str:
    if "enabled_tools" not in settings:
        return _normalize_tools_csv("memory,search,fetch,wikipedia,tts")
    return _normalize_tools_csv(settings.get("enabled_tools", ""))


def _resolve_cron_tools_for_display(settings: dict) -> str:
    explicit = _normalize_tools_csv(settings.get("cron_enabled_tools", ""))
    if explicit:
        return explicit
    derived = _normalize_tools_csv(settings.get("enabled_tools", ""))
    derived_list = [t for t in derived.split(",") if t and t != "memory"]
    return ",".join(derived_list)


def _estimate_tokens_str(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3000" <= c <= "\u30ff")
    other = len(text) - cjk
    return max(1, int(cjk / 1.5 + other / 4))


def _estimate_tokens(messages: Sequence[dict]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        total += _estimate_tokens_str(str(content)) + 4
    return total


def _normalize_stream_mode(mode: str | None) -> str:
    current = (mode or "").strip().lower()
    if current in {"default", "time", "chars"}:
        return current
    return "default"


def _build_stream_preview(display_text: str, *, thinking_prefix: str = "", cursor: bool = True) -> str:
    suffix = " ▌" if cursor else ""
    text = f"{thinking_prefix}{display_text}{suffix}"
    if len(text) <= DISCORD_MAX_MESSAGE_LENGTH:
        return text

    keep = DISCORD_MAX_MESSAGE_LENGTH - len(STREAM_PREVIEW_PREFIX)
    if keep <= 0:
        return STREAM_PREVIEW_PREFIX[:DISCORD_MAX_MESSAGE_LENGTH]
    return STREAM_PREVIEW_PREFIX + text[-keep:]


def _tool_dedup_key(tc: ToolCall) -> str:
    try:
        args = json.loads(tc.arguments)
    except Exception:
        return f"{tc.name}:{tc.arguments}"

    if tc.name == "url_fetch":
        return f"url_fetch:{args.get('url', '')}"
    if tc.name == "web_search":
        return f"web_search:{args.get('query', '')}"
    return f"{tc.name}:{tc.arguments}"


def _effective_tool_timeout(tool_calls: Sequence[ToolCall]) -> int:
    playwright_tools = {"page_screenshot", "page_content"}
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
        elif tc.name in playwright_tools:
            timeout = max(timeout, 60)
    return timeout


async def _safe_edit_message(message: discord.Message, text: str) -> bool:
    try:
        trimmed = text if text else "(Empty response)"
        if len(trimmed) > DISCORD_MAX_MESSAGE_LENGTH:
            trimmed = trimmed[: DISCORD_MAX_MESSAGE_LENGTH - 3] + "..."
        await message.edit(content=trimmed)
        return True
    except Exception:
        return False


async def _send_text_reply(message: discord.Message, text: str) -> None:
    chunks = split_message(text or "(Empty response)", max_length=DISCORD_MAX_MESSAGE_LENGTH)
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(chunk, mention_author=False)
        else:
            await message.channel.send(chunk)


async def _send_ctx_reply(ctx: commands.Context, text: str) -> None:
    chunks = split_message(text or "(Empty response)", max_length=DISCORD_MAX_MESSAGE_LENGTH)
    for i, chunk in enumerate(chunks):
        if i == 0:
            await ctx.reply(chunk, mention_author=False)
        else:
            await ctx.send(chunk)


async def _run_stream_completion_round(
    user_id: int,
    messages: list[dict],
    model: str,
    temperature: float,
    tools: list[dict] | None,
    placeholder: discord.Message,
    *,
    show_waiting: bool = True,
    stream_mode: str = "default",
) -> tuple[str, dict | None, list[ToolCall], int, str | None]:
    client = get_ai_client(user_id)
    loop = asyncio.get_running_loop()
    mode = _normalize_stream_mode(stream_mode)

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
    usage_info = None
    all_tool_calls: list[ToolCall] = []
    finish_reason = None

    last_update_time = 0.0
    last_update_length = 0
    first_visible_chunk = True

    thinking_start_time = None
    thinking_seconds = 0
    thinking_locked = False

    waiting_start_time = loop.time()
    waiting_active = show_waiting

    async def _update_waiting() -> None:
        try:
            while True:
                await asyncio.sleep(1)
                if not waiting_active:
                    break
                elapsed = max(1, int(loop.time() - waiting_start_time))
                await _safe_edit_message(placeholder, f"Thinking for {elapsed}s")
        except asyncio.CancelledError:
            pass

    waiting_task = asyncio.create_task(_update_waiting()) if show_waiting else None

    end_marker = object()
    it = iter(stream)

    try:
        while True:
            chunk = await loop.run_in_executor(None, next, it, end_marker)
            if chunk is end_marker:
                break

            if chunk.usage is not None:
                usage_info = chunk.usage

            current_time = loop.time()

            if chunk.reasoning and thinking_start_time is None:
                waiting_active = False
                thinking_start_time = current_time
                thinking_seconds = 1
                await _safe_edit_message(placeholder, "Thought for 1s")
                last_update_time = current_time

            if thinking_start_time is not None:
                new_seconds = max(1, int(current_time - thinking_start_time))
                display_text_now = filter_thinking_content(full_response, streaming=True) if full_response else ""
                if not display_text_now and new_seconds > thinking_seconds and current_time - last_update_time >= 1.0:
                    thinking_seconds = new_seconds
                    await _safe_edit_message(placeholder, f"Thought for {thinking_seconds}s")
                    last_update_time = current_time

            if chunk.content:
                full_response += chunk.content
                display_text = filter_thinking_content(full_response, streaming=True)

                if not display_text and full_response.strip() and thinking_start_time is None:
                    waiting_active = False
                    thinking_start_time = current_time
                    thinking_seconds = 1
                    await _safe_edit_message(placeholder, "Thought for 1s")
                    last_update_time = current_time

                thinking_prefix = ""
                if thinking_start_time is not None and display_text:
                    if not thinking_locked:
                        thinking_seconds = max(1, int(current_time - thinking_start_time))
                        thinking_locked = True
                    thinking_prefix = f"_Thought for {thinking_seconds}s_\n\n"

                if first_visible_chunk and display_text:
                    waiting_active = False
                    await _safe_edit_message(
                        placeholder,
                        _build_stream_preview(display_text, thinking_prefix=thinking_prefix, cursor=True),
                    )
                    last_update_time = current_time
                    last_update_length = len(display_text)
                    first_visible_chunk = False
                elif display_text and len(display_text) > last_update_length:
                    new_chars = len(display_text) - last_update_length
                    elapsed = current_time - last_update_time
                    ends_with_boundary = display_text[-1] in STREAM_BOUNDARY_CHARS

                    if mode == "time":
                        should_update = elapsed >= STREAM_TIME_MODE_INTERVAL
                    elif mode == "chars":
                        should_update = new_chars >= STREAM_CHARS_MODE_INTERVAL
                    else:
                        should_update = (
                            (elapsed >= STREAM_UPDATE_INTERVAL and new_chars >= STREAM_MIN_UPDATE_CHARS)
                            or (elapsed >= STREAM_UPDATE_INTERVAL and ends_with_boundary)
                            or (elapsed >= STREAM_FORCE_UPDATE_INTERVAL)
                        )

                    if should_update:
                        await _safe_edit_message(
                            placeholder,
                            _build_stream_preview(display_text, thinking_prefix=thinking_prefix, cursor=True),
                        )
                        last_update_time = current_time
                        last_update_length = len(display_text)

            if chunk.tool_calls:
                all_tool_calls.extend(chunk.tool_calls)

            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
    finally:
        waiting_active = False
        if waiting_task and not waiting_task.done():
            waiting_task.cancel()

    if thinking_start_time is not None and not thinking_locked:
        thinking_seconds = max(1, int(loop.time() - thinking_start_time))

    return full_response, usage_info, all_tool_calls, thinking_seconds, finish_reason


async def _generate_and_set_title(user_id: int, session_id: int, user_message: str, ai_response: str) -> None:
    try:
        from cache import cache

        title = await generate_session_title(user_id, user_message, ai_response)
        if title:
            cache.update_session_title(session_id, title)
            logger.info("[user=%d] Auto-generated session title: %s", user_id, title)
    except Exception as e:
        logger.warning("[user=%d] Failed to auto-generate title: %s", user_id, e)


async def _extract_reply_context(message: discord.Message) -> str:
    if not message.reference or not message.reference.message_id:
        return ""

    ref = message.reference.resolved
    quoted_msg: discord.Message | None = None

    if isinstance(ref, discord.Message):
        quoted_msg = ref
    else:
        try:
            quoted_msg = await message.channel.fetch_message(message.reference.message_id)
        except Exception:
            quoted_msg = None

    if not quoted_msg:
        return ""

    quoted_text = quoted_msg.content.strip()
    if not quoted_text:
        return ""

    sender = quoted_msg.author.display_name if quoted_msg.author else "Unknown"
    return f"[Quoted message from {sender}]:\n{quoted_text}"


async def _build_user_content_from_message(
    message: discord.Message,
    user_text: str,
) -> tuple[str | list[dict], str]:
    attachments = message.attachments or []
    if not attachments:
        save_msg = user_text.strip() if user_text.strip() else "[Empty message]"
        return user_text.strip(), save_msg

    oversized: list[str] = []
    text_blocks: list[str] = []
    image_parts: list[dict] = []
    unsupported_files: list[str] = []
    file_names: list[str] = []

    for attachment in attachments:
        file_name = attachment.filename or "unknown"
        file_names.append(file_name)

        if attachment.size and attachment.size > MAX_FILE_SIZE:
            oversized.append(file_name)
            continue

        try:
            file_bytes = await attachment.read()
        except Exception:
            unsupported_files.append(file_name)
            continue

        if (attachment.content_type or "").startswith("image/") or is_image_file(file_name):
            image_base64 = base64.b64encode(file_bytes).decode("utf-8")
            content_type = attachment.content_type or ""
            if content_type.startswith("image/"):
                mime = content_type.split(";", 1)[0].split("/", 1)[1]
            else:
                ext = get_file_extension(file_name).replace(".", "")
                mime = MIME_TYPE_MAP.get(ext, "jpeg")

            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{mime};base64,{image_base64}"},
                }
            )
            continue

        if is_text_file(file_name) or is_likely_text(file_bytes):
            file_content = decode_file_content(file_bytes)
            if file_content is None:
                unsupported_files.append(file_name)
                continue

            truncated = False
            if len(file_content) > MAX_TEXT_CONTENT_LENGTH:
                file_content = file_content[:MAX_TEXT_CONTENT_LENGTH]
                truncated = True

            label = f"[File: {file_name}]"
            if truncated:
                label += " (truncated)"
            text_blocks.append(f"{label}\n\n```\n{file_content}\n```")
            continue

        unsupported_files.append(file_name)

    text_sections: list[str] = []
    if user_text.strip():
        text_sections.append(user_text.strip())

    if text_blocks:
        text_sections.append("\n\n".join(text_blocks))

    if oversized:
        blocked = ", ".join(oversized[:5])
        if len(oversized) > 5:
            blocked += ", ..."
        text_sections.append(f"Skipped oversized files (max 20MB): {blocked}")

    if unsupported_files:
        skipped = ", ".join(unsupported_files[:5])
        if len(unsupported_files) > 5:
            skipped += ", ..."
        text_sections.append(f"Skipped unsupported files: {skipped}")

    text_prompt = "\n\n".join(text_sections).strip()

    if image_parts:
        user_content: str | list[dict] = list(image_parts)
        if text_prompt:
            user_content.insert(0, {"type": "text", "text": text_prompt})
    else:
        user_content = text_prompt or "Please analyze the uploaded file(s)."

    if len(file_names) == 1:
        save_msg = f"[File: {file_names[0]}]"
    else:
        preview = ", ".join(file_names[:3])
        if len(file_names) > 3:
            preview += ", ..."
        save_msg = f"[Files x{len(file_names)}] {preview}"

    if user_text.strip():
        save_msg = f"{save_msg} {user_text.strip()}"

    return user_content, save_msg


async def _should_respond_in_channel(bot: commands.Bot, message: discord.Message) -> bool:
    if message.guild is None:
        return True

    if bot.user and bot.user in message.mentions:
        return True

    if not message.reference or not message.reference.message_id:
        return False

    ref = message.reference.resolved
    if isinstance(ref, discord.Message):
        return bool(bot.user and ref.author.id == bot.user.id)

    try:
        replied = await message.channel.fetch_message(message.reference.message_id)
        return bool(bot.user and replied.author.id == bot.user.id)
    except Exception:
        return False


def _strip_bot_mentions(text: str, bot_user_id: int | None) -> str:
    if not bot_user_id:
        return text.strip()
    stripped = text or ""
    stripped = stripped.replace(f"<@{bot_user_id}>", "")
    stripped = stripped.replace(f"<@!{bot_user_id}>", "")
    return stripped.strip()


def _status_text(tool_calls: Sequence[ToolCall]) -> str:
    if not tool_calls:
        return ""
    lines = []
    for tc in tool_calls:
        lines.append(TOOL_STATUS_MAP.get(tc.name, f"Running {tc.name}..."))
    return "\n".join(lines)


async def _process_chat_message(bot: commands.Bot, message: discord.Message) -> None:
    user_id = int(message.author.id)
    ctx = _discord_ctx(message.guild.id if message.guild else None, message.channel.id, user_id)

    raw_text = _strip_bot_mentions(message.content or "", bot.user.id if bot.user else None)
    quoted = await _extract_reply_context(message)
    if quoted:
        raw_text = f"{quoted}\n\n{raw_text}" if raw_text else quoted

    user_content, save_msg = await _build_user_content_from_message(message, raw_text)

    if isinstance(user_content, str) and not user_content.strip():
        await _send_text_reply(message, "Please send a text message or attachment.")
        return

    if not has_api_key(user_id):
        await _send_text_reply(
            message,
            "Please set your OpenAI API key first:\n"
            f"{DISCORD_COMMAND_PREFIX}set api_key YOUR_API_KEY",
        )
        return

    persona_name = get_current_persona_name(user_id)
    remaining = get_remaining_tokens(user_id, persona_name)
    if remaining is not None and remaining <= 0:
        await _send_text_reply(
            message,
            f"Persona '{persona_name}' reached its token limit.\n"
            f"Use `{DISCORD_COMMAND_PREFIX}usage` to check usage or "
            f"`{DISCORD_COMMAND_PREFIX}set token_limit <number>` to adjust.",
        )
        return

    settings = get_user_settings(user_id)
    enabled_tools = _resolve_enabled_tools_for_discord(settings)
    user_stream_mode = _normalize_stream_mode(settings.get("stream_mode", "") or STREAM_UPDATE_MODE)
    session_id = ensure_session(user_id, persona_name)
    conversation = list(get_conversation(session_id))

    placeholder = await message.reply("Thinking...", mention_author=False)
    request_start = time.monotonic()

    try:
        system_prompt = get_system_prompt(user_id)
        system_prompt += "\n\n" + get_datetime_prompt()

        if isinstance(user_content, str):
            query_text = user_content
        elif isinstance(user_content, list):
            query_text = next(
                (
                    part["text"]
                    for part in user_content
                    if isinstance(part, dict) and part.get("type") == "text"
                ),
                save_msg,
            )
        else:
            query_text = save_msg

        system_prompt = enrich_system_prompt(
            user_id,
            system_prompt,
            enabled_tools=enabled_tools,
            query=query_text,
        )
        system_prompt += get_tool_instructions(enabled_tools=enabled_tools)
        system_prompt += (
            "\n\nIMPORTANT: Avoid LaTeX delimiters ($...$ / $$...$$). "
            "Use plain text and Unicode math symbols instead."
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation)
        messages.append({"role": "user", "content": user_content})

        tools = get_all_tools(enabled_tools=enabled_tools)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_thinking_seconds = 0
        seen_tool_keys: set[str] = set()
        last_text_response = ""
        tool_results_pending = False
        truncated_prefix = ""

        for round_num in range(MAX_TOOL_ROUNDS + 1):
            full_response, usage_info, tool_calls, thinking_seconds, finish_reason = await _run_stream_completion_round(
                user_id,
                messages,
                settings["model"],
                settings["temperature"],
                tools,
                placeholder,
                show_waiting=(round_num == 0),
                stream_mode=user_stream_mode,
            )
            total_thinking_seconds += thinking_seconds

            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens") or 0
                total_completion_tokens += usage_info.get("completion_tokens") or 0

            if not tool_calls and full_response:
                parsed_calls, cleaned = parse_raw_tool_calls(full_response)
                if parsed_calls:
                    tool_calls = [
                        ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                        for tc in parsed_calls
                    ]
                    full_response = cleaned
                    logger.info("%s parsed %d raw tool call(s)", ctx, len(tool_calls))

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
                    messages.append(
                        {
                            "role": "user",
                            "content": "Please continue and complete your response concisely.",
                        }
                    )
                    continue
                break

            status = _status_text(tool_calls)
            display_text = filter_thinking_content(full_response, streaming=True).strip()
            thinking_prefix = f"_Thought for {total_thinking_seconds}s_\n\n" if total_thinking_seconds > 0 else ""
            if display_text:
                status_text = _build_stream_preview(
                    f"{display_text}\n\n{status}",
                    thinking_prefix=thinking_prefix,
                    cursor=False,
                )
            else:
                status_text = _build_stream_preview(status, thinking_prefix=thinking_prefix, cursor=False)
            await _safe_edit_message(placeholder, status_text)
            tool_names = [tc.name for tc in tool_calls]

            new_tool_calls: list[ToolCall] = []
            dup_indices: set[int] = set()
            for i, tc in enumerate(tool_calls):
                key = _tool_dedup_key(tc)
                if key in seen_tool_keys:
                    dup_indices.add(i)
                else:
                    seen_tool_keys.add(key)
                    new_tool_calls.append(tc)

            if new_tool_calls:
                effective_timeout = _effective_tool_timeout(new_tool_calls)
                anim_active = True

                async def _animate_tool_status() -> None:
                    elapsed = 0
                    try:
                        while anim_active:
                            await asyncio.sleep(2)
                            if not anim_active:
                                break
                            elapsed += 2
                            lines = []
                            for name in tool_names:
                                base = TOOL_STATUS_MAP.get(name, f"Running {name}...")
                                lines.append(f"{base} ({elapsed}s)")
                            animated = "\n".join(lines)
                            if display_text:
                                animated_text = _build_stream_preview(
                                    f"{display_text}\n\n{animated}",
                                    thinking_prefix=thinking_prefix,
                                    cursor=False,
                                )
                            else:
                                animated_text = _build_stream_preview(
                                    animated,
                                    thinking_prefix=thinking_prefix,
                                    cursor=False,
                                )
                            await _safe_edit_message(placeholder, animated_text)
                    except asyncio.CancelledError:
                        pass

                anim_task = asyncio.create_task(_animate_tool_status())
                try:
                    executed_results = await asyncio.wait_for(
                        asyncio.get_running_loop().run_in_executor(
                            None,
                            lambda: process_tool_calls(
                                user_id,
                                new_tool_calls,
                                enabled_tools=enabled_tools,
                            ),
                        ),
                        timeout=effective_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning("%s tool timeout after %ds", ctx, effective_timeout)
                    executed_results = [
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Error: Tool execution timed out after {effective_timeout}s.",
                        }
                        for tc in new_tool_calls
                    ]
                finally:
                    anim_active = False
                    anim_task.cancel()
            else:
                executed_results = []

            tool_results: list[dict] = []
            exec_idx = 0
            for i, tc in enumerate(tool_calls):
                if i in dup_indices:
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": (
                                "Already called with the same target. "
                                "The result is in the conversation above."
                            ),
                        }
                    )
                else:
                    tool_results.append(executed_results[exec_idx])
                    exec_idx += 1

            if not tool_results:
                logger.warning("%s tool calls produced no results", ctx)
                break

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

            if round_num == MAX_TOOL_ROUNDS:
                break

        if tool_results_pending:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Please respond to the user based on the information above. "
                        "Do not attempt to call any more tools."
                    ),
                }
            )
            full_response, usage_info, _, thinking_seconds, _ = await _run_stream_completion_round(
                user_id,
                messages,
                settings["model"],
                settings["temperature"],
                None,
                placeholder,
                show_waiting=False,
                stream_mode=user_stream_mode,
            )
            total_thinking_seconds += thinking_seconds
            if usage_info:
                total_prompt_tokens += usage_info.get("prompt_tokens") or 0
                total_completion_tokens += usage_info.get("completion_tokens") or 0
            if full_response.strip():
                last_text_response = full_response

        combined_response = truncated_prefix + last_text_response if truncated_prefix else last_text_response
        final_text = filter_thinking_content(combined_response).strip()
        if not final_text and last_text_response:
            final_text = filter_thinking_content(last_text_response).strip()
        final_text = post_process_response(user_id, final_text, enabled_tools=enabled_tools)
        if not final_text:
            final_text = "(Empty response)"

        chunks = split_message(final_text, max_length=DISCORD_MAX_MESSAGE_LENGTH)
        if not chunks:
            chunks = ["(Empty response)"]

        edited = await _safe_edit_message(placeholder, chunks[0])
        if not edited:
            await message.channel.send(chunks[0])

        for chunk in chunks[1:]:
            await message.channel.send(chunk)

        pending_voices = drain_pending_voice_jobs(user_id)
        for idx, job in enumerate(pending_voices, 1):
            audio_data = job.get("audio")
            if not audio_data:
                continue

            file_obj = io.BytesIO(audio_data)
            filename = job.get("filename") or f"tts_{idx}.ogg"
            discord_file = discord.File(file_obj, filename=filename)
            caption = job.get("caption") or None
            await message.reply(content=caption, file=discord_file, mention_author=False)

        pending_screenshots = drain_pending_screenshot_jobs(user_id)
        for idx, job in enumerate(pending_screenshots, 1):
            image_data = job.get("image")
            if not image_data:
                continue

            file_obj = io.BytesIO(image_data)
            filename = job.get("filename") or f"screenshot_{idx}.png"
            discord_file = discord.File(file_obj, filename=filename)
            caption = job.get("caption") or None
            await message.reply(content=caption, file=discord_file, mention_author=False)

        add_user_message(session_id, save_msg)
        add_assistant_message(session_id, final_text)

        if get_session_message_count(session_id) <= 2:
            asyncio.create_task(_generate_and_set_title(user_id, session_id, save_msg, final_text))

        if not total_prompt_tokens and not total_completion_tokens:
            total_prompt_tokens = _estimate_tokens(messages)
            total_completion_tokens = _estimate_tokens_str(final_text)

        if total_prompt_tokens or total_completion_tokens:
            add_token_usage(
                user_id,
                total_prompt_tokens,
                total_completion_tokens,
                persona_name=persona_name,
            )

        latency_ms = int((time.monotonic() - request_start) * 1000)
        tool_name_list = list({k.split(":")[0] for k in seen_tool_keys}) if seen_tool_keys else None
        record_ai_interaction(
            user_id,
            settings["model"],
            total_prompt_tokens,
            total_completion_tokens,
            total_prompt_tokens + total_completion_tokens,
            tool_name_list,
            latency_ms,
            persona_name,
        )

    except Exception as e:
        logger.exception("%s AI API error", ctx)
        await _safe_edit_message(placeholder, "Error. Please retry.")
        record_error(user_id, str(e), "discord chat handler", settings.get("model"), persona_name)


def _fetch_models(user_id: int) -> list[str]:
    try:
        client = get_ai_client(user_id)
        return client.list_models()
    except Exception:
        logger.exception("Failed to fetch models")
        return []


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=DISCORD_COMMAND_PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready() -> None:
    global CRON_SCHEDULER_STARTED
    if bot.user:
        logger.info("Discord bot logged in as %s (%s)", bot.user, bot.user.id)
    if not CRON_SCHEDULER_STARTED:
        set_main_loop(asyncio.get_running_loop())
        start_cron_scheduler(bot)
        CRON_SCHEDULER_STARTED = True


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    logger.warning("Command error: %s", error)
    await _send_ctx_reply(ctx, f"Error: {error}")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    if (message.content or "").strip().startswith(DISCORD_COMMAND_PREFIX):
        return

    if not await _should_respond_in_channel(bot, message):
        return

    user_id = int(message.author.id)
    dctx = _discord_ctx(message.guild.id if message.guild else None, message.channel.id, user_id)
    logger.info("%s chat message", dctx)
    await _process_chat_message(bot, message)


@bot.command(name="start")
async def start_command(ctx: commands.Context) -> None:
    user_id = int(ctx.author.id)
    if not has_api_key(user_id):
        await _send_ctx_reply(
            ctx,
            "Welcome to AI Bot.\n\n"
            "Please configure your API first:\n"
            f"{DISCORD_COMMAND_PREFIX}set api_key YOUR_API_KEY\n\n"
            "Optional:\n"
            f"{DISCORD_COMMAND_PREFIX}set base_url <url>\n"
            f"{DISCORD_COMMAND_PREFIX}set model <name>\n"
            f"{DISCORD_COMMAND_PREFIX}set voice <name>\n"
            f"{DISCORD_COMMAND_PREFIX}set style <style>\n\n"
            f"Use {DISCORD_COMMAND_PREFIX}help for all commands.",
        )
        return

    persona = get_current_persona_name(user_id)
    await _send_ctx_reply(
        ctx,
        f"Welcome back. Current persona: {persona}\n\n"
        "Send a text/image/file to chat, or use help command.",
    )


@bot.command(name="help")
async def help_command(ctx: commands.Context) -> None:
    p = DISCORD_COMMAND_PREFIX
    await _send_ctx_reply(
        ctx,
        "AI Bot Help\n\n"
        "Send text, image, or file to chat with AI.\n"
        "In servers: mention the bot or reply to a bot message.\n"
        "In DMs: direct chat works.\n\n"
        f"Commands ({p}):\n"
        f"{p}start\n"
        f"{p}help\n"
        f"{p}clear\n"
        f"{p}persona ...\n"
        f"{p}chat ...\n"
        f"{p}settings\n"
        f"{p}set <key> <value>\n"
        f"{p}export\n"
        f"{p}usage\n"
        f"{p}remember <text>\n"
        f"{p}memories\n"
        f"{p}forget <num|all>\n"
        f"{p}web",
    )


@bot.command(name="clear")
async def clear_command(ctx: commands.Context) -> None:
    user_id = int(ctx.author.id)
    persona_name = get_current_persona_name(user_id)
    session_id = ensure_session(user_id, persona_name)
    clear_conversation(session_id)
    reset_token_usage(user_id)
    await _send_ctx_reply(
        ctx,
        f"Conversation cleared and usage reset for persona '{persona_name}'.",
    )


@bot.command(name="settings")
async def settings_command(ctx: commands.Context) -> None:
    user_id = int(ctx.author.id)
    settings = get_user_settings(user_id)
    persona_name = get_current_persona_name(user_id)
    persona = get_current_persona(user_id)

    prompt = persona["system_prompt"]
    prompt_display = prompt[:80] + "..." if len(prompt) > 80 else prompt

    enabled_tools = _resolve_enabled_tools_for_discord(settings) or "(none)"
    cron_tools = _resolve_cron_tools_for_display(settings) or "(none)"
    presets = settings.get("api_presets", {})
    presets_info = ", ".join(presets.keys()) if presets else "(none)"

    title_model_raw = settings.get("title_model", "")
    title_model_display = title_model_raw or "(current model)"
    cron_model_raw = settings.get("cron_model", "")
    cron_model_display = cron_model_raw or "(current model)"

    p = DISCORD_COMMAND_PREFIX
    text = (
        "Current Settings:\n\n"
        f"base_url: {settings['base_url']}\n"
        f"api_key: {_mask_key(settings['api_key'])}\n"
        f"model: {settings['model']}\n"
        f"temperature: {settings['temperature']}\n"
        f"title_model: {title_model_display}\n"
        f"cron_model: {cron_model_display}\n"
        f"persona: {persona_name}\n"
        f"prompt: {prompt_display}\n"
        f"tools: {enabled_tools}\n"
        f"cron_tools: {cron_tools}\n"
        f"tts_voice: {settings.get('tts_voice', '') or 'default'}\n"
        f"tts_style: {settings.get('tts_style', '') or 'default'}\n"
        f"tts_endpoint: {settings.get('tts_endpoint', '') or 'auto'}\n"
        f"providers: {presets_info}\n\n"
        f"Use `{p}persona` to manage personas and prompts.\n"
        f"Use `{p}chat` to manage chat sessions.\n"
        f"Use `{p}set tool <name> <on|off>` to manage tools.\n"
        f"Use `{p}set provider` to manage API providers."
    )

    await _send_ctx_reply(ctx, text)


@bot.command(name="set")
async def set_command(ctx: commands.Context, *args: str) -> None:
    user_id = int(ctx.author.id)
    settings = get_user_settings(user_id)

    if not args:
        p = DISCORD_COMMAND_PREFIX
        await _send_ctx_reply(
            ctx,
            "Usage: set <key> <value>\n\n"
            "Keys:\n"
            "- base_url\n"
            "- api_key\n"
            "- model (no value to browse list)\n"
            "- temperature\n"
            "- token_limit\n"
            "- title_model [provider:]model\n"
            "- cron_model [provider:]model\n"
            "- cron_tools <tool1,tool2,...>\n"
            "- stream_mode (default/time/chars)\n"
            "- voice\n"
            "- style\n"
            "- endpoint\n"
            "- tool <name> <on|off>\n"
            "- cron_tool <name> <on|off>\n"
            "- provider save/load/delete/list\n\n"
            f"For prompt, use `{p}persona prompt <text>`.\n"
            f"Example: {p}set model gpt-4o",
        )
        return

    key = args[0].lower()

    if key == "model" and len(args) == 1:
        if not has_api_key(user_id):
            await _send_ctx_reply(
                ctx,
                "Please set API key first:\n"
                f"{DISCORD_COMMAND_PREFIX}set api_key YOUR_API_KEY",
            )
            return

        wait_msg = await ctx.reply("Fetching models...", mention_author=False)
        models = await asyncio.get_running_loop().run_in_executor(None, lambda: _fetch_models(user_id))
        if not models:
            await wait_msg.edit(content="Failed to fetch models. Check your api_key and base_url.")
            return

        head = models[:40]
        extra = f"\n...and {len(models) - 40} more" if len(models) > 40 else ""
        await wait_msg.edit(
            content="Available models:\n" + "\n".join(head) + extra
        )
        return

    if len(args) < 2:
        if key == "tool":
            enabled_tools = _resolve_enabled_tools_for_discord(settings)
            enabled_list = [t.strip().lower() for t in enabled_tools.split(",") if t.strip()]
            status = []
            for tool in AVAILABLE_TOOLS:
                icon = "[on]" if tool in enabled_list else "[off]"
                status.append(f"{icon} {tool}")
            await _send_ctx_reply(
                ctx,
                "Tool Settings:\n\n"
                + "\n".join(status)
                + "\n\nUsage: set tool <name> <on|off>",
            )
            return

        if key == "cron_tool":
            cron_tools = _resolve_cron_tools_for_display(settings)
            enabled_list = [t.strip().lower() for t in cron_tools.split(",") if t.strip()]
            status = []
            for tool in AVAILABLE_TOOLS:
                icon = "[on]" if tool in enabled_list else "[off]"
                status.append(f"{icon} {tool}")
            await _send_ctx_reply(
                ctx,
                "Cron Tool Settings:\n\n"
                + "\n".join(status)
                + "\n\nUsage: set cron_tool <name> <on|off>",
            )
            return

        if key == "cron_tools":
            current = settings.get("cron_enabled_tools", "") or "(auto: chat tools without memory)"
            await _send_ctx_reply(
                ctx,
                "Current cron_tools: "
                + current
                + "\nUsage: set cron_tools <tool1,tool2,...>\n"
                "Use set cron_tools clear to reset to auto.",
            )
            return

        if key in {"voice", "style", "endpoint"}:
            setting_key = {
                "voice": "tts_voice",
                "style": "tts_style",
                "endpoint": "tts_endpoint",
            }[key]
            current = settings.get(setting_key, "") or "auto"
            await _send_ctx_reply(ctx, f"Current {key}: {current}\nUsage: set {key} <value>")
            return

        if key == "provider":
            await _show_provider_list(ctx, settings)
            return

        if key == "stream_mode":
            current = settings.get("stream_mode", "") or "default"
            await _send_ctx_reply(
                ctx,
                f"Current stream_mode: {current}\n"
                "Usage: set stream_mode <mode>\n\n"
                "Available modes:\n"
                "- default: time + chars combined\n"
                "- time: update by time interval\n"
                "- chars: update by character interval",
            )
            return

        await _send_ctx_reply(ctx, "Usage: set <key> <value>")
        return

    value = " ".join(args[1:]).strip()

    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        await _send_ctx_reply(ctx, f"base_url set to: {value}")
        return

    if key == "api_key":
        update_user_setting(user_id, "api_key", value)
        masked = _mask_key(value)
        try:
            models = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: _fetch_models(user_id),
            )
            if models:
                await _send_ctx_reply(
                    ctx,
                    f"api_key set to: {masked}\nVerified ({len(models)} models available)",
                )
            else:
                await _send_ctx_reply(
                    ctx,
                    f"api_key set to: {masked}\nCould not verify key (no models returned).",
                )
        except Exception:
            await _send_ctx_reply(
                ctx,
                f"api_key set to: {masked}\nCould not verify key. Check base_url and api_key.",
            )
        return

    if key == "model":
        update_user_setting(user_id, "model", value)
        await _send_ctx_reply(ctx, f"model set to: {value}")
        return

    if key == "prompt":
        await _send_ctx_reply(
            ctx,
            "Prompts are per-persona.\n"
            f"Use {DISCORD_COMMAND_PREFIX}persona prompt <text> to update current persona prompt.",
        )
        return

    if key == "temperature":
        try:
            temp = float(value)
        except ValueError:
            await _send_ctx_reply(ctx, "Invalid temperature value")
            return

        if not (0.0 <= temp <= 2.0):
            await _send_ctx_reply(ctx, "Temperature must be between 0.0 and 2.0")
            return

        update_user_setting(user_id, "temperature", temp)
        await _send_ctx_reply(ctx, f"temperature set to: {temp}")
        return

    if key == "token_limit":
        try:
            limit = int(value)
        except ValueError:
            await _send_ctx_reply(ctx, "Invalid token limit value")
            return

        if limit < 0:
            await _send_ctx_reply(ctx, "Token limit must be non-negative")
            return

        persona_name = get_current_persona_name(user_id)
        set_token_limit(user_id, limit, persona_name)
        await _send_ctx_reply(
            ctx,
            f"Persona '{persona_name}' token_limit set to: {limit:,}"
            + (" (unlimited)" if limit == 0 else ""),
        )
        return

    if key == "voice":
        if not value:
            await _send_ctx_reply(ctx, "Voice cannot be empty")
            return
        update_user_setting(user_id, "tts_voice", value)
        await _send_ctx_reply(ctx, f"voice set to: {value}")
        return

    if key == "style":
        style = value.lower()
        if not style:
            await _send_ctx_reply(ctx, "Style cannot be empty")
            return
        update_user_setting(user_id, "tts_style", style)
        await _send_ctx_reply(ctx, f"style set to: {style}")
        return

    if key == "endpoint":
        if value.lower() in {"auto", "default", "off"}:
            update_user_setting(user_id, "tts_endpoint", "")
            await _send_ctx_reply(ctx, "endpoint set to: auto")
            return

        normalized = normalize_tts_endpoint(value)
        if not normalized:
            await _send_ctx_reply(
                ctx,
                "Invalid endpoint. Example:\n"
                "set endpoint southeastasia\n"
                "or set endpoint southeastasia.tts.speech.microsoft.com",
            )
            return

        update_user_setting(user_id, "tts_endpoint", normalized)
        await _send_ctx_reply(ctx, f"endpoint set to: {normalized}")
        return

    if key == "tool":
        if len(args) < 3:
            await _send_ctx_reply(ctx, "Usage: set tool <name> <on|off>")
            return

        tool_name = args[1].lower()
        action = args[2].lower()

        if tool_name not in AVAILABLE_TOOLS:
            await _send_ctx_reply(
                ctx,
                f"Unknown/unsupported tool: {tool_name}. Available: {', '.join(AVAILABLE_TOOLS)}",
            )
            return

        enabled_tools = _resolve_enabled_tools_for_discord(settings)
        enabled_list = [t.strip().lower() for t in enabled_tools.split(",") if t.strip()]

        if action == "on":
            if tool_name not in enabled_list:
                enabled_list.append(tool_name)
        elif action == "off":
            if tool_name in enabled_list:
                enabled_list.remove(tool_name)
        else:
            await _send_ctx_reply(ctx, "Action must be 'on' or 'off'")
            return

        update_user_setting(user_id, "enabled_tools", _normalize_tools_csv(",".join(enabled_list)))
        await _send_ctx_reply(ctx, f"Tool {tool_name} set to {action}")
        return

    if key == "cron_tool":
        if len(args) < 3:
            await _send_ctx_reply(ctx, "Usage: set cron_tool <name> <on|off>")
            return

        tool_name = args[1].lower()
        action = args[2].lower()

        if tool_name not in AVAILABLE_TOOLS:
            await _send_ctx_reply(
                ctx,
                f"Unknown/unsupported tool: {tool_name}. Available: {', '.join(AVAILABLE_TOOLS)}",
            )
            return

        cron_tools = _resolve_cron_tools_for_display(settings)
        enabled_list = [t.strip().lower() for t in cron_tools.split(",") if t.strip()]

        if action == "on":
            if tool_name not in enabled_list:
                enabled_list.append(tool_name)
        elif action == "off":
            if tool_name in enabled_list:
                enabled_list.remove(tool_name)
        else:
            await _send_ctx_reply(ctx, "Action must be 'on' or 'off'")
            return

        new_enabled = _normalize_tools_csv(",".join(enabled_list))
        update_user_setting(user_id, "cron_enabled_tools", new_enabled)
        await _send_ctx_reply(ctx, f"Cron tool {tool_name} set to {action}")
        return

    if key == "cron_tools":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none", "default"}:
            update_user_setting(user_id, "cron_enabled_tools", "")
            await _send_ctx_reply(
                ctx,
                "cron_tools cleared.\n"
                "Now cron tasks will auto-use chat tools without memory.",
            )
            return

        normalized = _normalize_tools_csv(val)
        if not normalized:
            await _send_ctx_reply(
                ctx,
                "No valid tools provided.\n"
                f"Available: {', '.join(AVAILABLE_TOOLS)}",
            )
            return

        requested = [t.strip().lower() for t in val.split(",") if t.strip()]
        unknown = [t for t in requested if t not in AVAILABLE_TOOLS]
        update_user_setting(user_id, "cron_enabled_tools", normalized)
        if unknown:
            await _send_ctx_reply(
                ctx,
                f"cron_tools set to: {normalized}\n"
                f"Ignored unknown tools: {', '.join(sorted(set(unknown)))}",
            )
        else:
            await _send_ctx_reply(ctx, f"cron_tools set to: {normalized}")
        return

    if key == "provider":
        await _handle_provider_command(ctx, user_id, settings, list(args[1:]))
        return

    if key == "title_model":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "title_model", "")
            await _send_ctx_reply(ctx, "title_model cleared (will use current provider + model)")
        else:
            update_user_setting(user_id, "title_model", val)
            if ":" in val:
                provider, model_name = val.split(":", 1)
                presets = settings.get("api_presets", {})
                found = any(k.lower() == provider.lower() for k in presets)
                if found:
                    await _send_ctx_reply(
                        ctx,
                        f"title_model set to: {val}\n"
                        f"Provider: {provider} | Model: {model_name}",
                    )
                else:
                    available = ", ".join(presets.keys()) if presets else "(none)"
                    await _send_ctx_reply(
                        ctx,
                        f"title_model set to: {val}\n"
                        f"Provider '{provider}' not found in presets.\n"
                        f"Available: {available}\n"
                        f"Use {DISCORD_COMMAND_PREFIX}set provider save <name> first.",
                    )
            else:
                await _send_ctx_reply(
                    ctx,
                    f"title_model set to: {val}\n"
                    "(uses current provider API)",
                )
        return

    if key == "cron_model":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "cron_model", "")
            await _send_ctx_reply(ctx, "cron_model cleared (will use current provider + model)")
        else:
            update_user_setting(user_id, "cron_model", val)
            if ":" in val:
                provider, model_name = val.split(":", 1)
                presets = settings.get("api_presets", {})
                found = any(k.lower() == provider.lower() for k in presets)
                if found:
                    await _send_ctx_reply(
                        ctx,
                        f"cron_model set to: {val}\n"
                        f"Provider: {provider} | Model: {model_name}",
                    )
                else:
                    available = ", ".join(presets.keys()) if presets else "(none)"
                    await _send_ctx_reply(
                        ctx,
                        f"cron_model set to: {val}\n"
                        f"Provider '{provider}' not found in presets.\n"
                        f"Available: {available}\n"
                        f"Use {DISCORD_COMMAND_PREFIX}set provider save <name> first.",
                    )
            else:
                await _send_ctx_reply(
                    ctx,
                    f"cron_model set to: {val}\n"
                    "(uses current provider API)",
                )
        return

    if key == "stream_mode":
        mode = value.lower()
        if mode in {"default", "time", "chars"}:
            update_user_setting(user_id, "stream_mode", mode)
            await _send_ctx_reply(
                ctx,
                f"stream_mode set to: {mode}\n"
                "Applies to both Telegram and Discord streaming output.",
            )
        elif mode in {"", "off", "clear", "none"}:
            update_user_setting(user_id, "stream_mode", "")
            await _send_ctx_reply(
                ctx,
                "stream_mode cleared (will use default mode)\n"
                "Default mode: time + chars combined",
            )
        else:
            current = settings.get("stream_mode", "") or "default"
            await _send_ctx_reply(
                ctx,
                f"Current stream_mode: {current}\n"
                "Usage: set stream_mode <mode>\n\n"
                "Available modes:\n"
                "- default: time + chars combined\n"
                "- time: update by time interval\n"
                "- chars: update by character interval",
            )
        return

    await _send_ctx_reply(
        ctx,
        f"Unknown key: {key}\n"
        "Available: base_url, api_key, model, temperature, token_limit, title_model, cron_model, cron_tools, stream_mode, voice, style, endpoint, tool, cron_tool, provider",
    )


async def _show_provider_list(ctx: commands.Context, settings: dict) -> None:
    presets = settings.get("api_presets", {})
    if not presets:
        await _send_ctx_reply(
            ctx,
            "No saved providers.\n\n"
            "Usage:\n"
            "set provider save <name>\n"
            "set provider load <name>\n"
            "set provider delete <name>",
        )
        return

    lines = ["Saved Providers:\n"]
    for name, preset in presets.items():
        lines.append(
            f"[{name}]\n"
            f"  base_url: {preset.get('base_url', '')}\n"
            f"  api_key: {_mask_key(preset.get('api_key', ''))}\n"
            f"  model: {preset.get('model', '')}"
        )

    lines.append(
        "\nUsage:\n"
        "set provider save <name>\n"
        "set provider load <name>\n"
        "set provider delete <name>"
    )
    await _send_ctx_reply(ctx, "\n".join(lines))


async def _handle_provider_command(
    ctx: commands.Context,
    user_id: int,
    settings: dict,
    args: list[str],
) -> None:
    presets = settings.get("api_presets", {})

    if not args:
        await _show_provider_list(ctx, settings)
        return

    sub = args[0].lower()

    if sub == "list":
        await _show_provider_list(ctx, settings)
        return

    if sub == "save":
        if len(args) < 2:
            await _send_ctx_reply(ctx, "Usage: set provider save <name>")
            return

        name = args[1]
        presets[name] = {
            "api_key": settings["api_key"],
            "base_url": settings["base_url"],
            "model": settings["model"],
        }
        update_user_setting(user_id, "api_presets", presets)
        await _send_ctx_reply(
            ctx,
            f"Provider '{name}' saved:\n"
            f"  base_url: {settings['base_url']}\n"
            f"  api_key: {_mask_key(settings['api_key'])}\n"
            f"  model: {settings['model']}",
        )
        return

    if sub == "delete":
        if len(args) < 2:
            await _send_ctx_reply(ctx, "Usage: set provider delete <name>")
            return

        name = args[1]
        if name not in presets:
            await _send_ctx_reply(ctx, f"Provider '{name}' not found.")
            return

        del presets[name]
        update_user_setting(user_id, "api_presets", presets)
        await _send_ctx_reply(ctx, f"Provider '{name}' deleted.")
        return

    if sub == "load":
        if len(args) < 2:
            await _send_ctx_reply(ctx, "Usage: set provider load <name>")
            return

        name = args[1]
        if name not in presets:
            matched = next((k for k in presets if k.lower() == name.lower()), None)
            if matched is None:
                available = ", ".join(presets.keys()) if presets else "(none)"
                await _send_ctx_reply(ctx, f"Provider '{name}' not found. Available: {available}")
                return
            name = matched

        preset = presets[name]
        update_user_setting(user_id, "api_key", preset["api_key"])
        update_user_setting(user_id, "base_url", preset["base_url"])
        update_user_setting(user_id, "model", preset["model"])

        await _send_ctx_reply(
            ctx,
            f"Loaded provider '{name}':\n"
            f"  base_url: {preset['base_url']}\n"
            f"  api_key: {_mask_key(preset.get('api_key', ''))}\n"
            f"  model: {preset['model']}",
        )
        return

    await _send_ctx_reply(
        ctx,
        "Usage:\n"
        "set provider list\n"
        "set provider save <name>\n"
        "set provider load <name>\n"
        "set provider delete <name>",
    )


@bot.command(name="usage")
async def usage_command(ctx: commands.Context, *args: str) -> None:
    user_id = int(ctx.author.id)
    persona_name = get_current_persona_name(user_id)

    if args and args[0].lower() == "reset":
        reset_token_usage(user_id, persona_name)
        await _send_ctx_reply(ctx, f"Usage reset for persona '{persona_name}'.")
        return

    usage = get_token_usage(user_id, persona_name)
    token_limit = get_token_limit(user_id, persona_name)

    prompt_tokens = usage["prompt_tokens"]
    completion_tokens = usage["completion_tokens"]
    total_tokens = usage["total_tokens"]

    message = f"Token Usage (Persona: {persona_name}):\n\n"
    message += f"Prompt tokens:     {prompt_tokens:,}\n"
    message += f"Completion tokens: {completion_tokens:,}\n"
    message += f"Total tokens:      {total_tokens:,}\n"

    if token_limit > 0:
        remaining = get_remaining_tokens(user_id, persona_name)
        percentage = get_usage_percentage(user_id, persona_name) or 0

        message += f"\nLimit:     {token_limit:,}\n"
        message += f"Remaining: {remaining:,}\n"
        message += f"Usage:     {percentage:.1f}%\n\n"

        filled = int(percentage / 5)
        empty = 20 - filled
        bar = "[" + "#" * filled + "-" * empty + "]"
        message += f"{bar} {percentage:.1f}%"
    else:
        message += "\nLimit: Unlimited"

    total_all = get_total_tokens_all_personas(user_id)
    message += f"\n\n--- All Personas ---\nTotal tokens: {total_all:,}"

    await _send_ctx_reply(ctx, message)


@bot.command(name="export")
async def export_command(ctx: commands.Context) -> None:
    user_id = int(ctx.author.id)
    persona_name = get_current_persona_name(user_id)
    session_id = get_current_session_id(user_id, persona_name)

    file_buffer = export_to_markdown(user_id, persona_name)
    if file_buffer is None:
        await _send_ctx_reply(
            ctx,
            f"No conversation history to export in current session (persona: '{persona_name}').",
        )
        return

    filename = getattr(file_buffer, "name", None) or f"chat_export_{persona_name}.md"
    file_buffer.seek(0)
    discord_file = discord.File(file_buffer, filename=filename)

    caption = f"Chat history export (Persona: {persona_name})"
    if session_id is not None:
        caption += f"\nSession ID: {session_id}"

    await ctx.reply(caption, file=discord_file, mention_author=False)


@bot.command(name="remember")
async def remember_command(ctx: commands.Context, *, content: str | None = None) -> None:
    user_id = int(ctx.author.id)
    if not content:
        await _send_ctx_reply(
            ctx,
            "Usage: remember <content>\n"
            "Example: remember I prefer concise answers",
        )
        return

    add_memory(user_id, content, source="user")
    await _send_ctx_reply(ctx, f"Remembered: {content}")


@bot.command(name="memories")
async def memories_command(ctx: commands.Context) -> None:
    user_id = int(ctx.author.id)
    memories = get_memories(user_id)

    if not memories:
        await _send_ctx_reply(
            ctx,
            "No memories yet.\n\n"
            "Use remember <content> to add a memory.\n"
            "AI can also add memories during conversations.",
        )
        return

    lines = ["Your memories:\n"]
    for i, mem in enumerate(memories, 1):
        source_tag = "[AI]" if mem["source"] == "ai" else "[user]"
        lines.append(f"{i}. {source_tag} {mem['content']}")

    lines.append("\n[user] = added by you")
    lines.append("[AI] = added by AI")
    lines.append("\nUse forget <number> to delete")
    lines.append("Use forget all to clear all")

    await _send_ctx_reply(ctx, "\n".join(lines))


@bot.command(name="forget")
async def forget_command(ctx: commands.Context, target: str | None = None) -> None:
    user_id = int(ctx.author.id)

    if not target:
        await _send_ctx_reply(
            ctx,
            "Usage:\n"
            "forget <number> - Delete specific memory\n"
            "forget all - Clear all memories",
        )
        return

    if target.lower() == "all":
        count = clear_memories(user_id)
        if count > 0:
            await _send_ctx_reply(ctx, f"Cleared {count} memories.")
        else:
            await _send_ctx_reply(ctx, "No memories to clear.")
        return

    try:
        index = int(target)
    except ValueError:
        await _send_ctx_reply(ctx, "Please specify a number or 'all'.")
        return

    if delete_memory(user_id, index):
        await _send_ctx_reply(ctx, f"Memory #{index} deleted.")
    else:
        await _send_ctx_reply(ctx, f"Invalid memory number: {index}")


@bot.command(name="persona")
async def persona_command(ctx: commands.Context, *args: str) -> None:
    user_id = int(ctx.author.id)

    if not args:
        personas = get_personas(user_id)
        current = get_current_persona_name(user_id)
        if not personas:
            await _send_ctx_reply(ctx, "No personas found.")
            return

        lines = ["Your personas:\n"]
        for name, persona in personas.items():
            marker = "> " if name == current else "  "
            usage = get_token_usage(user_id, name)
            session_id = ensure_session(user_id, name)
            msg_count = len(get_conversation(session_id))
            session_ct = get_session_count(user_id, name)
            prompt_preview = persona["system_prompt"][:30]
            if len(persona["system_prompt"]) > 30:
                prompt_preview += "..."

            lines.append(f"{marker}{name}")
            lines.append(f"    {msg_count} msgs | {session_ct} sessions | {usage['total_tokens']:,} tokens")
            lines.append(f"    {prompt_preview}")
            lines.append("")

        lines.append("Commands:")
        lines.append("persona <name> - switch")
        lines.append("persona new <name> - create")
        lines.append("persona delete <name> - delete")
        lines.append("persona prompt <text> - set prompt")

        await _send_ctx_reply(ctx, "\n".join(lines))
        return

    subcmd = args[0].lower()

    if subcmd == "new":
        if len(args) < 2:
            await _send_ctx_reply(ctx, "Usage: persona new <name> [system prompt]")
            return

        name = args[1]
        prompt = " ".join(args[2:]) if len(args) > 2 else None
        if create_persona(user_id, name, prompt):
            switch_persona(user_id, name)
            await _send_ctx_reply(
                ctx,
                f"Created and switched to persona: {name}\n"
                "Use persona prompt <text> to set its prompt.",
            )
        else:
            await _send_ctx_reply(ctx, f"Persona '{name}' already exists.")
        return

    if subcmd == "delete":
        if len(args) < 2:
            await _send_ctx_reply(ctx, "Usage: persona delete <name>")
            return

        name = args[1]
        if name == "default":
            await _send_ctx_reply(ctx, "Cannot delete the default persona.")
            return

        if delete_persona(user_id, name):
            await _send_ctx_reply(ctx, f"Deleted persona: {name}")
        else:
            await _send_ctx_reply(ctx, f"Persona '{name}' not found.")
        return

    if subcmd == "prompt":
        if len(args) < 2:
            persona = get_current_persona(user_id)
            await _send_ctx_reply(
                ctx,
                f"Current persona: {persona['name']}\n\n"
                f"Prompt: {persona['system_prompt']}\n\n"
                "Usage: persona prompt <new prompt>",
            )
            return

        prompt = " ".join(args[1:])
        update_current_prompt(user_id, prompt)
        name = get_current_persona_name(user_id)
        await _send_ctx_reply(ctx, f"Updated prompt for '{name}'.")
        return

    name = args[0]
    if not persona_exists(user_id, name):
        await _send_ctx_reply(ctx, f"Persona '{name}' not found. Use persona new {name} to create it.")
        return

    switch_persona(user_id, name)
    persona = get_current_persona(user_id)
    usage = get_token_usage(user_id, name)
    session_id = ensure_session(user_id, name)
    msg_count = len(get_conversation(session_id))
    session_ct = get_session_count(user_id, name)
    current_session = get_current_session(user_id, name)
    session_title = (current_session.get("title") or "New Chat") if current_session else "New Chat"
    prompt_text = persona["system_prompt"]
    if len(prompt_text) > 100:
        prompt_text = prompt_text[:100] + "..."

    await _send_ctx_reply(
        ctx,
        f"Switched to: {name}\n\n"
        f"Messages: {msg_count}\n"
        f"Sessions: {session_ct}\n"
        f"Current session: {session_title}\n"
        f"Tokens: {usage['total_tokens']:,}\n\n"
        f"Prompt: {prompt_text}",
    )


@bot.command(name="chat")
async def chat_command(ctx: commands.Context, *args: str) -> None:
    user_id = int(ctx.author.id)
    persona_name = get_current_persona_name(user_id)

    if not args:
        sessions = get_sessions(user_id, persona_name)
        current_id = get_current_session_id(user_id, persona_name)

        if not sessions:
            await _send_ctx_reply(
                ctx,
                f"No sessions for persona '{persona_name}'.\n"
                "Send a message to create one automatically, or use chat new",
            )
            return

        lines = [f"Sessions (persona: {persona_name})\n"]
        for i, session in enumerate(sessions, 1):
            marker = "> " if session["id"] == current_id else "  "
            title = session.get("title") or "New Chat"
            msg_count = get_session_message_count(session["id"])
            lines.append(f"{marker}{i}. {title} ({msg_count} msgs)")

        lines.append("")
        lines.append("chat <num> - switch")
        lines.append("chat new [title] - new session")
        lines.append("chat rename <title> - rename")
        lines.append("chat delete <num> - delete")

        await _send_ctx_reply(ctx, "\n".join(lines))
        return

    subcmd = args[0].lower()

    if subcmd == "new":
        title = " ".join(args[1:]) if len(args) > 1 else None
        session = create_session(user_id, persona_name, title)
        display_title = title or "New Chat"
        await _send_ctx_reply(
            ctx,
            f"Created new session: {display_title}\n"
            f"Switched to session #{len(get_sessions(user_id, persona_name))}",
        )
        logger.info("[user=%d] chat new (session_id=%s)", user_id, session["id"])
        return

    if subcmd == "rename":
        if len(args) < 2:
            await _send_ctx_reply(ctx, "Usage: chat rename <title>")
            return

        title = " ".join(args[1:])
        if rename_session(user_id, title, persona_name):
            await _send_ctx_reply(ctx, f"Session renamed to: {title}")
        else:
            await _send_ctx_reply(ctx, "No current session to rename.")
        return

    if subcmd == "delete":
        if len(args) < 2:
            await _send_ctx_reply(ctx, "Usage: chat delete <number>")
            return

        try:
            index = int(args[1])
        except ValueError:
            await _send_ctx_reply(ctx, "Please provide a valid session number.")
            return

        sessions = get_sessions(user_id, persona_name)
        if index < 1 or index > len(sessions):
            await _send_ctx_reply(ctx, f"Invalid session number. Valid range: 1-{len(sessions)}")
            return

        session = sessions[index - 1]
        display_title = session.get("title") or "New Chat"

        if delete_chat_session(user_id, index, persona_name):
            await _send_ctx_reply(ctx, f"Deleted session: {display_title}")
        else:
            await _send_ctx_reply(ctx, "Failed to delete session.")
        return

    try:
        index = int(subcmd)
    except ValueError:
        await _send_ctx_reply(
            ctx,
            "Unknown subcommand. Usage:\n"
            "chat - list sessions\n"
            "chat new [title] - new session\n"
            "chat <num> - switch session\n"
            "chat rename <title> - rename\n"
            "chat delete <num> - delete",
        )
        return

    if switch_session(user_id, index, persona_name):
        sessions = get_sessions(user_id, persona_name)
        session = sessions[index - 1]
        display_title = session.get("title") or "New Chat"
        msg_count = get_session_message_count(session["id"])
        await _send_ctx_reply(
            ctx,
            f"Switched to session #{index}: {display_title}\nMessages: {msg_count}",
        )
    else:
        total = len(get_sessions(user_id, persona_name))
        await _send_ctx_reply(ctx, f"Invalid session number. Valid range: 1-{total}")


@bot.command(name="web")
async def web_command(ctx: commands.Context) -> None:
    user_id = int(ctx.author.id)
    token = create_short_token(user_id)
    url = f"{WEB_BASE_URL}/?token={token}"
    text = (
        "Open the Gemen dashboard:\n"
        f"{url}\n\n"
        "This link is single-use and expires in 10 minutes."
    )

    try:
        await ctx.author.send(text)
        if ctx.guild:
            await _send_ctx_reply(ctx, "Dashboard link sent to your DM.")
    except Exception:
        await _send_ctx_reply(ctx, "Could not send DM. Please allow DMs and retry.")


def main() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables")
        return

    init_database()

    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    logger.info("Starting Discord bot...")
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
