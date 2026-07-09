"""Memory and generic utility message builders."""

from __future__ import annotations


def build_api_key_required_message(prefix: str) -> str:
    return f"🔑 **Please set your API key first:**\n\n`{prefix}set api_key YOUR_API_KEY`"


def build_token_limit_reached_message(prefix: str, persona_name: str) -> str:
    return (
        f"⚠️ Persona `{persona_name}` has reached token limit.\n\n"
        f"💡 Use `{prefix}usage` to view usage, or `{prefix}set token_limit <number>` to adjust limit."
    )


def build_latex_guidance() -> str:
    return "\n\n**Important:** Avoid using LaTeX delimiters ($...$ / $$...$$). Use plain text and Unicode math symbols (like × ÷ √ π ≤ ≥)."


def build_memory_empty_message(prefix: str) -> str:
    return (
        "📝 **No memories yet.**\n\n"
        f"💡 Use `{prefix}remember <content>` to add a memory.\n"
        "AI can also automatically add memories during conversation."
    )


def build_forget_usage_message(prefix: str) -> str:
    return (
        "**Usage:**\n"
        f"• `{prefix}forget <number>` - delete specific memory\n"
        f"• `{prefix}forget all` - clear all memories\n\n"
        f"💡 Use `{prefix}memories` to view numbered list."
    )


def build_usage_reset_message(persona_name: str) -> str:
    return f"🔄 Usage for persona `{persona_name}` has been reset."


def build_retry_message() -> str:
    return "❌ An error occurred. Please try again."


def build_remember_usage_message(prefix: str) -> str:
    return (
        f"**Usage:** `{prefix}remember <content>`\n\n"
        f"**Example:** `{prefix}remember I prefer concise answers`"
    )


def build_memory_list_footer_message(prefix: str) -> str:
    return (
        "\n👤 = added by you | 🤖 = added by AI\n\n"
        f"💡 `{prefix}forget <number>` to delete | `{prefix}forget all` to clear all"
    )


def build_forget_invalid_target_message(prefix: str) -> str:
    return (
        f"❌ Please specify a number or `all`.\n\n"
        f"**Example:** `{prefix}forget 1` or `{prefix}forget all`"
    )


def build_invalid_memory_number_message(index: int, prefix: str) -> str:
    return f"❌ Invalid memory number: `{index}`\n\n💡 Use `{prefix}memories` to view list."
