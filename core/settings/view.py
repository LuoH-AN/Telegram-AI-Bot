"""Shared settings view use case."""

from services.platform import build_settings_text


def get_settings_view_text(user_id: int, *, command_prefix: str) -> str:
    return build_settings_text(user_id, command_prefix=command_prefix)
