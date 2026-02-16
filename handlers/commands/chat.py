"""Chat session command handler: /chat."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common import get_log_context

from services import (
    get_current_persona_name,
    get_sessions,
    get_current_session,
    get_current_session_id,
    create_session,
    delete_chat_session,
    switch_session,
    rename_session,
    get_session_message_count,
)

logger = logging.getLogger(__name__)


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /chat command - manage chat sessions.

    Usage:
        /chat                    - List sessions for current persona
        /chat new [title]        - Create new session, switch to it
        /chat <number>           - Switch to session by list number
        /chat rename <title>     - Rename current session's title
        /chat delete <number>    - Delete a session by list number
    """
    user_id = update.effective_user.id
    args = context.args or []
    ctx = get_log_context(update)
    persona_name = get_current_persona_name(user_id)

    if not args:
        # List all sessions
        logger.info("%s /chat list", ctx)
        await _list_sessions(update, user_id, persona_name)
        return

    subcmd = args[0].lower()

    if subcmd == "new":
        # Create new session
        title = " ".join(args[1:]) if len(args) > 1 else None
        session = create_session(user_id, persona_name, title)
        logger.info("%s /chat new (session_id=%s)", ctx, session["id"])
        display_title = title or "New Chat"
        await update.message.reply_text(
            f"Created new session: {display_title}\n"
            f"Switched to session #{len(get_sessions(user_id, persona_name))}"
        )

    elif subcmd == "rename":
        if len(args) < 2:
            await update.message.reply_text("Usage: /chat rename <title>")
            return
        title = " ".join(args[1:])
        if rename_session(user_id, title, persona_name):
            logger.info("%s /chat rename '%s'", ctx, title)
            await update.message.reply_text(f"Session renamed to: {title}")
        else:
            await update.message.reply_text("No current session to rename.")

    elif subcmd == "delete":
        if len(args) < 2:
            await update.message.reply_text("Usage: /chat delete <number>")
            return
        try:
            index = int(args[1])
        except ValueError:
            await update.message.reply_text("Please provide a valid session number.")
            return

        sessions = get_sessions(user_id, persona_name)
        if index < 1 or index > len(sessions):
            await update.message.reply_text(f"Invalid session number. Valid range: 1-{len(sessions)}")
            return

        session = sessions[index - 1]
        display_title = session.get("title") or "New Chat"

        if delete_chat_session(user_id, index, persona_name):
            logger.info("%s /chat delete %d", ctx, index)
            await update.message.reply_text(f"Deleted session: {display_title}")
        else:
            await update.message.reply_text("Failed to delete session.")

    else:
        # Try to parse as session number
        try:
            index = int(subcmd)
        except ValueError:
            await update.message.reply_text(
                "Unknown subcommand. Usage:\n\n"
                "/chat - list sessions\n"
                "/chat new [title] - new session\n"
                "/chat <num> - switch session\n"
                "/chat rename <title> - rename\n"
                "/chat delete <num> - delete"
            )
            return

        if switch_session(user_id, index, persona_name):
            sessions = get_sessions(user_id, persona_name)
            session = sessions[index - 1]
            display_title = session.get("title") or "New Chat"
            msg_count = get_session_message_count(session["id"])
            logger.info("%s /chat switch %d", ctx, index)
            await update.message.reply_text(
                f"Switched to session #{index}: {display_title}\n"
                f"Messages: {msg_count}"
            )
        else:
            total = len(get_sessions(user_id, persona_name))
            await update.message.reply_text(
                f"Invalid session number. Valid range: 1-{total}"
            )


async def _list_sessions(update: Update, user_id: int, persona_name: str) -> None:
    """List all sessions for a persona."""
    sessions = get_sessions(user_id, persona_name)
    current_id = get_current_session_id(user_id, persona_name)

    if not sessions:
        await update.message.reply_text(
            f"No sessions for persona '{persona_name}'.\n"
            "Send a message to create one automatically, or use /chat new"
        )
        return

    lines = [f"Sessions (persona: {persona_name})\n"]
    for i, session in enumerate(sessions, 1):
        marker = "> " if session["id"] == current_id else "  "
        title = session.get("title") or "New Chat"
        msg_count = get_session_message_count(session["id"])
        lines.append(f"{marker}{i}. {title} ({msg_count} msgs)")

    lines.append("")
    lines.append("/chat <num> - switch")
    lines.append("/chat new - new session")
    lines.append("/chat rename <title> - rename")
    lines.append("/chat delete <num> - delete")

    await update.message.reply_text("\n".join(lines))
