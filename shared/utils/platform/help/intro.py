"""General help and startup messages."""

from __future__ import annotations

from collections.abc import Iterable


def format_log_context(*, platform: str, user_id: int, scope: str, chat_id: int) -> str:
    return f"[platform={platform} user={user_id} scope={scope} chat={chat_id}]"


def build_start_message_missing_api(prefix: str) -> str:
    return (
        "👋 **Welcome to AI Bot!**\n\n"
        "🔑 **First, set your API key:**\n"
        f"`{prefix}set api_key YOUR_API_KEY`\n\n"
        "**Optional configuration:**\n"
        f"• `{prefix}set base_url <url>` - API endpoint\n"
        f"• `{prefix}set model <name>` - choose model\n\n"
        f"💡 Type `{prefix}help` for all commands."
    )


def build_start_message_returning(persona: str, prefix: str) -> str:
    return (
        f"👋 **Welcome back!**\n\n"
        f"Current persona: `{persona}`\n\n"
        f"💡 Send a message to chat, or use `{prefix}help` for commands."
    )


def build_help_message(prefix: str, groups: Iterable[tuple[str, Iterable[tuple[str, str]]]]) -> str:
    lines = [
        "📚 **AI Bot Help**\n",
        "Send text, images, or files to chat with AI.",
        "AI can use installed tools during chat when the current model supports them.\n",
        "📍 **In groups:** mention the bot or reply to a bot message",
        "📍 **In private chats/DMs:** direct chat works",
    ]
    for category, commands in groups:
        lines.append(f"\n**{category}**")
        for usage, help in commands:
            lines.append(f"• `{prefix}{usage}` - {help}")
    return "\n".join(lines)

