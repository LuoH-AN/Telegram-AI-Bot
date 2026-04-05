"""Provider subcommand use cases."""

from services import get_user_settings
from services.platform_shared import apply_provider_command, build_provider_list_text


def show_provider_list(user_id: int, *, command_prefix: str) -> str:
    settings = get_user_settings(user_id)
    return build_provider_list_text(settings, command_prefix=command_prefix)


def run_provider_command(
    user_id: int,
    args: list[str],
    *,
    command_prefix: str,
) -> str:
    settings = get_user_settings(user_id)
    return apply_provider_command(
        user_id,
        settings,
        args,
        command_prefix=command_prefix,
    )

