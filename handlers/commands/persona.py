"""Persona command handlers: /persona, /personas."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context

from services import (
    get_personas,
    get_current_persona_name,
    get_current_persona,
    switch_persona,
    create_persona,
    delete_persona,
    update_current_prompt,
    get_token_usage,
    ensure_session,
    get_message_count,
    persona_exists,
    get_session_count,
    get_current_session,
)

logger = logging.getLogger(__name__)


async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /persona command - manage personas.

    Usage:
        /persona - list all personas
        /persona <name> - switch to persona (creates if not exists)
        /persona new <name> [prompt] - create with optional prompt
        /persona delete <name> - delete a persona
        /persona prompt <text> - set current persona's prompt
    """
    user_id = update.effective_user.id
    args = context.args or []
    ctx = get_log_context(update)

    if not args:
        # List all personas
        logger.info("%s /persona list", ctx)
        await _list_personas(update, user_id)
        return

    subcmd = args[0].lower()

    if subcmd == "new":
        # Create new persona
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /persona new <name> [system prompt]\n\n"
                "Example:\n"
                "/persona new coder You are a coding assistant."
            )
            return
        name = args[1]
        prompt = " ".join(args[2:]) if len(args) > 2 else None
        if create_persona(user_id, name, prompt):
            switch_persona(user_id, name)
            logger.info("%s /persona new %s", ctx, name)
            await update.message.reply_text(
                f"Created and switched to persona: {name}\n\n"
                f"Use /persona prompt <text> to set its system prompt."
            )
        else:
            await update.message.reply_text(f"Persona '{name}' already exists.")

    elif subcmd == "delete":
        # Delete persona
        if len(args) < 2:
            await update.message.reply_text("Usage: /persona delete <name>")
            return
        name = args[1]
        if name == "default":
            await update.message.reply_text("Cannot delete the default persona.")
            return
        if delete_persona(user_id, name):
            logger.info("%s /persona delete %s", ctx, name)
            await update.message.reply_text(f"Deleted persona: {name}")
        else:
            await update.message.reply_text(f"Persona '{name}' not found.")

    elif subcmd == "prompt":
        # Set current persona's prompt
        if len(args) < 2:
            persona = get_current_persona(user_id)
            await update.message.reply_text(
                f"Current persona: {persona['name']}\n\n"
                f"Prompt: {persona['system_prompt']}\n\n"
                "Usage: /persona prompt <new prompt>"
            )
            return
        prompt = " ".join(args[1:])
        update_current_prompt(user_id, prompt)
        name = get_current_persona_name(user_id)
        logger.info("%s /persona prompt (persona=%s)", ctx, name)
        await update.message.reply_text(f"Updated prompt for '{name}'.")

    else:
        # Switch to existing persona (do NOT auto-create)
        name = args[0]
        if not persona_exists(user_id, name):
            await update.message.reply_text(
                f"Persona '{name}' not found. Use /persona new {name} to create it."
            )
            return
        switch_persona(user_id, name)
        logger.info("%s /persona switch %s", ctx, name)
        persona = get_current_persona(user_id)
        usage = get_token_usage(user_id, name)
        session_id = ensure_session(user_id, name)
        msg_count = get_message_count(session_id)
        session_ct = get_session_count(user_id, name)
        current_session = get_current_session(user_id, name)
        session_title = (current_session.get("title") or "New Chat") if current_session else "New Chat"
        prompt_text = persona['system_prompt']
        if len(prompt_text) > 100:
            prompt_text = prompt_text[:100] + "..."
        await update.message.reply_text(
            f"Switched to: {name}\n\n"
            f"Messages: {msg_count}\n"
            f"Sessions: {session_ct}\n"
            f"Current session: {session_title}\n"
            f"Tokens: {usage['total_tokens']:,}\n\n"
            f"Prompt: {prompt_text}"
        )


async def _list_personas(update: Update, user_id: int) -> None:
    """List all personas for a user."""
    personas = get_personas(user_id)
    current = get_current_persona_name(user_id)

    if not personas:
        await update.message.reply_text("No personas found.")
        return

    lines = ["Your personas:\n"]
    for name, persona in personas.items():
        marker = "> " if name == current else "  "
        usage = get_token_usage(user_id, name)
        session_id = ensure_session(user_id, name)
        msg_count = get_message_count(session_id)
        session_ct = get_session_count(user_id, name)
        prompt_preview = persona['system_prompt'][:30] + "..." if len(persona['system_prompt']) > 30 else persona['system_prompt']
        lines.append(f"{marker}{name}")
        lines.append(f"    {msg_count} msgs | {session_ct} sessions | {usage['total_tokens']:,} tokens")
        lines.append(f"    {prompt_preview}")
        lines.append("")

    lines.append("Commands:")
    lines.append("/persona <name> - switch")
    lines.append("/persona new <name> - create")
    lines.append("/persona delete <name> - delete")
    lines.append("/persona prompt <text> - set prompt")

    await update.message.reply_text("\n".join(lines))
