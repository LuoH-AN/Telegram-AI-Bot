"""Discord mention/reply routing helpers."""

from __future__ import annotations

import discord
from discord.ext import commands


async def extract_reply_context(message: discord.Message) -> str:
    if not message.reference or not message.reference.message_id:
        return ""
    ref = message.reference.resolved
    quoted_msg: discord.Message | None = ref if isinstance(ref, discord.Message) else None
    if quoted_msg is None:
        try:
            quoted_msg = await message.channel.fetch_message(message.reference.message_id)
        except Exception:
            return ""
    quoted_text = quoted_msg.content.strip() if quoted_msg else ""
    if not quoted_text:
        return ""
    sender = quoted_msg.author.display_name if quoted_msg and quoted_msg.author else "Unknown"
    return f"[Quoted message from {sender}]:\n{quoted_text}"


async def should_respond_in_channel(bot: commands.Bot, message: discord.Message) -> bool:
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


def strip_bot_mentions(text: str, bot_user_id: int | None) -> str:
    if not bot_user_id:
        return text.strip()
    stripped = text or ""
    stripped = stripped.replace(f"<@{bot_user_id}>", "")
    stripped = stripped.replace(f"<@!{bot_user_id}>", "")
    return stripped.strip()
