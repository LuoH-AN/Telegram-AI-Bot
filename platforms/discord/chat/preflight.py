"""Preflight and context assembly for Discord chat handling."""

from __future__ import annotations

import time
from dataclasses import dataclass

import discord
from discord.ext import commands

from services import ensure_session, get_conversation, get_current_persona_name, get_remaining_tokens, get_user_settings, has_api_key
from services.platform_shared import normalize_reasoning_effort, normalize_stream_mode
from services.refresh import ensure_user_state
from utils.platform_parity import build_api_key_required_message, build_token_limit_reached_message

from ..config import DISCORD_COMMAND_PREFIX, STREAM_UPDATE_MODE
from ..context import discord_ctx
from ..message.content import build_user_content_from_message, extract_reply_context, strip_bot_mentions
from ..replies import send_text_reply


@dataclass
class ChatPreflight:
    user_id: int
    log_ctx: str
    persona_name: str
    settings: dict
    stream_mode: str
    reasoning_effort: str
    show_thinking: bool
    session_id: int
    conversation: list
    request_start: float
    user_content: str | list[dict]
    save_msg: str


async def run_preflight(bot: commands.Bot, message: discord.Message) -> ChatPreflight | None:
    user_id = int(message.author.id)
    log_ctx = discord_ctx(message.guild.id if message.guild else None, message.channel.id, user_id)
    ensure_user_state(user_id)
    raw_text = strip_bot_mentions(message.content or "", bot.user.id if bot.user else None)
    quoted = await extract_reply_context(message)
    if quoted:
        raw_text = f"{quoted}\n\n{raw_text}" if raw_text else quoted
    user_content, save_msg = await build_user_content_from_message(message, raw_text)
    if isinstance(user_content, str) and not user_content.strip():
        await send_text_reply(message, "Please send a text message or attachment.")
        return None
    if not has_api_key(user_id):
        await send_text_reply(message, build_api_key_required_message(DISCORD_COMMAND_PREFIX))
        return None
    persona_name = get_current_persona_name(user_id)
    remaining = get_remaining_tokens(user_id, persona_name)
    if remaining is not None and remaining <= 0:
        await send_text_reply(message, build_token_limit_reached_message(DISCORD_COMMAND_PREFIX, persona_name))
        return None
    settings = get_user_settings(user_id)
    stream_mode = normalize_stream_mode(settings.get("stream_mode", "") or STREAM_UPDATE_MODE)
    reasoning_effort = normalize_reasoning_effort(settings.get("reasoning_effort", ""))
    session_id = ensure_session(user_id, persona_name)
    return ChatPreflight(
        user_id=user_id,
        log_ctx=log_ctx,
        persona_name=persona_name,
        settings=settings,
        stream_mode=stream_mode,
        reasoning_effort=reasoning_effort,
        show_thinking=bool(settings.get("show_thinking")),
        session_id=session_id,
        conversation=list(get_conversation(session_id)),
        request_start=time.monotonic(),
        user_content=user_content,
        save_msg=save_msg,
    )
