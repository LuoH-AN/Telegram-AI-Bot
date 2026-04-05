"""Provider preset management message builders."""

from __future__ import annotations


def build_provider_save_hint_message(prefix: str) -> str:
    return f"Use {prefix}set provider save <name> to save a configuration first."


def build_provider_no_saved_message(prefix: str) -> str:
    return (
        "No saved provider configurations.\n\n"
        "Usage:\n"
        f"{prefix}set provider save <name> - save current API config\n"
        f"{prefix}set provider load <name> - load saved config\n"
        f"{prefix}set provider delete <name> - delete saved config"
    )


def build_provider_usage_message(prefix: str) -> str:
    return (
        "Usage:\n"
        f"{prefix}set provider list\n"
        f"{prefix}set provider save <name>\n"
        f"{prefix}set provider load <name>\n"
        f"{prefix}set provider delete <name>"
    )


def build_provider_list_usage_message(prefix: str) -> str:
    return (
        "\nUsage:\n"
        f"{prefix}set provider save <name>\n"
        f"{prefix}set provider load <name>\n"
        f"{prefix}set provider delete <name>"
    )


def build_provider_not_found_available_message(name: str, available: str) -> str:
    return f"Provider '{name}' does not exist.\nAvailable: {available}"
