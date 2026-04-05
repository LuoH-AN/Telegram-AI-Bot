"""Basic command handlers shared by all platforms."""

from __future__ import annotations

import asyncio

from core.settings import get_settings_view_text
from services import (
    clear_conversation,
    ensure_session,
    get_current_persona_name,
    has_api_key,
    reset_token_usage,
    run_hot_update,
    schedule_process_restart,
)
from services.platform import apply_provider_command, build_provider_list_text
from services.runtime_queue import cancel_user_responses
from utils.platform_parity import build_help_message, build_start_message_missing_api, build_start_message_returning


async def start_command(ctx, command_prefix: str) -> None:
    user_id = ctx.local_user_id
    if not has_api_key(user_id):
        await ctx.reply_text(build_start_message_missing_api(command_prefix))
        return
    await ctx.reply_text(build_start_message_returning(get_current_persona_name(user_id), command_prefix))


async def help_command(ctx, command_prefix: str) -> None:
    await ctx.reply_text(build_help_message(command_prefix))


async def clear_command(ctx) -> None:
    user_id = ctx.local_user_id
    persona_name = get_current_persona_name(user_id)
    clear_conversation(ensure_session(user_id, persona_name))
    reset_token_usage(user_id)
    await ctx.reply_text(f"Conversation cleared and usage reset for persona '{persona_name}'.")


async def stop_command(ctx, *, platform: str) -> None:
    cancelled = cancel_user_responses(ctx.local_chat_id, ctx.local_user_id, platform=platform)
    await ctx.reply_text(f"Stopped {len(cancelled)} active response(s)." if cancelled else "No active responses to stop.")


async def update_command(ctx, command_prefix: str) -> None:
    await ctx.reply_text("Starting hot update: fetching latest code...")
    result = await asyncio.to_thread(run_hot_update)
    if not result.get("ok"):
        await ctx.reply_text(f"Update failed:\n{result.get('message')}")
        return
    if not result.get("changed"):
        await ctx.reply_text(result.get("message") or "Already up to date.")
        return
    await ctx.reply_text(
        "Update applied successfully.\n"
        f"Branch: {result.get('branch')}\n"
        f"Commit: {result.get('old', '')[:7]} -> {result.get('new', '')[:7]}\n"
        "Restarting bot processes now..."
    )
    schedule_process_restart()


async def settings_command(ctx, command_prefix: str) -> None:
    await ctx.reply_text(get_settings_view_text(ctx.local_user_id, command_prefix=command_prefix))


async def show_provider_list(ctx, settings: dict, command_prefix: str) -> None:
    await ctx.reply_text(build_provider_list_text(settings, command_prefix=command_prefix))


async def handle_provider_command(ctx, user_id: int, settings: dict, args: list[str], command_prefix: str) -> None:
    await ctx.reply_text(apply_provider_command(user_id, settings, args, command_prefix=command_prefix))
