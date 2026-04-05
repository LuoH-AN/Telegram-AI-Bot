"""General help and startup messages."""

from __future__ import annotations


def format_log_context(*, platform: str, user_id: int, scope: str, chat_id: int) -> str:
    return f"[platform={platform} user={user_id} scope={scope} chat={chat_id}]"


def build_start_message_missing_api(prefix: str) -> str:
    return (
        "Welcome to AI Bot!\n\n"
        "First, set your API key:\n"
        f"{prefix}set api_key YOUR_API_KEY\n\n"
        "Optional configuration:\n"
        f"{prefix}set base_url <url> - API endpoint\n"
        f"{prefix}set model <name> - choose model\n\n"
        f"Type {prefix}help for all commands."
    )


def build_start_message_returning(persona: str, prefix: str) -> str:
    return (
        f"Welcome back! Current persona: {persona}\n\n"
        f"Send a message to chat, or use {prefix}help for commands."
    )


def build_help_message(prefix: str) -> str:
    return (
        "AI Bot Help\n\n"
        "Send text, images, or files to chat with AI.\n"
        "AI can use installed tools during chat when the current model supports them.\n\n"
        "In groups/servers: mention the bot or reply to a bot message\n"
        "In private chats/DMs: direct chat works\n\n"
        "Commands:\n"
        f"{prefix}start - show welcome message\n"
        f"{prefix}help - show this help\n"
        f"{prefix}persona - manage personas\n"
        f"{prefix}chat - manage sessions\n"
        f"{prefix}settings - view settings\n"
        f"{prefix}set <key> <value> - modify settings\n"
        f"{prefix}stop - stop active response\n"
        f"{prefix}remember <text> - add memory\n"
        f"{prefix}memories - view memories\n"
        f"{prefix}forget <num|all> - delete memory\n"
        f"{prefix}usage - view usage\n"
        f"{prefix}export - export conversation\n"
        f"{prefix}clear - clear conversation\n"
        f"{prefix}web - open dashboard"
    )
