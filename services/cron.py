"""Cron scheduler service — daemon thread that polls and executes cron tasks."""

import asyncio
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

from cache.manager import cache
from config import VALID_REASONING_EFFORTS
from utils.provider import resolve_provider_model

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))
_POLL_INTERVAL = 30  # seconds

# Track currently running tasks to prevent duplicate execution
_running_tasks: set[tuple[int, str]] = set()  # (user_id, task_name)
_running_tasks_lock = threading.Lock()


def _cron_matches(expr: str, dt: datetime) -> bool:
    """Check if a cron expression matches the given datetime.

    Supports: * (any), */N (step), N,M (list), N-M (range), exact value.
    Fields: minute hour day month weekday (0=Sun or 7=Sun, 1=Mon..6=Sat).
    """
    parts = expr.split()
    if len(parts) != 5:
        return False

    values = [dt.minute, dt.hour, dt.day, dt.month, dt.isoweekday() % 7]
    # isoweekday: Mon=1..Sun=7; % 7 makes Sun=0

    ranges = [
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day
        (1, 12),   # month
        (0, 6),    # weekday (0=Sun)
    ]

    for field_str, current, (lo, hi) in zip(parts, values, ranges):
        if not _field_matches(field_str, current, lo, hi):
            return False
    return True


def _field_matches(field: str, value: int, lo: int, hi: int) -> bool:
    """Check if a single cron field matches the given value."""
    for item in field.split(","):
        item = item.strip()
        if not item:
            continue

        # Handle step: */N or N-M/S
        step = 1
        if "/" in item:
            base, step_str = item.split("/", 1)
            try:
                step = int(step_str)
            except ValueError:
                continue
            item = base

        if item == "*":
            # Match any value with optional step
            if (value - lo) % step == 0:
                return True
        elif "-" in item:
            # Range: N-M
            try:
                start, end = item.split("-", 1)
                start, end = int(start), int(end)
            except ValueError:
                continue
            if start <= value <= end and (value - start) % step == 0:
                return True
        else:
            # Exact value
            try:
                exact = int(item)
            except ValueError:
                continue
            if exact == value:
                return True

    return False


@contextmanager
def _heartbeat_monitor(user_id: int, task_name: str):
    """Context manager that logs heartbeat messages while a cron task runs."""
    task_start = time.time()
    phase = ["init"]
    stop_event = threading.Event()

    def _loop():
        while not stop_event.wait(10):
            elapsed = int(time.time() - task_start)
            logger.info("[user=%d] cron task '%s': %s (%ds)", user_id, task_name, phase[0], elapsed)

    hb = threading.Thread(target=_loop, daemon=True)
    hb.start()
    try:
        yield phase
    finally:
        stop_event.set()
        hb.join(timeout=1)


def _create_task_client(user_id: int, model_spec: str, settings: dict):
    """Create an AI client for a cron/title task.

    If model_spec is non-empty, resolves provider:model and creates a dedicated
    client. Otherwise falls back to the user's default client.

    Returns (client, resolved_model).
    """
    from ai import get_ai_client
    from ai.openai_client import create_openai_client

    api_key = settings["api_key"]
    base_url = settings["base_url"]
    model = settings.get("model", "gpt-4o")

    if model_spec:
        try:
            api_key, base_url, model = resolve_provider_model(
                model_spec,
                settings.get("api_presets", {}),
                api_key,
                base_url,
                model,
            )
        except ValueError:
            logger.warning("[user=%d] provider not found in presets: %s", user_id, model_spec)
            return get_ai_client(user_id), model

        client = create_openai_client(
            api_key=api_key,
            base_url=base_url,
            log_context=f"[user={user_id}]",
        )
        return client, model

    return get_ai_client(user_id), model


def _execute_cron_task(bot, task: dict) -> None:
    """Execute a single cron task: call AI with the task prompt, send result to user."""
    user_id = task["user_id"]
    task_name = task["name"]
    task_key = (user_id, task_name)
    prompt = task["prompt"]
    task_start = time.time()

    logger.info("[user=%d] cron task '%s' started | prompt: %s", user_id, task_name, prompt[:100])

    try:
        from services import get_user_settings, get_system_prompt
        from utils import get_datetime_prompt, filter_thinking_content

        settings = get_user_settings(user_id)
        if not settings.get("api_key"):
            logger.warning("[user=%d] cron task '%s' skipped: no API key", user_id, task_name)
            return
        reasoning_effort = str(settings.get("reasoning_effort", "") or "").strip().lower()
        if reasoning_effort not in VALID_REASONING_EFFORTS:
            reasoning_effort = ""

        client, cron_model = _create_task_client(
            user_id, settings.get("cron_model", ""), settings
        )

        system_prompt = get_system_prompt(user_id)
        system_prompt += "\n\n" + get_datetime_prompt()
        platform_hint = _detect_platform(bot)
        system_prompt += (
            "\n\nYou are executing a scheduled task. Provide a concise, useful response."
        )
        system_prompt += f"\n\nScheduled task results are delivered via {platform_hint}."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        with _heartbeat_monitor(user_id, task_name) as phase:
            full_response = ""
            last_text_response = ""

            while True:
                phase[0] = "waiting for AI"
                chunks = list(client.chat_completion(
                    messages=messages,
                    model=cron_model,
                    temperature=settings["temperature"],
                    reasoning_effort=reasoning_effort or None,
                    stream=False,
                ))

                if not chunks:
                    break

                chunk = chunks[0]
                content = chunk.content or ""
                full_response = content

                if content.strip():
                    last_text_response = content

                if chunk.finish_reason == "length":
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "Please continue and complete your response concisely."})
                    continue
                break

            final_text = filter_thinking_content(full_response).strip()
            if not final_text and last_text_response:
                final_text = filter_thinking_content(last_text_response).strip()
            if not final_text:
                final_text = "(Scheduled task produced no output)"

            result_text = f"[Scheduled: {task_name}]\n\n{final_text}"

            phase[0] = "sending message"
            _send_message(bot, user_id, result_text)

        # Update last_run_at
        now = datetime.now(_CST)
        cache.update_cron_last_run(user_id, task_name, now)

        logger.info("[user=%d] cron task '%s' completed successfully (%ds)", user_id, task_name, int(time.time() - task_start))

    except Exception as e:
        logger.exception("[user=%d] cron task '%s' failed (%ds)", user_id, task_name, int(time.time() - task_start))
        try:
            _send_message(bot, user_id, f"[Scheduled: {task_name}]\n\nError: {e}")
        except Exception:
            logger.exception("[user=%d] failed to send cron error message", user_id)
    finally:
        with _running_tasks_lock:
            _running_tasks.discard(task_key)


