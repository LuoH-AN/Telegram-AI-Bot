"""Discord AI Bot entry point."""

import asyncio
import base64
import io
import json
import logging
import threading
import time
from urllib.parse import urlsplit
from typing import Sequence

import discord
import uvicorn
from discord import asset as discord_asset
from discord import gateway as discord_gateway
from discord import http as discord_http
from discord import invite as discord_invite
from discord.ext import commands
from yarl import URL

from config import (
    DISCORD_BOT_TOKEN,
    DISCORD_COMMAND_PREFIX,
    DISCORD_API_BASE,
    DISCORD_GATEWAY_BASE,
    DISCORD_CDN_BASE,
    DISCORD_INVITE_BASE,
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
    DEFAULT_TTS_VOICE,
    DEFAULT_TTS_STYLE,
    TOOL_CONTINUE_OR_FINISH_PROMPT,
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
    get_message_count,
    get_token_usage,
    get_total_tokens_all_personas,
    get_token_limit,
    get_usage_percentage,
    export_to_markdown,
    set_token_limit,
    get_token_limit,
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
    conversation_slot,
)
from services.log import record_ai_interaction, record_error
from services.cron import start_cron_scheduler, set_main_loop
from tools import (
    get_all_tools,
    process_tool_calls,
    get_tool_instructions,
    enrich_system_prompt,
    post_process_response,
    drain_pending_voice_jobs,
    drain_pending_screenshot_jobs,
    prewarm_browser_tools,
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
    ChatEventPump,
    StreamOutboundAdapter,
)
from utils.tooling import (
    AVAILABLE_TOOLS,
    normalize_tools_csv,
    resolve_cron_tools_csv,
    resolve_enabled_tools_csv,
)
from utils.ai_helpers import (
    effective_tool_timeout,
    estimate_tokens as _estimate_tokens,
    estimate_tokens_str as _estimate_tokens_str,
    tool_dedup_key as _tool_dedup_key,
)
from utils.platform_parity import (
    SHARED_TOOL_STATUS_MAP,
    build_analyze_uploaded_files_message,
    build_api_key_required_message,
    build_api_key_verify_failed_message,
    build_api_key_verify_no_models_message,
    build_chat_commands_message,
    build_chat_no_sessions_message,
    build_chat_unknown_subcommand_message,
    build_endpoint_invalid_message,
    build_forget_usage_message,
    build_forget_invalid_target_message,
    build_help_message,
    build_invalid_memory_number_message,
    build_latex_guidance,
    build_memory_empty_message,
    build_memory_list_footer_message,
    build_persona_commands_message,
    build_persona_created_message,
    build_persona_new_usage_message,
    build_persona_not_found_message,
    build_persona_prompt_overview_message,
    build_prompt_per_persona_message,
    build_provider_list_usage_message,
    build_provider_no_saved_message,
    build_provider_not_found_available_message,
    build_provider_save_hint_message,
    build_provider_usage_message,
    build_set_usage_message,
    build_start_message_missing_api,
    build_start_message_returning,
    build_token_limit_reached_message,
    build_unknown_set_key_message,
    build_usage_reset_message,
    build_remember_usage_message,
    build_retry_message,
    build_web_dashboard_message,
    build_web_dm_failed_message,
    build_web_dm_sent_message,
    format_log_context,
)


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

DISCORD_MAX_MESSAGE_LENGTH = 2000
TOOL_TIMEOUT = 30
AI_STREAM_NO_OUTPUT_TIMEOUT = 45
AI_STREAM_OUTPUT_IDLE_TIMEOUT = 120
STREAM_BOUNDARY_CHARS = set(" \n\t.,!?;:)]}，。！？；：）】」》")
STREAM_PREVIEW_PREFIX = "[...]\n"
CRON_SCHEDULER_STARTED = False
TOOL_STATUS_MAP = SHARED_TOOL_STATUS_MAP
VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


_DISCORD_CDN_PROXY_BASE: str | None = None
_DISCORD_GATEWAY_PROXY_URL: str | None = None


def _normalize_http_base(value: str, *, name: str) -> str | None:
    base = (value or "").strip()
    if not base:
        return None
    if not base.startswith(("http://", "https://")):
        logger.warning(
            "Ignoring %s=%s because it does not start with http:// or https://",
            name,
            base,
        )
        return None
    return base.rstrip("/")


def _normalize_ws_base(value: str, *, name: str) -> URL | None:
    base = (value or "").strip()
    if not base:
        return None
    if not base.startswith(("ws://", "wss://")):
        logger.warning(
            "Ignoring %s=%s because it does not start with ws:// or wss://",
            name,
            base,
        )
        return None
    gateway_url = URL(base)
    if gateway_url.query:
        logger.warning("Ignoring query string in %s; configure it on proxy side", name)
        gateway_url = gateway_url.with_query(None)
    if gateway_url.fragment:
        logger.warning("Ignoring fragment in %s; fragments are not used in ws URLs", name)
        gateway_url = gateway_url.with_fragment("")
    if not gateway_url.path:
        gateway_url = gateway_url.with_path("/")
    return gateway_url


def _join_base_with_path(base: str, path_with_query: str) -> str:
    if not path_with_query.startswith("/"):
        path_with_query = f"/{path_with_query}"
    return f"{base}{path_with_query}"


def _rewrite_cdn_url_if_needed(url: str) -> str:
    if not _DISCORD_CDN_PROXY_BASE:
        return url
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if host not in {"cdn.discordapp.com", "media.discordapp.net"}:
        return url

    path_with_query = parsed.path or "/"
    if parsed.query:
        path_with_query = f"{path_with_query}?{parsed.query}"
    return _join_base_with_path(_DISCORD_CDN_PROXY_BASE, path_with_query)


def _resolve_discord_api_route_base() -> str | None:
    base = _normalize_http_base(DISCORD_API_BASE, name="DISCORD_API_BASE")
    if not base:
        return None

    version_suffix = f"/api/v{discord_http.INTERNAL_API_VERSION}"
    if base.endswith(version_suffix):
        return base
    if base.endswith("/api"):
        return f"{base}/v{discord_http.INTERNAL_API_VERSION}"
    return f"{base}{version_suffix}"


