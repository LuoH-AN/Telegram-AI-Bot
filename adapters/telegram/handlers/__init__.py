"""Telegram handlers module."""

from importlib import import_module

_COMMAND_EXPORTS = {
    "start",
    "help_command",
    "clear",
    "stop",
    "update",
    "restart",
    "status",
    "settings_command",
    "set_command",
    "usage_command",
    "export_command",
    "remember_command",
    "memories_command",
    "forget_command",
    "persona_command",
    "chat_command",
    "skill_command",
}
_MESSAGE_EXPORTS = {"chat", "handle_photo", "handle_document"}
_CALLBACK_EXPORTS = {"model_callback", "help_callback"}
_COMMON_EXPORTS = {"should_respond_in_group"}

__all__ = [
    "start",
    "help_command",
    "clear",
    "stop",
    "restart",
    "update",
    "status",
    "settings_command",
    "set_command",
    "usage_command",
    "export_command",
    "remember_command",
    "memories_command",
    "forget_command",
    "persona_command",
    "chat_command",
    "skill_command",
    "chat",
    "handle_photo",
    "handle_document",
    "model_callback",
    "help_callback",
    "should_respond_in_group",
]


def __getattr__(name: str):
    if name in _COMMAND_EXPORTS:
        module = import_module("adapters.telegram.commands")
    elif name in _MESSAGE_EXPORTS:
        module = import_module("adapters.telegram.handlers.messages")
    elif name in _CALLBACK_EXPORTS:
        module = import_module("adapters.telegram.handlers.callback")
    elif name in _COMMON_EXPORTS:
        module = import_module("adapters.telegram.handlers.common")
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(module, name)
    globals()[name] = value
    return value
