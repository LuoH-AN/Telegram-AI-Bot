"""Telegram AI Bot entry point."""

import logging
import threading

import uvicorn
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_API_BASE, HEALTH_CHECK_PORT
from cache import init_database
from web.app import create_app
from handlers import (
    start,
    help_command,
    clear,
    settings_command,
    set_command,
    export_command,
    usage_command,
    chat,
    handle_photo,
    handle_document,
    model_callback,
    help_callback,
    remember_command,
    memories_command,
    forget_command,
    persona_command,
    chat_command,
    web_command,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def start_web_server():
    """Start the FastAPI web server (runs in a daemon thread)."""
    app = create_app()
    config = uvicorn.Config(
        app, host="0.0.0.0", port=HEALTH_CHECK_PORT,
        log_level="warning", access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("Web server started on port %d", HEALTH_CHECK_PORT)
    server.run()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors from the Telegram API and bot handlers."""
    error = context.error
    if isinstance(error, TelegramError) and "Invalid server response" in str(error):
        logger.warning("Telegram API returned invalid response (likely proxy issue), will retry automatically")
        return
    user_info = ""
    user_id = None
    if isinstance(update, Update) and update.effective_user:
        user_id = update.effective_user.id
        user_info = f" [user={user_id}]"
    logger.error("Unhandled exception%s: %s", user_info, error, exc_info=context.error)
    if user_id:
        try:
            from services.log_service import record_error
            record_error(user_id, str(error), "global error handler")
        except Exception:
            pass


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return

    # Initialize database
    init_database()

    # Start web server (FastAPI + uvicorn) in background thread
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    # Create application with custom Telegram API base URL if provided
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True)
    if TELEGRAM_API_BASE:
        base_url = f"{TELEGRAM_API_BASE}/bot"
        base_file_url = f"{TELEGRAM_API_BASE}/file/bot"
        builder = builder.base_url(base_url).base_file_url(base_file_url)
        logger.info(f"Using custom Telegram API: {TELEGRAM_API_BASE}")
    application = builder.build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("persona", persona_command))
    application.add_handler(CommandHandler("chat", chat_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("set", set_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(CommandHandler("remember", remember_command))
    application.add_handler(CommandHandler("memories", memories_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("web", web_command))
    application.add_handler(CallbackQueryHandler(model_callback, pattern=r"^model:|^models_"))
    application.add_handler(CallbackQueryHandler(help_callback, pattern=r"^help:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Register error handler
    application.add_error_handler(error_handler)

    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
