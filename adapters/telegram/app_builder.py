"""Telegram application builder and handler registration."""
from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from infrastructure.config import (
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
    ADMIN_IDS,
    OWNER_ID,
)
from adapters.telegram.commands import all_commands, make_handler
from adapters.telegram.approval import terminal_approval_callback
from adapters.telegram.ux.callbacks import ux_callback
from adapters.telegram.ux.pending import handle_pending_input
from adapters.telegram.handlers import (
    chat,
    handle_document,
    handle_photo,
    help_callback,
    model_callback,
)
from .rate import QueuedRateLimiter
from .error_handler import build_error_handler

def _register_handlers(application: Application) -> None:
    for cmd in all_commands():
        application.add_handler(CommandHandler(cmd.name, make_handler(cmd)))
    application.add_handler(CallbackQueryHandler(model_callback, pattern=r"^model:|^models_"))
    application.add_handler(CallbackQueryHandler(help_callback, pattern=r"^help:"))
    application.add_handler(CallbackQueryHandler(terminal_approval_callback, pattern=r"^term:"))
    application.add_handler(CallbackQueryHandler(ux_callback, pattern=r"^ux:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pending_input), group=-1)
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
        from domain.services.cron import set_main_loop

        set_main_loop(asyncio.get_running_loop())
        from adapters.telegram.terminal_completion import start_terminal_completion_monitor

        start_terminal_completion_monitor(application)
        common_commands = [
            BotCommand("start", "打开主菜单 / Open main menu"),
            BotCommand("chat", "管理会话 / Manage chats"),
            BotCommand("settings", "打开设置 / Open settings"),
            BotCommand("usage", "查看用量 / View usage"),
            BotCommand("stop", "停止生成 / Stop generating"),
            BotCommand("cancel", "取消当前输入 / Cancel input"),
            BotCommand("help", "查看帮助 / View help"),
        ]
        await application.bot.set_my_commands(common_commands)
        admin_commands = common_commands + [
            BotCommand("update", "检查并应用更新 / Apply updates"),
            BotCommand("restart", "安全重启服务 / Restart safely"),
            BotCommand("status", "查看运行状态 / Runtime status"),
        ]
        admin_ids = set(ADMIN_IDS)
        if OWNER_ID is not None:
            admin_ids.add(OWNER_ID)
        for admin_id in admin_ids:
            try:
                await application.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(admin_id))
            except Exception as exc:
                logger.warning("Could not set Telegram command menu for admin %s: %s", admin_id, exc)

    async def _post_shutdown(application: Application) -> None:
        from adapters.telegram.terminal_completion import stop_terminal_completion_monitor

        await stop_terminal_completion_monitor(application)

    application = builder.post_init(_post_init).post_shutdown(_post_shutdown).build()
    _register_handlers(application)
    application.add_error_handler(build_error_handler(logger))
    return application
