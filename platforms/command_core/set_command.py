"""Top-level `/set` command orchestration."""

from __future__ import annotations

from services import get_user_settings
from utils.platform_parity import build_set_usage_message, build_unknown_set_key_message

from .basic import handle_provider_command, show_provider_list
from .set_core import handle_set_core
from .set_help import handle_set_without_value
from .set_runtime import handle_set_runtime
from .set_special import handle_specialized_model_set


async def set_command(
    ctx,
    command_prefix: str,
    *args: str,
    show_model_list_cb=None,
) -> None:
    user_id = ctx.local_user_id
    settings = get_user_settings(user_id)
    if not args:
        await ctx.reply_text(build_set_usage_message(command_prefix))
        return
    key = args[0].lower().strip()
    if len(args) < 2:
        async def _show_provider_list() -> None:
            await show_provider_list(ctx, settings, command_prefix)

        await handle_set_without_value(
            ctx,
            user_id=user_id,
            settings=settings,
            key=key,
            command_prefix=command_prefix,
            show_provider_list_cb=_show_provider_list,
            show_model_list_cb=show_model_list_cb,
        )
        return
    value = " ".join(args[1:]).strip()
    if key == "provider":
        await handle_provider_command(ctx, user_id, settings, list(args[1:]), command_prefix)
        return
    if key in {"title_model", "cron_model"}:
        await handle_specialized_model_set(
            ctx,
            user_id=user_id,
            settings=settings,
            key=key,
            value=value,
            command_prefix=command_prefix,
        )
        return
    if await handle_set_core(ctx, user_id=user_id, key=key, value=value, command_prefix=command_prefix):
        return
    if await handle_set_runtime(
        ctx,
        user_id=user_id,
        settings=settings,
        key=key,
        value=value,
        command_prefix=command_prefix,
    ):
        return
    await ctx.reply_text(build_unknown_set_key_message(key))
