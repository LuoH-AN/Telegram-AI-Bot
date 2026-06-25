"""`/set` command orchestration and provider helpers."""

from __future__ import annotations

from telegram import Message

from domain.services import get_user_settings
from domain.services.platform import apply_provider_command, build_provider_list_text
from shared.utils.platform import build_set_usage_message, build_unknown_set_key_message
from adapters.telegram.rich_text import reply_rich_text

from .core import handle_set_core
from .help import handle_set_without_value
from .model import handle_specialized_model_set
from .runtime import handle_set_runtime


async def show_provider_list(message: Message, settings: dict, command_prefix: str) -> None:
    await reply_rich_text(message, build_provider_list_text(settings, command_prefix=command_prefix))


async def handle_provider_command(
    message: Message, user_id: int, settings: dict, args: list[str], command_prefix: str
) -> None:
    await reply_rich_text(
        message, apply_provider_command(user_id, settings, args, command_prefix=command_prefix)
    )


async def run_set(
    message: Message,
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
    show_model_list_cb=None,
) -> None:
    settings = get_user_settings(user_id)
    if not args:
        await reply_rich_text(message, build_set_usage_message(command_prefix))
        return
    key = args[0].lower().strip()
    if len(args) < 2:
        async def _show_provider_list() -> None:
            await show_provider_list(message, settings, command_prefix)

        await handle_set_without_value(
            message,
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
        await handle_provider_command(message, user_id, settings, list(args[1:]), command_prefix)
        return
    if key in {"title_model", "cron_model"}:
        await handle_specialized_model_set(
            message, user_id=user_id, settings=settings, key=key, value=value, command_prefix=command_prefix
        )
        return
    if await handle_set_core(message, user_id=user_id, key=key, value=value, command_prefix=command_prefix):
        return
    if await handle_set_runtime(
        message, user_id=user_id, settings=settings, key=key, value=value, command_prefix=command_prefix
    ):
        return
    await reply_rich_text(message, build_unknown_set_key_message(key))