def _patch_discord_httpclient_methods() -> None:
    if getattr(discord_http.HTTPClient.get_from_cdn, "_gemen_patched", False):
        return

    original_get_from_cdn = discord_http.HTTPClient.get_from_cdn
    original_get_bot_gateway = discord_http.HTTPClient.get_bot_gateway

    async def _patched_get_from_cdn(self: discord_http.HTTPClient, url: str) -> bytes:
        return await original_get_from_cdn(self, _rewrite_cdn_url_if_needed(url))

    async def _patched_get_bot_gateway(self: discord_http.HTTPClient):
        shards, url, session_limits = await original_get_bot_gateway(self)
        if _DISCORD_GATEWAY_PROXY_URL:
            return shards, _DISCORD_GATEWAY_PROXY_URL, session_limits
        return shards, url, session_limits

    setattr(_patched_get_from_cdn, "_gemen_patched", True)
    setattr(_patched_get_bot_gateway, "_gemen_patched", True)
    discord_http.HTTPClient.get_from_cdn = _patched_get_from_cdn
    discord_http.HTTPClient.get_bot_gateway = _patched_get_bot_gateway


def _apply_discord_network_overrides() -> None:
    global _DISCORD_CDN_PROXY_BASE
    global _DISCORD_GATEWAY_PROXY_URL

    route_base = _resolve_discord_api_route_base()
    if route_base:
        discord_http.Route.BASE = route_base
        logger.info("Discord API base overridden to %s", route_base)

    gateway_base = _normalize_ws_base(DISCORD_GATEWAY_BASE, name="DISCORD_GATEWAY_BASE")
    if gateway_base:
        _DISCORD_GATEWAY_PROXY_URL = str(gateway_base)
        discord_gateway.DiscordWebSocket.DEFAULT_GATEWAY = gateway_base
        logger.info("Discord Gateway base overridden to %s", _DISCORD_GATEWAY_PROXY_URL)
    else:
        _DISCORD_GATEWAY_PROXY_URL = None

    cdn_base = _normalize_http_base(DISCORD_CDN_BASE, name="DISCORD_CDN_BASE")
    if cdn_base:
        _DISCORD_CDN_PROXY_BASE = cdn_base
        discord_asset.Asset.BASE = cdn_base
        logger.info("Discord CDN base overridden to %s", cdn_base)
    else:
        _DISCORD_CDN_PROXY_BASE = None

    invite_base = _normalize_http_base(DISCORD_INVITE_BASE, name="DISCORD_INVITE_BASE")
    if invite_base:
        discord_invite.Invite.BASE = invite_base
        logger.info("Discord invite base overridden to %s", invite_base)

    _patch_discord_httpclient_methods()


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
        return format_log_context(platform="discord", user_id=user_id, scope="private", chat_id=channel_id)
    return format_log_context(platform="discord", user_id=user_id, scope="group", chat_id=channel_id)


def _discord_cmd_ctx(ctx: commands.Context) -> str:
    user_id = int(ctx.author.id)
    guild_id = ctx.guild.id if ctx.guild else None
    channel_id = ctx.channel.id
    return _discord_ctx(guild_id, channel_id, user_id)


def _mask_key(api_key: str) -> str:
    if not api_key:
        return "(empty)"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}...{api_key[-4:]}"


def _normalize_stream_mode(mode: str | None) -> str:
    current = (mode or "").strip().lower()
    if current in {"default", "time", "chars"}:
        return current
    return "default"


def _normalize_reasoning_effort(value: str | None) -> str:
    current = (value or "").strip().lower()
    if current in VALID_REASONING_EFFORTS:
        return current
    return ""


def _build_stream_preview(display_text: str, *, thinking_prefix: str = "", cursor: bool = True) -> str:
    suffix = " ▌" if cursor else ""
    text = f"{thinking_prefix}{display_text}{suffix}"
    if len(text) <= DISCORD_MAX_MESSAGE_LENGTH:
        return text

    keep = DISCORD_MAX_MESSAGE_LENGTH - len(STREAM_PREVIEW_PREFIX)
    if keep <= 0:
        return STREAM_PREVIEW_PREFIX[:DISCORD_MAX_MESSAGE_LENGTH]
    return STREAM_PREVIEW_PREFIX + text[-keep:]


def _effective_tool_timeout(tool_calls: Sequence[ToolCall]) -> int:
    return effective_tool_timeout(tool_calls, default_timeout=TOOL_TIMEOUT)


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
    reasoning_effort: str | None,
    tools: list[dict] | None,
    stream_update,
    status_update=None,
    *,
    show_waiting: bool = True,
    stream_mode: str = "default",
) -> tuple[str, dict | None, list[ToolCall], int, str | None]:
    client = get_ai_client(user_id)
    loop = asyncio.get_running_loop()
    status_cb = status_update or stream_update
    mode = _normalize_stream_mode(stream_mode)

    stream = await loop.run_in_executor(
        None,
        lambda: client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            reasoning_effort=reasoning_effort or None,
            stream=True,
            tools=tools,
        ),
    )

    full_response = ""
    usage_info = None
    all_tool_calls: list[ToolCall] = []
    finish_reason = None
    stream_start_time = loop.time()
    last_output_activity: float | None = None

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
                await status_cb(f"Thinking for {elapsed}s")
        except asyncio.CancelledError:
            pass

    waiting_task = asyncio.create_task(_update_waiting()) if show_waiting else None

    end_marker = object()
    it = iter(stream)

    try:
        while True:
            idle_limit = AI_STREAM_NO_OUTPUT_TIMEOUT if last_output_activity is None else AI_STREAM_OUTPUT_IDLE_TIMEOUT
            idle_since = stream_start_time if last_output_activity is None else last_output_activity
            timeout_left = idle_limit - (loop.time() - idle_since)
            if timeout_left <= 0:
                logger.warning(
                    "Discord stream idle timeout (%ss, has_output=%s)",
                    idle_limit,
                    last_output_activity is not None,
                )
                finish_reason = finish_reason or "timeout"
                break
            try:
                chunk = await asyncio.wait_for(
                    loop.run_in_executor(None, next, it, end_marker),
                    timeout=max(1.0, timeout_left),
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Discord stream stalled: no activity for %ss (has_output=%s)",
                    idle_limit,
                    last_output_activity is not None,
                )
                finish_reason = finish_reason or "timeout"
                break
            if chunk is end_marker:
                break

            if chunk.usage is not None:
                usage_info = chunk.usage

            current_time = loop.time()
            has_output_activity = bool(chunk.content or chunk.reasoning or chunk.tool_calls)
            if has_output_activity:
                last_output_activity = current_time

            if chunk.reasoning and thinking_start_time is None:
                waiting_active = False
                thinking_start_time = current_time
                thinking_seconds = 1
                await status_cb("Thinking for 1s")
                last_update_time = current_time

            if thinking_start_time is not None:
                new_seconds = max(1, int(current_time - thinking_start_time))
                display_text_now = filter_thinking_content(full_response, streaming=True) if full_response else ""
                if not display_text_now and new_seconds > thinking_seconds and current_time - last_update_time >= 1.0:
                    thinking_seconds = new_seconds
                    await status_cb(f"Thinking for {thinking_seconds}s")
                    last_update_time = current_time

            if chunk.content:
                full_response += chunk.content
                display_text = filter_thinking_content(full_response, streaming=True)

                if not display_text and full_response.strip() and thinking_start_time is None:
                    waiting_active = False
                    thinking_start_time = current_time
                    thinking_seconds = 1
                    await status_cb("Thinking for 1s")
                    last_update_time = current_time

                thinking_prefix = ""
                if thinking_start_time is not None and display_text:
                    if not thinking_locked:
                        thinking_seconds = max(1, int(current_time - thinking_start_time))
                        thinking_locked = True
                    thinking_prefix = f"_Thinking for {thinking_seconds}s_\n\n"

                if first_visible_chunk and display_text:
                    waiting_active = False
                    await stream_update(_build_stream_preview(display_text, thinking_prefix=thinking_prefix, cursor=True))
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
                        await stream_update(_build_stream_preview(display_text, thinking_prefix=thinking_prefix, cursor=True))
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
            sctx = format_log_context(platform="discord", user_id=user_id, scope="system", chat_id=0)
            logger.info("%s auto-generated session title: %s", sctx, title)
    except Exception as e:
        sctx = format_log_context(platform="discord", user_id=user_id, scope="system", chat_id=0)
        logger.warning("%s failed to auto-generate title: %s", sctx, e)


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
        user_content = text_prompt or build_analyze_uploaded_files_message()

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


