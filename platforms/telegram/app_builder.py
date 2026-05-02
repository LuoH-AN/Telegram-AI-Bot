"""Telegram application builder and handler registration."""
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from config import (
    TELEGRAM_API_BASE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_SEND_GLOBAL_PERIOD,
    TELEGRAM_SEND_GLOBAL_RATE,
    TELEGRAM_SEND_MAX_RETRIES,
    TELEGRAM_SEND_PER_CHAT_EDIT_PERIOD,
    TELEGRAM_SEND_PER_CHAT_EDIT_RATE,
    TELEGRAM_SEND_PER_CHAT_PERIOD,
    TELEGRAM_SEND_PER_CHAT_RATE,
    TELEGRAM_SEND_QUEUE_WARN_THRESHOLD,
    TELEGRAM_SEND_RETRY_JITTER,
)
from platforms.telegram.handlers import (
    chat,
    chat_command,
    clear,
    export_command,
    forget_command,
    handle_document,
    handle_photo,
    help_callback,
    help_command,
    login,
    memories_command,
    model_callback,
    persona_command,
    remember_command,
    set_command,
    settings_command,
    start,
    stop,
    restart,
    usage_command,
    update,
    web_command,
)
from utils.rate import QueuedRateLimiter
from .error_handler import build_error_handler

def _register_handlers(application: Application) -> None:
    for name, handler in (
        ("start", start),
        ("help", help_command),
        ("login", login),
        ("clear", clear),
        ("stop", stop),
        ("restart", restart),
        ("update", update),
        ("persona", persona_command),
        ("chat", chat_command),
        ("settings", settings_command),
        ("set", set_command),
        ("export", export_command),
        ("usage", usage_command),
        ("remember", remember_command),
        ("memories", memories_command),
        ("forget", forget_command),
        ("web", web_command),
    ):
        application.add_handler(CommandHandler(name, handler))
    application.add_handler(CallbackQueryHandler(model_callback, pattern=r"^model:|^models_"))
    application.add_handler(CallbackQueryHandler(help_callback, pattern=r"^help:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
def build_application(logger) -> Application:
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
        builder = builder.base_url(f"{TELEGRAM_API_BASE}/bot").base_file_url(f"{TELEGRAM_API_BASE}/file/bot")
        logger.info("Using custom Telegram API: %s", TELEGRAM_API_BASE)

    async def _post_init(application: Application) -> None:
        import asyncio
        from services.cron import set_main_loop

        set_main_loop(asyncio.get_running_loop())

    application = builder.post_init(_post_init).build()
    _register_handlers(application)
    application.add_error_handler(build_error_handler(logger))
    return application
