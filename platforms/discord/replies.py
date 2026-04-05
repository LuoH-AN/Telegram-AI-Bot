"""Discord reply and streaming preview helpers."""

from __future__ import annotations

import discord
from discord.ext import commands

from utils import split_message

from .config import DISCORD_MAX_MESSAGE_LENGTH, STREAM_PREVIEW_PREFIX


def normalize_discord_output_text(text: str) -> str:
    return (
        (text or "")
        .replace("\x02BQXSTART\x02", "```\n")
        .replace("\x02BQSTART\x02", "```\n")
        .replace("\x02BQXEND\x02", "\n```")
        .replace("\x02BQEND\x02", "\n```")
    )


def build_stream_preview(display_text: str, *, thinking_prefix: str = "", cursor: bool = True) -> str:
    suffix = " ▌" if cursor else ""
    text = f"{thinking_prefix}{display_text}{suffix}"
    if len(text) <= DISCORD_MAX_MESSAGE_LENGTH:
        return text
    keep = DISCORD_MAX_MESSAGE_LENGTH - len(STREAM_PREVIEW_PREFIX)
    if keep <= 0:
        return STREAM_PREVIEW_PREFIX[:DISCORD_MAX_MESSAGE_LENGTH]
    return STREAM_PREVIEW_PREFIX + text[-keep:]


async def safe_edit_message(message: discord.Message, text: str) -> bool:
    try:
        trimmed = normalize_discord_output_text(text) if text else "(Empty response)"
        if len(trimmed) > DISCORD_MAX_MESSAGE_LENGTH:
            trimmed = trimmed[: DISCORD_MAX_MESSAGE_LENGTH - 3] + "..."
        await message.edit(content=trimmed)
        return True
    except Exception:
        return False


async def send_text_reply(message: discord.Message, text: str) -> None:
    normalized = normalize_discord_output_text(text or "(Empty response)")
    chunks = split_message(normalized, max_length=DISCORD_MAX_MESSAGE_LENGTH)
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(chunk, mention_author=False)
        else:
            await message.channel.send(chunk)


async def send_ctx_reply(ctx: commands.Context, text: str) -> None:
    normalized = normalize_discord_output_text(text or "(Empty response)")
    chunks = split_message(normalized, max_length=DISCORD_MAX_MESSAGE_LENGTH)
    for i, chunk in enumerate(chunks):
        if i == 0:
            await ctx.reply(chunk, mention_author=False)
        else:
            await ctx.send(chunk)