def _status_text(
    tool_calls: Sequence[ToolCall],
    *,
    elapsed_seconds: int | None = None,
    overrides: dict[str, str] | None = None,
) -> str:
    if not tool_calls:
        return ""
    counts: dict[str, int] = {}
    order: list[str] = []
    for tc in tool_calls:
        name = (tc.name or "").strip() or "tool"
        if name not in counts:
            order.append(name)
            counts[name] = 0
        counts[name] += 1
    lines = []
    for name in order:
        base = (overrides or {}).get(name) or TOOL_STATUS_MAP.get(name, f"Running {name}...")
        count_suffix = f" ×{counts[name]}" if counts[name] > 1 else ""
        elapsed_suffix = f" ({elapsed_seconds}s)" if elapsed_seconds is not None else ""
        lines.append(f"{base}{count_suffix}{elapsed_suffix}")
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
        await _send_text_reply(message, build_api_key_required_message(DISCORD_COMMAND_PREFIX))
        return

    persona_name = get_current_persona_name(user_id)
    remaining = get_remaining_tokens(user_id, persona_name)
    if remaining is not None and remaining <= 0:
        await _send_text_reply(
            message,
            build_token_limit_reached_message(DISCORD_COMMAND_PREFIX, persona_name),
        )
        return

    settings = get_user_settings(user_id)
    enabled_tools = resolve_enabled_tools_csv(settings)
    user_stream_mode = _normalize_stream_mode(settings.get("stream_mode", "") or STREAM_UPDATE_MODE)
    user_reasoning_effort = _normalize_reasoning_effort(settings.get("reasoning_effort", ""))
    session_id = ensure_session(user_id, persona_name)
    conversation = list(get_conversation(session_id))

    placeholder = await message.reply("Thinking...", mention_author=False)

    placeholder_alive = True

    async def _edit_placeholder(text: str) -> bool:
        if not placeholder_alive:
            return False
        return await _safe_edit_message(placeholder, text)

    async def _send_text(text: str) -> bool:
        chunks = split_message(text or "(Empty response)", max_length=DISCORD_MAX_MESSAGE_LENGTH)
        if not chunks:
            chunks = ["(Empty response)"]
        try:
            await message.channel.send(chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)
            return True
        except Exception:
            logger.exception("%s failed to send discord text chunk", ctx)
            return False

    async def _delete_placeholder() -> None:
        nonlocal placeholder_alive
        if not placeholder_alive:
            return
        try:
            await placeholder.delete()
        except Exception:
            pass
        placeholder_alive = False

    outbound = StreamOutboundAdapter(
        max_message_length=DISCORD_MAX_MESSAGE_LENGTH,
        has_placeholder=lambda: placeholder_alive,
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

    slot_key = f"discord:{message.channel.id}:{user_id}:{session_id}"
    slot_cm = conversation_slot(slot_key)
    was_queued = await slot_cm.__aenter__()
    request_start = time.monotonic()
    final_delivery_confirmed = False

    try:
        if was_queued:
            await _status_update("Previous request is still running. Queued and starting soon...")

        system_prompt = get_system_prompt(user_id, persona_name)
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
        system_prompt += build_latex_guidance()

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

        round_num = 0
        while True:
            round_num += 1
            full_response, usage_info, tool_calls, thinking_seconds, finish_reason = await _run_stream_completion_round(
                user_id,
                messages,
                settings["model"],
                settings["temperature"],
                user_reasoning_effort,
                tools,
                _stream_update,
                _status_update,
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
                if finish_reason == "length":
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
            thinking_prefix = f"_Thinking for {total_thinking_seconds}s_\n\n" if total_thinking_seconds > 0 else ""
            if display_text:
                status_text = _build_stream_preview(
                    f"{display_text}\n\n{status}",
                    thinking_prefix=thinking_prefix,
                    cursor=False,
                )
            else:
                status_text = _build_stream_preview(status, thinking_prefix=thinking_prefix, cursor=False)
            await _status_update(status_text)

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
                status_overrides: dict[str, str] = {}
                status_dirty = asyncio.Event()
                tool_started_at = time.monotonic()
                activity_lock = threading.Lock()
                last_activity = time.monotonic()
                loop = asyncio.get_running_loop()
                anim_active = True

                def _touch_activity() -> None:
                    nonlocal last_activity
                    with activity_lock:
                        last_activity = time.monotonic()

                def _activity_age() -> float:
                    with activity_lock:
                        return time.monotonic() - last_activity

                def _on_tool_event(event: dict) -> None:
                    event_type = str(event.get("type") or "").strip().lower()
                    name = str(event.get("tool_name") or "tool").strip() or "tool"
                    _touch_activity()
                    if event_type == "tool_start":
                        status_overrides[name] = TOOL_STATUS_MAP.get(name, f"Running {name}...")
                    elif event_type == "tool_progress":
                        message_text = str(event.get("message") or "").strip()
                        if message_text:
                            status_overrides[name] = message_text
                    elif event_type == "tool_end" and not bool(event.get("ok", True)):
                        status_overrides[name] = f"{name} failed"
                    try:
                        loop.call_soon_threadsafe(status_dirty.set)
                    except RuntimeError:
                        pass

                async def _animate_tool_status() -> None:
                    try:
                        while anim_active:
                            try:
                                await asyncio.wait_for(status_dirty.wait(), timeout=2.0)
                                status_dirty.clear()
                            except asyncio.TimeoutError:
                                pass
                            if not anim_active:
                                break
                            elapsed = max(1, int(time.monotonic() - tool_started_at))
                            animated = _status_text(
                                tool_calls,
                                elapsed_seconds=elapsed,
                                overrides=status_overrides,
                            )
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
                            await _status_update(animated_text)
                    except asyncio.CancelledError:
                        pass

                status_dirty.set()
                anim_task = asyncio.create_task(_animate_tool_status())
                try:
                    tool_future = loop.run_in_executor(
                        None,
                        lambda: process_tool_calls(
                            user_id,
                            new_tool_calls,
                            enabled_tools=enabled_tools,
                            event_callback=_on_tool_event,
                        ),
                    )
                    while True:
                        try:
                            executed_results = await asyncio.wait_for(asyncio.shield(tool_future), timeout=1.0)
                            break
                        except asyncio.TimeoutError:
                            if _activity_age() > effective_timeout:
                                raise asyncio.TimeoutError
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

            messages.append({"role": "user", "content": TOOL_CONTINUE_OR_FINISH_PROMPT})

        combined_response = truncated_prefix + last_text_response if truncated_prefix else last_text_response
        final_text = filter_thinking_content(combined_response).strip()
        if not final_text and last_text_response:
            final_text = filter_thinking_content(last_text_response).strip()
        final_text = post_process_response(user_id, final_text, enabled_tools=enabled_tools).strip()
        if not final_text:
            logger.warning(
                "%s model returned empty visible response (tool_calls=%d last_text_len=%d truncated_len=%d)",
                ctx,
                len(seen_tool_keys),
                len(last_text_response),
                len(truncated_prefix),
            )
            final_text = "(Empty response)"

        await render_pump.drain()
        await render_pump.stop()
        final_delivery_ok = await outbound.deliver_final(final_text)
        final_delivery_confirmed = final_delivery_ok

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
        try:
            await render_pump.stop()
        except Exception:
            pass
        if not final_delivery_confirmed:
            await outbound.deliver_final(build_retry_message())
        record_error(user_id, str(e), "discord chat handler", settings.get("model"), persona_name)
    finally:
        try:
            await render_pump.stop()
        except Exception:
            pass
        await slot_cm.__aexit__(None, None, None)


def _fetch_models(user_id: int) -> list[str]:
    try:
        client = get_ai_client(user_id)
        return client.list_models()
    except Exception:
        logger.exception("Failed to fetch models")
        return []


intents = discord.Intents.default()
intents.message_content = True
_apply_discord_network_overrides()
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
    dctx = _discord_cmd_ctx(ctx)
    logger.info("%s /start", dctx)
    user_id = int(ctx.author.id)
    if not has_api_key(user_id):
        await _send_ctx_reply(ctx, build_start_message_missing_api(DISCORD_COMMAND_PREFIX))
        return

    persona = get_current_persona_name(user_id)
    await _send_ctx_reply(ctx, build_start_message_returning(persona, DISCORD_COMMAND_PREFIX))


@bot.command(name="help")
async def help_command(ctx: commands.Context) -> None:
    logger.info("%s /help", _discord_cmd_ctx(ctx))
    await _send_ctx_reply(ctx, build_help_message(DISCORD_COMMAND_PREFIX))


@bot.command(name="clear")
async def clear_command(ctx: commands.Context) -> None:
    logger.info("%s /clear", _discord_cmd_ctx(ctx))
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
    logger.info("%s /settings", _discord_cmd_ctx(ctx))
    user_id = int(ctx.author.id)
    settings = get_user_settings(user_id)
    persona_name = get_current_persona_name(user_id)
    persona = get_current_persona(user_id)
    token_limit = get_token_limit(user_id, persona_name)

    prompt = persona["system_prompt"]
    prompt_display = prompt[:80] + "..." if len(prompt) > 80 else prompt
    global_prompt = settings.get("global_prompt", "") or ""
    global_prompt_display = global_prompt[:80] + "..." if len(global_prompt) > 80 else global_prompt if global_prompt else "(none)"

    enabled_tools = resolve_enabled_tools_csv(settings) or "(none)"
    cron_tools = resolve_cron_tools_csv(settings) or "(none)"
    tts_voice = settings.get("tts_voice", DEFAULT_TTS_VOICE)
    tts_style = settings.get("tts_style", DEFAULT_TTS_STYLE)
    tts_endpoint = settings.get("tts_endpoint", "") or "auto"
    stream_mode = settings.get("stream_mode", "") or "default"
    presets = settings.get("api_presets", {})
    presets_info = ", ".join(presets.keys()) if presets else "(none)"

    title_model_raw = settings.get("title_model", "")
    title_model_display = title_model_raw or "(current model)"
    cron_model_raw = settings.get("cron_model", "")
    cron_model_display = cron_model_raw or "(current model)"

    text = (
        "Current Settings:\n\n"
        f"base_url: {settings['base_url']}\n"
        f"api_key: {_mask_key(settings['api_key'])}\n"
        f"model: {settings['model']}\n"
        f"temperature: {settings['temperature']}\n"
        f"reasoning_effort: {settings.get('reasoning_effort', '') or '(provider/model default)'}\n"
        f"stream_mode: {stream_mode}\n"
        f"title_model: {title_model_display}\n"
        f"cron_model: {cron_model_display}\n"
        f"persona: {persona_name}\n"
        f"token_limit({persona_name}): {token_limit if token_limit > 0 else 'unlimited'}\n"
        f"global_prompt: {global_prompt_display}\n"
        f"prompt: {prompt_display}\n"
        f"tools: {enabled_tools}\n\n"
        f"cron_tools: {cron_tools}\n\n"
        f"tts_voice: {tts_voice}\n"
        f"tts_style: {tts_style}\n"
        f"tts_endpoint: {tts_endpoint}\n\n"
        f"providers: {presets_info}\n\n"
        f"Use {DISCORD_COMMAND_PREFIX}persona to manage personas and prompts.\n"
        f"Use {DISCORD_COMMAND_PREFIX}chat to manage chat sessions.\n"
        f"Use {DISCORD_COMMAND_PREFIX}set tool <name> <on|off> to manage tools.\n"
        f"Use {DISCORD_COMMAND_PREFIX}set provider to manage API providers."
    )

    await _send_ctx_reply(ctx, text)


@bot.command(name="set")
async def set_command(ctx: commands.Context, *args: str) -> None:
    ctx_log = _discord_cmd_ctx(ctx)
    logger.info("%s /set %s", ctx_log, " ".join(args)[:120] if args else "")
    user_id = int(ctx.author.id)
    settings = get_user_settings(user_id)
    p = DISCORD_COMMAND_PREFIX

    if not args:
        await _send_ctx_reply(ctx, build_set_usage_message(p))
        return

    key = args[0].lower()

    if key == "model" and len(args) == 1:
        if not has_api_key(user_id):
            await _send_ctx_reply(ctx, build_api_key_required_message(DISCORD_COMMAND_PREFIX))
            return

        wait_msg = await ctx.reply("Fetching models...", mention_author=False)
        models = await asyncio.get_running_loop().run_in_executor(None, lambda: _fetch_models(user_id))
        if not models:
            await wait_msg.edit(content="Failed to fetch models. Check your API key and base_url.")
            return

        head = models[:40]
        extra = f"\n...and {len(models) - 40} more" if len(models) > 40 else ""
        await wait_msg.edit(
            content="Available models:\n" + "\n".join(head) + extra
        )
        return

    if len(args) < 2:
        if key == "tool":
            enabled_tools = resolve_enabled_tools_csv(settings)
            enabled_list = [t.strip().lower() for t in enabled_tools.split(",") if t.strip()]
            status = []
            for tool in AVAILABLE_TOOLS:
                icon = "[on]" if tool in enabled_list else "[off]"
                status.append(f"{icon} {tool}")
            await _send_ctx_reply(
                ctx,
                "Tool Settings:\n\n"
                + "\n".join(status)
                + f"\n\nUsage: {p}set tool <name> <on|off>",
            )
            return

        if key == "cron_tool":
            cron_tools = resolve_cron_tools_csv(settings)
            enabled_list = [t.strip().lower() for t in cron_tools.split(",") if t.strip()]
            status = []
            for tool in AVAILABLE_TOOLS:
                icon = "[on]" if tool in enabled_list else "[off]"
                status.append(f"{icon} {tool}")
            await _send_ctx_reply(
                ctx,
                "Cron Tool Settings:\n\n"
                + "\n".join(status)
                + f"\n\nUsage: {p}set cron_tool <name> <on|off>",
            )
            return

        if key == "cron_tools":
            current = settings.get("cron_enabled_tools", "") or "(auto: chat tools without memory)"
            await _send_ctx_reply(
                ctx,
                "Current cron_tools: "
                + current
                + f"\nUsage: {p}set cron_tools <tool1,tool2,...>\n"
                + f"Use {p}set cron_tools clear to reset to auto.",
            )
            return

        if key in {"voice", "style", "endpoint"}:
            setting_key = {
                "voice": "tts_voice",
                "style": "tts_style",
                "endpoint": "tts_endpoint",
            }[key]
            current = settings.get(setting_key, "") or "auto"
            await _send_ctx_reply(ctx, f"Current {key}: {current}\nUsage: {p}set {key} <value>")
            return

        if key == "provider":
            await _show_provider_list(ctx, settings)
            return

        if key == "stream_mode":
            current = settings.get("stream_mode", "") or "default"
            await _send_ctx_reply(
                ctx,
                f"Current stream_mode: {current}\n"
                f"Usage: {p}set stream_mode <mode>\n\n"
                "Available modes:\n"
                "- default: time + chars combined\n"
                "- time: update by time interval\n"
                "- chars: update by character interval",
            )
            return
        if key == "reasoning_effort":
            current = settings.get("reasoning_effort", "") or "(provider/model default)"
            await _send_ctx_reply(
                ctx,
                f"Current reasoning_effort: {current}\n"
                f"Usage: {p}set reasoning_effort <value>\n\n"
                "Available values:\n"
                "- none\n"
                "- minimal\n"
                "- low\n"
                "- medium\n"
                "- high\n"
                "- xhigh\n\n"
                f"Use {p}set reasoning_effort clear to follow provider/model default.",
            )
            return
        if key == "global_prompt":
            current = settings.get("global_prompt", "") or "(none)"
            display = current[:100] + "..." if len(current) > 100 else current
            await _send_ctx_reply(
                ctx,
                f"Current global_prompt: {display}\n\n"
                f"Usage: {p}set global_prompt <prompt>\n"
                f"Use {p}set global_prompt clear to remove.",
            )
            return

        await _send_ctx_reply(ctx, build_set_usage_message(p))
        return

    value = " ".join(args[1:]).strip()

    if key == "base_url":
        update_user_setting(user_id, "base_url", value)
        logger.info("%s set base_url = %s", ctx_log, value)
        await _send_ctx_reply(ctx, f"base_url set to: {value}")
        return

    if key == "api_key":
        update_user_setting(user_id, "api_key", value)
        masked = _mask_key(value)
        logger.info("%s set api_key = %s", ctx_log, masked)
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
                await _send_ctx_reply(ctx, build_api_key_verify_no_models_message(masked))
        except Exception:
            await _send_ctx_reply(ctx, build_api_key_verify_failed_message(masked))
        return

    if key == "model":
        update_user_setting(user_id, "model", value)
        logger.info("%s set model = %s", ctx_log, value)
        await _send_ctx_reply(ctx, f"model set to: {value}")
        return

    if key == "prompt":
        await _send_ctx_reply(ctx, build_prompt_per_persona_message(p))
        return

    if key == "global_prompt":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "global_prompt", "")
            logger.info("%s cleared global_prompt", ctx_log)
            await _send_ctx_reply(
                ctx,
                "global_prompt cleared.\n"
                "Now personas will use their own system prompts only.",
            )
            return
        update_user_setting(user_id, "global_prompt", val)
        logger.info("%s set global_prompt = %s", ctx_log, val[:50] + "..." if len(val) > 50 else val)
        display = val[:100] + "..." if len(val) > 100 else val
        await _send_ctx_reply(
            ctx,
            f"global_prompt set to: {display}\n\n"
            "This prompt will be prepended to all personas' system prompts.\n"
            f"Use {p}set global_prompt clear to remove.",
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
        logger.info("%s set temperature = %s", ctx_log, temp)
        await _send_ctx_reply(ctx, f"temperature set to: {temp}")
        return

    if key == "reasoning_effort":
        val = value.strip().lower()
        if not val or val in {"off", "clear"}:
            update_user_setting(user_id, "reasoning_effort", "")
            logger.info("%s cleared reasoning_effort", ctx_log)
            await _send_ctx_reply(
                ctx,
                "reasoning_effort cleared (follow provider/model default).",
            )
            return

        if val not in VALID_REASONING_EFFORTS:
            await _send_ctx_reply(
                ctx,
                "Invalid reasoning_effort. Available: none, minimal, low, medium, high, xhigh.",
            )
            return

        update_user_setting(user_id, "reasoning_effort", val)
        logger.info("%s set reasoning_effort = %s", ctx_log, val)
        await _send_ctx_reply(ctx, f"reasoning_effort set to: {val}")
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
        logger.info("%s set token_limit = %s (persona=%s)", ctx_log, limit, persona_name)
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
        logger.info("%s set voice = %s", ctx_log, value)
        await _send_ctx_reply(ctx, f"voice set to: {value}")
        return

    if key == "style":
        style = value.lower()
        if not style:
            await _send_ctx_reply(ctx, "Style cannot be empty")
            return
        update_user_setting(user_id, "tts_style", style)
        logger.info("%s set style = %s", ctx_log, style)
        await _send_ctx_reply(ctx, f"style set to: {style}")
        return

    if key == "endpoint":
        if value.lower() in {"auto", "default", "off"}:
            update_user_setting(user_id, "tts_endpoint", "")
            logger.info("%s set endpoint = auto", ctx_log)
            await _send_ctx_reply(ctx, "endpoint set to: auto")
            return

        normalized = normalize_tts_endpoint(value)
        if not normalized:
            await _send_ctx_reply(ctx, build_endpoint_invalid_message(p))
            return

        update_user_setting(user_id, "tts_endpoint", normalized)
        logger.info("%s set endpoint = %s", ctx_log, normalized)
        await _send_ctx_reply(ctx, f"endpoint set to: {normalized}")
        return

    if key == "tool":
        if len(args) < 3:
            await _send_ctx_reply(ctx, f"Usage: {p}set tool <name> <on|off>")
            return

        tool_name = args[1].lower()
        action = args[2].lower()

        if tool_name not in AVAILABLE_TOOLS:
            await _send_ctx_reply(
                ctx,
                f"Unknown/unsupported tool: {tool_name}. Available: {', '.join(AVAILABLE_TOOLS)}",
            )
            return

        enabled_tools = resolve_enabled_tools_csv(settings)
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

        update_user_setting(user_id, "enabled_tools", normalize_tools_csv(",".join(enabled_list)))
        logger.info("%s set tool %s = %s", ctx_log, tool_name, action)
        await _send_ctx_reply(ctx, f"Tool {tool_name} set to {action}")
        return

    if key == "cron_tool":
        if len(args) < 3:
            await _send_ctx_reply(ctx, f"Usage: {p}set cron_tool <name> <on|off>")
            return

        tool_name = args[1].lower()
        action = args[2].lower()

        if tool_name not in AVAILABLE_TOOLS:
            await _send_ctx_reply(
                ctx,
                f"Unknown/unsupported tool: {tool_name}. Available: {', '.join(AVAILABLE_TOOLS)}",
            )
            return

        cron_tools = resolve_cron_tools_csv(settings)
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

        new_enabled = normalize_tools_csv(",".join(enabled_list))
        update_user_setting(user_id, "cron_enabled_tools", new_enabled)
        logger.info("%s set cron_tool %s = %s", ctx_log, tool_name, action)
        await _send_ctx_reply(ctx, f"Cron tool {tool_name} set to {action}")
        return

    if key == "cron_tools":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none", "default"}:
            update_user_setting(user_id, "cron_enabled_tools", "")
            logger.info("%s cleared cron_enabled_tools (auto mode)", ctx_log)
            await _send_ctx_reply(
                ctx,
                "cron_tools cleared.\n"
                "Now cron tasks will auto-use chat tools without memory.",
            )
            return

        normalized = normalize_tools_csv(val)
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
        logger.info("%s set cron_enabled_tools = %s", ctx_log, normalized)
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
        await _handle_provider_command(ctx, user_id, settings, list(args[1:]), ctx_log)
        return

    if key == "title_model":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "title_model", "")
            logger.info("%s cleared title_model", ctx_log)
            await _send_ctx_reply(ctx, "title_model cleared (will use current provider + model)")
        else:
            update_user_setting(user_id, "title_model", val)
            logger.info("%s set title_model = %s", ctx_log, val)
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
                        f"{build_provider_save_hint_message(p)}",
                    )
            else:
                await _send_ctx_reply(
                    ctx,
                    f"title_model set to: {val}\n"
                    "(uses current provider's API)",
                )
        return

    if key == "cron_model":
        val = value.strip()
        if not val or val.lower() in {"off", "clear", "none"}:
            update_user_setting(user_id, "cron_model", "")
            logger.info("%s cleared cron_model", ctx_log)
            await _send_ctx_reply(ctx, "cron_model cleared (will use current provider + model)")
        else:
            update_user_setting(user_id, "cron_model", val)
            logger.info("%s set cron_model = %s", ctx_log, val)
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
                        f"{build_provider_save_hint_message(p)}",
                    )
            else:
                await _send_ctx_reply(
                    ctx,
                    f"cron_model set to: {val}\n"
                    "(uses current provider's API)",
                )
        return

    if key == "stream_mode":
        mode = value.lower()
        if mode in {"default", "time", "chars"}:
            update_user_setting(user_id, "stream_mode", mode)
            logger.info("%s set stream_mode = %s", ctx_log, mode)
            await _send_ctx_reply(
                ctx,
                f"stream_mode set to: {mode}\n"
                "Applies to both Telegram and Discord streaming output.",
            )
        elif mode in {"", "off", "clear", "none"}:
            update_user_setting(user_id, "stream_mode", "")
            logger.info("%s cleared stream_mode", ctx_log)
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
                f"Usage: {p}set stream_mode <mode>\n\n"
                "Available modes:\n"
                "- default: time + chars combined\n"
                "- time: update by time interval\n"
                "- chars: update by character interval",
            )
        return

    await _send_ctx_reply(ctx, build_unknown_set_key_message(key))


