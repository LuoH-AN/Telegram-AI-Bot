"""Telegram AI Bot entry point."""

import logging
import threading

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

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_API_BASE,
    TELEGRAM_SEND_GLOBAL_RATE,
    TELEGRAM_SEND_GLOBAL_PERIOD,
    TELEGRAM_SEND_PER_CHAT_RATE,
    TELEGRAM_SEND_PER_CHAT_PERIOD,
    TELEGRAM_SEND_PER_CHAT_EDIT_RATE,
    TELEGRAM_SEND_PER_CHAT_EDIT_PERIOD,
    TELEGRAM_SEND_MAX_RETRIES,
    TELEGRAM_SEND_RETRY_JITTER,
    TELEGRAM_SEND_QUEUE_WARN_THRESHOLD,
    HEALTH_CHECK_PORT,
)
from cache import init_database
from services.platform_shared import start_web_server
from utils.rate_limiter import QueuedRateLimiter
from handlers import (
    start,
    help_command,
    clear,
    stop,
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
    skill_command,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            from services.log import record_error
            record_error(user_id, str(error), "global error handler")
        except Exception:
            pass


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return

    init_database()

    web_thread = threading.Thread(
        target=start_web_server,
        kwargs={"logger": logger, "port": HEALTH_CHECK_PORT},
        daemon=True,
    )
    web_thread.start()

    builder = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .rate_limiter(
            QueuedRateLimiter(
                overall_max_rate=TELEGRAM_SEND_GLOBAL_RATE,
                overall_time_period=TELEGRAM_SEND_GLOBAL_PERIOD,
                per_chat_max_rate=TELEGRAM_SEND_PER_CHAT_RATE,
                per_chat_time_period=TELEGRAM_SEND_PER_CHAT_PERIOD,
                per_chat_edit_max_rate=TELEGRAM_SEND_PER_CHAT_EDIT_RATE,
                per_chat_edit_time_period=TELEGRAM_SEND_PER_CHAT_EDIT_PERIOD,
                max_retries=TELEGRAM_SEND_MAX_RETRIES,
                retry_jitter=TELEGRAM_SEND_RETRY_JITTER,
                queue_warn_threshold=TELEGRAM_SEND_QUEUE_WARN_THRESHOLD,
            )
        )
    )
    if TELEGRAM_API_BASE:
        base_url = f"{TELEGRAM_API_BASE}/bot"
        base_file_url = f"{TELEGRAM_API_BASE}/file/bot"
        builder = builder.base_url(base_url).base_file_url(base_file_url)
        logger.info(f"Using custom Telegram API: {TELEGRAM_API_BASE}")

    async def _post_init(application: Application) -> None:
        import asyncio
        from services.cron import set_main_loop
        set_main_loop(asyncio.get_running_loop())

    builder = builder.post_init(_post_init)
    application = builder.build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("persona", persona_command))
    application.add_handler(CommandHandler("chat", chat_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("set", set_command))
    application.add_handler(CommandHandler("skill", skill_command))
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

    application.add_error_handler(error_handler)

    logger.info("Starting bot...")
    from services.cron import start_cron_scheduler
    start_cron_scheduler(application.bot)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