def _detect_platform(bot) -> str:
    """Detect the platform from the bot instance."""
    if hasattr(bot, "send_message"):
        return "Telegram"
    if hasattr(bot, "fetch_user"):
        return "Discord DM"
    if hasattr(bot, "send_wechat_text"):
        return "WeChat"
    return "this platform"


def _send_telegram(bot, chat_id: int, text: str, loop) -> None:
    """Send a message via Telegram bot."""
    from telegram.constants import ParseMode
    from utils.formatters import markdown_to_telegram_html, split_message

    html_text = markdown_to_telegram_html(text)
    chunks = split_message(html_text, max_length=4096)
    for chunk in chunks:
        future = asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML),
            loop,
        )
        future.result(timeout=60)


def _send_discord(bot, chat_id: int, text: str, loop) -> None:
    """Send a message via Discord bot DM."""
    from utils.formatters import split_message

    chunks = split_message(text, max_length=2000)

    async def _dm() -> None:
        user = bot.get_user(chat_id)
        if user is None:
            user = await bot.fetch_user(chat_id)
        if user is None:
            raise RuntimeError(f"Discord user {chat_id} not found")
        for chunk in chunks:
            await user.send(chunk)

    future = asyncio.run_coroutine_threadsafe(_dm(), loop)
    future.result(timeout=60)


def _send_wechat(bot, chat_id: int, text: str, loop) -> None:
    """Send a message via WeChat runtime."""
    future = asyncio.run_coroutine_threadsafe(bot.send_wechat_text(chat_id, text), loop)
    future.result(timeout=60)


def _send_message(bot, chat_id: int, text: str) -> None:
    """Send a cron result message using the active runtime platform."""
    loop = _main_loop
    if loop is None or loop.is_closed():
        logger.error("Main event loop not available, cannot send cron message")
        return

    if hasattr(bot, "send_message"):
        _send_telegram(bot, chat_id, text, loop)
    elif hasattr(bot, "fetch_user"):
        _send_discord(bot, chat_id, text, loop)
    elif hasattr(bot, "send_wechat_text"):
        _send_wechat(bot, chat_id, text, loop)
    else:
        logger.error("Unsupported bot type for cron delivery: %s", type(bot).__name__)


def _scheduler_loop(bot) -> None:
    """Background loop that checks cron tasks every POLL_INTERVAL seconds."""
    while True:
        time.sleep(_POLL_INTERVAL)
        try:
            now = datetime.now(_CST)
            tasks = cache.get_all_cron_tasks()

            for task in tasks:
                if not task.get("enabled", True):
                    continue

                expr = task.get("cron_expression", "")
                if not _cron_matches(expr, now):
                    continue

                # Avoid re-running within the same minute
                last_run = task.get("last_run_at")
                if last_run:
                    if hasattr(last_run, "minute"):
                        # datetime object
                        if (last_run.year == now.year and last_run.month == now.month
                                and last_run.day == now.day and last_run.hour == now.hour
                                and last_run.minute == now.minute):
                            continue

                # Skip if already running
                task_key = (task["user_id"], task["name"])
                with _running_tasks_lock:
                    if task_key in _running_tasks:
                        continue
                    _running_tasks.add(task_key)

                # Execute in a separate thread to avoid blocking the scheduler
                thread = threading.Thread(
                    target=_execute_cron_task,
                    args=(bot, task),
                    daemon=True,
                )
                thread.start()

        except Exception:
            logger.exception("Cron scheduler error")


_bot_ref = None
_main_loop = None


def set_main_loop(loop) -> None:
    """Store reference to the main asyncio event loop (called from post_init)."""
    global _main_loop
    _main_loop = loop


def start_cron_scheduler(bot) -> None:
    """Start the cron scheduler daemon thread."""
    global _bot_ref
    _bot_ref = bot
    thread = threading.Thread(target=_scheduler_loop, args=(bot,), daemon=True)
    thread.start()
    platform = _detect_platform(bot)
    logger.info("Cron scheduler started (platform=%s, poll interval=%ds)", platform, _POLL_INTERVAL)


def run_cron_task(user_id: int, task_name: str) -> str:
    """Manually trigger a cron task by name. Called from CronTool.execute (sync thread).

    Returns a status message. The actual AI execution + platform delivery
    happens in a background thread (same as scheduled runs).
    """
    if _bot_ref is None:
        return "Error: Bot is not initialized yet."

    tasks = cache.get_cron_tasks(user_id)
    task = next((t for t in tasks if t["name"] == task_name), None)
    if task is None:
        return f"Error: Task '{task_name}' not found."

    thread = threading.Thread(
        target=_execute_cron_task,
        args=(_bot_ref, task),
        daemon=True,
    )
    thread.start()
    return f"Task '{task_name}' triggered. The result will be sent as a separate message."