async def _show_provider_list(ctx: commands.Context, settings: dict) -> None:
    p = DISCORD_COMMAND_PREFIX
    presets = settings.get("api_presets", {})
    if not presets:
        await _send_ctx_reply(ctx, build_provider_no_saved_message(p))
        return

    lines = ["Saved Providers:\n"]
    for name, preset in presets.items():
        lines.append(
            f"[{name}]\n"
            f"  base_url: {preset.get('base_url', '')}\n"
            f"  api_key: {_mask_key(preset.get('api_key', ''))}\n"
            f"  model: {preset.get('model', '')}"
        )

    lines.append(build_provider_list_usage_message(p))
    await _send_ctx_reply(ctx, "\n".join(lines))


async def _handle_provider_command(
    ctx: commands.Context,
    user_id: int,
    settings: dict,
    args: list[str],
    ctx_log: str,
) -> None:
    p = DISCORD_COMMAND_PREFIX
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
            await _send_ctx_reply(ctx, f"Usage: {p}set provider save <name>")
            return

        name = args[1]
        presets[name] = {
            "api_key": settings["api_key"],
            "base_url": settings["base_url"],
            "model": settings["model"],
        }
        update_user_setting(user_id, "api_presets", presets)
        logger.info("%s provider save %s", ctx_log, name)
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
            await _send_ctx_reply(ctx, f"Usage: {p}set provider delete <name>")
            return

        name = args[1]
        if name not in presets:
            await _send_ctx_reply(ctx, f"Provider '{name}' not found.")
            return

        del presets[name]
        update_user_setting(user_id, "api_presets", presets)
        logger.info("%s provider delete %s", ctx_log, name)
        await _send_ctx_reply(ctx, f"Provider '{name}' deleted.")
        return

    if sub == "load":
        if len(args) < 2:
            await _send_ctx_reply(ctx, f"Usage: {p}set provider load <name>")
            return

        name = args[1]
        if name not in presets:
            matched = next((k for k in presets if k.lower() == name.lower()), None)
            if matched is None:
                available = ", ".join(presets.keys()) if presets else "(none)"
                await _send_ctx_reply(ctx, build_provider_not_found_available_message(name, available))
                return
            name = matched

        preset = presets[name]
        update_user_setting(user_id, "api_key", preset["api_key"])
        update_user_setting(user_id, "base_url", preset["base_url"])
        update_user_setting(user_id, "model", preset["model"])
        logger.info("%s provider load %s", ctx_log, name)

        await _send_ctx_reply(
            ctx,
            f"Loaded provider '{name}':\n"
            f"  base_url: {preset['base_url']}\n"
            f"  api_key: {_mask_key(preset.get('api_key', ''))}\n"
            f"  model: {preset['model']}",
        )
        return

    await _send_ctx_reply(ctx, build_provider_usage_message(p))


@bot.command(name="usage")
async def usage_command(ctx: commands.Context, *args: str) -> None:
    logger.info("%s /usage %s", _discord_cmd_ctx(ctx), " ".join(args) if args else "")
    user_id = int(ctx.author.id)
    persona_name = get_current_persona_name(user_id)

    if args and args[0].lower() == "reset":
        reset_token_usage(user_id, persona_name)
        await _send_ctx_reply(ctx, build_usage_reset_message(persona_name))
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
    logger.info("%s /export", _discord_cmd_ctx(ctx))
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
    ctx_log = _discord_cmd_ctx(ctx)
    logger.info("%s /remember", ctx_log)
    user_id = int(ctx.author.id)
    if not content:
        await _send_ctx_reply(ctx, build_remember_usage_message(DISCORD_COMMAND_PREFIX))
        return

    add_memory(user_id, content, source="user")
    logger.info("%s /remember content=%s", ctx_log, content[:80])
    await _send_ctx_reply(ctx, f"Remembered: {content}")


@bot.command(name="memories")
async def memories_command(ctx: commands.Context) -> None:
    logger.info("%s /memories", _discord_cmd_ctx(ctx))
    user_id = int(ctx.author.id)
    memories = get_memories(user_id)

    if not memories:
        await _send_ctx_reply(ctx, build_memory_empty_message(DISCORD_COMMAND_PREFIX))
        return

    lines = ["Your memories:\n"]
    for i, mem in enumerate(memories, 1):
        source_tag = "[AI]" if mem["source"] == "ai" else "[user]"
        lines.append(f"{i}. {source_tag} {mem['content']}")

    lines.append(build_memory_list_footer_message(DISCORD_COMMAND_PREFIX))

    await _send_ctx_reply(ctx, "\n".join(lines))


@bot.command(name="forget")
async def forget_command(ctx: commands.Context, target: str | None = None) -> None:
    logger.info("%s /forget %s", _discord_cmd_ctx(ctx), target or "")
    user_id = int(ctx.author.id)

    if not target:
        await _send_ctx_reply(ctx, build_forget_usage_message(DISCORD_COMMAND_PREFIX))
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
        await _send_ctx_reply(ctx, build_forget_invalid_target_message(DISCORD_COMMAND_PREFIX))
        return

    if delete_memory(user_id, index):
        await _send_ctx_reply(ctx, f"Memory #{index} deleted.")
    else:
        await _send_ctx_reply(ctx, build_invalid_memory_number_message(index, DISCORD_COMMAND_PREFIX))


@bot.command(name="persona")
async def persona_command(ctx: commands.Context, *args: str) -> None:
    ctx_log = _discord_cmd_ctx(ctx)
    logger.info("%s /persona %s", ctx_log, " ".join(args) if args else "")
    user_id = int(ctx.author.id)
    p = DISCORD_COMMAND_PREFIX

    if not args:
        logger.info("%s /persona list", ctx_log)
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
            msg_count = get_message_count(session_id)
            session_ct = get_session_count(user_id, name)
            prompt_preview = persona["system_prompt"][:30]
            if len(persona["system_prompt"]) > 30:
                prompt_preview += "..."

            lines.append(f"{marker}{name}")
            lines.append(f"    {msg_count} msgs | {session_ct} sessions | {usage['total_tokens']:,} tokens")
            lines.append(f"    {prompt_preview}")
            lines.append("")

        lines.append(build_persona_commands_message(p))

        await _send_ctx_reply(ctx, "\n".join(lines))
        return

    subcmd = args[0].lower()

    if subcmd == "new":
        if len(args) < 2:
            await _send_ctx_reply(ctx, build_persona_new_usage_message(p))
            return

        name = args[1]
        prompt = " ".join(args[2:]) if len(args) > 2 else None
        if create_persona(user_id, name, prompt):
            switch_persona(user_id, name)
            logger.info("%s /persona new %s", ctx_log, name)
            await _send_ctx_reply(ctx, build_persona_created_message(name, p))
        else:
            await _send_ctx_reply(ctx, f"Persona '{name}' already exists.")
        return

    if subcmd == "delete":
        if len(args) < 2:
            await _send_ctx_reply(ctx, f"Usage: {p}persona delete <name>")
            return

        name = args[1]
        if name == "default":
            await _send_ctx_reply(ctx, "Cannot delete the default persona.")
            return

        if delete_persona(user_id, name):
            logger.info("%s /persona delete %s", ctx_log, name)
            await _send_ctx_reply(ctx, f"Deleted persona: {name}")
        else:
            await _send_ctx_reply(ctx, f"Persona '{name}' not found.")
        return

    if subcmd == "prompt":
        if len(args) < 2:
            persona = get_current_persona(user_id)
            await _send_ctx_reply(
                ctx,
                build_persona_prompt_overview_message(
                    persona["name"],
                    persona["system_prompt"],
                    p,
                ),
            )
            return

        prompt = " ".join(args[1:])
        update_current_prompt(user_id, prompt)
        name = get_current_persona_name(user_id)
        logger.info("%s /persona prompt (persona=%s)", ctx_log, name)
        await _send_ctx_reply(ctx, f"Updated prompt for '{name}'.")
        return

    name = args[0]
    if not persona_exists(user_id, name):
        await _send_ctx_reply(ctx, build_persona_not_found_message(name, p))
        return

    switch_persona(user_id, name)
    logger.info("%s /persona switch %s", ctx_log, name)
    persona = get_current_persona(user_id)
    usage = get_token_usage(user_id, name)
    session_id = ensure_session(user_id, name)
    msg_count = get_message_count(session_id)
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
    ctx_log = _discord_cmd_ctx(ctx)
    logger.info("%s /chat %s", ctx_log, " ".join(args) if args else "")
    user_id = int(ctx.author.id)
    persona_name = get_current_persona_name(user_id)
    p = DISCORD_COMMAND_PREFIX

    if not args:
        logger.info("%s /chat list", ctx_log)
        sessions = get_sessions(user_id, persona_name)
        current_id = get_current_session_id(user_id, persona_name)

        if not sessions:
            await _send_ctx_reply(ctx, build_chat_no_sessions_message(persona_name, p))
            return

        lines = [f"Sessions (persona: {persona_name})\n"]
        for i, session in enumerate(sessions, 1):
            marker = "> " if session["id"] == current_id else "  "
            title = session.get("title") or "New Chat"
            msg_count = get_session_message_count(session["id"])
            lines.append(f"{marker}{i}. {title} ({msg_count} msgs)")

        lines.append("")
        lines.append(build_chat_commands_message(p))

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
        logger.info("%s /chat new (session_id=%s)", ctx_log, session["id"])
        return

    if subcmd == "rename":
        if len(args) < 2:
            await _send_ctx_reply(ctx, f"Usage: {p}chat rename <title>")
            return

        title = " ".join(args[1:])
        if rename_session(user_id, title, persona_name):
            logger.info("%s /chat rename '%s'", ctx_log, title)
            await _send_ctx_reply(ctx, f"Session renamed to: {title}")
        else:
            await _send_ctx_reply(ctx, "No current session to rename.")
        return

    if subcmd == "delete":
        if len(args) < 2:
            await _send_ctx_reply(ctx, f"Usage: {p}chat delete <number>")
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
            logger.info("%s /chat delete %d", ctx_log, index)
            await _send_ctx_reply(ctx, f"Deleted session: {display_title}")
        else:
            await _send_ctx_reply(ctx, "Failed to delete session.")
        return

    try:
        index = int(subcmd)
    except ValueError:
        await _send_ctx_reply(ctx, build_chat_unknown_subcommand_message(p))
        return

    if switch_session(user_id, index, persona_name):
        sessions = get_sessions(user_id, persona_name)
        session = sessions[index - 1]
        display_title = session.get("title") or "New Chat"
        msg_count = get_session_message_count(session["id"])
        logger.info("%s /chat switch %d", ctx_log, index)
        await _send_ctx_reply(
            ctx,
            f"Switched to session #{index}: {display_title}\nMessages: {msg_count}",
        )
    else:
        total = len(get_sessions(user_id, persona_name))
        await _send_ctx_reply(ctx, f"Invalid session number. Valid range: 1-{total}")


@bot.command(name="web")
async def web_command(ctx: commands.Context) -> None:
    logger.info("%s /web", _discord_cmd_ctx(ctx))
    user_id = int(ctx.author.id)
    token = create_short_token(user_id)
    # Include both query + hash token to handle Discord/mobile link rewrites.
    url = f"{WEB_BASE_URL.rstrip('/')}/?token={token}#token={token}"
    text = build_web_dashboard_message(url)

    try:
        await ctx.author.send(text)
        if ctx.guild:
            await _send_ctx_reply(ctx, build_web_dm_sent_message())
    except Exception:
        await _send_ctx_reply(ctx, build_web_dm_failed_message())


def main() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables")
        return

    init_database()
    prewarm_browser_tools()

    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    logger.info("Starting Discord bot...")
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
